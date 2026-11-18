import argparse
import json
import time
import uuid
from datetime import datetime, timezone
import httpx
import pandas as pd
from pdm.mqtt import client, wait_connected
from pdm.schema import FEATURES


def messages(csv='data/test.csv', count=100, machine='SIM_AI4I', seed=42):
    frame = pd.read_csv(csv).sample(frac=1, random_state=seed).head(count)
    run = uuid.uuid4().hex[:12]
    for _, row in frame.iterrows():
        yield {**{key: row[key] for key in FEATURES}, 'message_id': f'{run}-{int(row.UDI)}',
            'machine_id': machine, 'source_row': int(row.UDI), 'measured_at': None,
            'sent_at': datetime.now(timezone.utc).isoformat()}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--protocol', choices=['mqtt', 'http'], default='mqtt')
    p.add_argument('--count', type=int, default=2000)
    p.add_argument('--interval', type=float, default=1)
    p.add_argument('--csv', default='data/test.csv')
    p.add_argument('--api', default='http://localhost:8000')
    args = p.parse_args()
    if args.count < 1 or args.interval < 0:
        p.error('count >= 1 et interval >= 0 requis')
    sender = client('pdm-simulator-' + uuid.uuid4().hex[:8]) if args.protocol == 'mqtt' else None
    if sender:
        wait_connected(sender)
    try:
        with httpx.Client(timeout=30) as http:
            for message in messages(args.csv, args.count):
                # Réessayer le même message conserve l'id et le timestamp.
                for attempt in range(10):
                    try:
                        if sender:
                            info = sender.publish(f"industrie/{message['machine_id']}/telemetry", json.dumps(message), qos=1)
                            info.wait_for_publish(timeout=15)
                            if not info.is_published():
                                raise TimeoutError('PUBACK non reçu')
                        else:
                            response = http.post(args.api + '/api/telemetry', json=message)
                            response.raise_for_status()
                        break
                    except (httpx.HTTPError, RuntimeError, TimeoutError):
                        if attempt == 9:
                            raise
                        time.sleep(min(2 ** attempt, 10))
                print(message['message_id'], flush=True)
                time.sleep(args.interval)
    finally:
        if sender:
            sender.disconnect(); sender.loop_stop()


if __name__ == '__main__':
    main()
