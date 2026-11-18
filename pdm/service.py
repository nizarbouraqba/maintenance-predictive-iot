"""Journal transactionnel local et outbox : un message accepté survit au redémarrage."""
import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from pdm.schema import FEATURES, Thresholds


class Conflict(Exception):
    pass


class Service:
    def __init__(self, artifact, database='runtime/journal.sqlite', sinks=()):
        Path(database).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(database, check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, fingerprint TEXT, machine TEXT, ts TEXT, body TEXT);
            CREATE INDEX IF NOT EXISTS event_machine_time ON events(machine, ts);
            CREATE TABLE IF NOT EXISTS states (machine TEXT PRIMARY KEY, active INTEGER, low_count INTEGER);
            CREATE TABLE IF NOT EXISTS settings (machine TEXT PRIMARY KEY, body TEXT);
            CREATE TABLE IF NOT EXISTS outbox (id TEXT, sink TEXT, PRIMARY KEY(id, sink));
        ''')
        self.artifact, self.sinks = artifact, sinks
        self.lock = threading.RLock()

    def thresholds(self, machine):
        with self.lock:
            row = self.db.execute('SELECT body FROM settings WHERE machine=?', (machine,)).fetchone()
        return Thresholds.model_validate_json(row[0]) if row else Thresholds()

    def set_thresholds(self, machine, thresholds):
        with self.lock, self.db:
            self.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (machine, thresholds.model_dump_json()))

    def ingest(self, telemetry):
        payload = telemetry.model_dump(mode='json')
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with self.lock:
            existing = self.db.execute('SELECT fingerprint, body FROM events WHERE id=?', (telemetry.message_id,)).fetchone()
            if existing:
                if existing[0] != fingerprint:
                    raise Conflict('message_id réutilisé avec un contenu différent')
                return json.loads(existing[1]), True
            score = float(self.artifact['pipeline'].predict_proba(pd.DataFrame([payload])[FEATURES])[0, 1])
            threshold = self.thresholds(telemetry.machine_id)
            state = self.db.execute('SELECT active, low_count FROM states WHERE machine=?', (telemetry.machine_id,)).fetchone()
            active, low_count = state if state else (False, 0)
            if score > threshold.critical:
                active, low_count = True, 0
            elif active:
                low_count = low_count + 1 if score < threshold.clear else 0
                if low_count >= threshold.clear_count:
                    active, low_count = False, 0
            now = datetime.now(timezone.utc).isoformat()
            result = {**payload, 'received_at': now, 'panne_probable': score,
                'status': 'CRITICAL' if active else 'NORMAL', 'model_version': self.artifact['version'],
                'seuil_critique': threshold.critical, 'seuil_retour': threshold.clear,
                'clear_count': threshold.clear_count, 'low_count': low_count}
            with self.db:
                self.db.execute('INSERT INTO events VALUES (?,?,?,?,?)', (telemetry.message_id, fingerprint, telemetry.machine_id, now, json.dumps(result)))
                self.db.execute('INSERT OR REPLACE INTO states VALUES (?,?,?)', (telemetry.machine_id, int(active), low_count))
                self.db.executemany('INSERT INTO outbox VALUES (?,?)', [(telemetry.message_id, sink) for sink in self.sinks])
            return result, False

    def history(self, machine=None, limit=100):
        with self.lock:
            if machine:
                rows = self.db.execute('SELECT body FROM events WHERE machine=? ORDER BY ts DESC LIMIT ?', (machine, limit)).fetchall()
            else:
                rows = self.db.execute('SELECT body FROM events ORDER BY ts DESC LIMIT ?', (limit,)).fetchall()
        return [json.loads(row[0]) for row in reversed(rows)]

    def pending(self):
        with self.lock:
            rows = self.db.execute('SELECT o.id,o.sink,e.body FROM outbox o JOIN events e ON o.id=e.id ORDER BY e.ts LIMIT 100').fetchall()
        return [(mid, sink, json.loads(body)) for mid, sink, body in rows]

    def delivered(self, mid, sink):
        with self.lock, self.db:
            self.db.execute('DELETE FROM outbox WHERE id=? AND sink=?', (mid, sink))

    def stats(self):
        with self.lock:
            return {'events': self.db.execute('SELECT COUNT(*) FROM events').fetchone()[0],
                'pending_deliveries': self.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0]}

    def close(self):
        self.db.close()
