import json
import os
from datetime import datetime
from pathlib import Path
import httpx
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from pdm.schema import NUMERIC, Thresholds


class Integrations:
    def __init__(self):
        self.influx = None
        self.tb_url = os.getenv('TB_URL', 'http://localhost:8080').rstrip('/')
        self.tokens_path = Path(os.getenv('TB_TOKENS_PATH', 'runtime/tb_devices.json'))
        self.http = httpx.Client(timeout=5)
        if os.getenv('INFLUX_URL'):
            self.influx = InfluxDBClient(url=os.environ['INFLUX_URL'], token=os.environ['INFLUX_TOKEN'], org=os.getenv('INFLUX_ORG', 'industrie'))
            self.writer = self.influx.write_api(write_options=SYNCHRONOUS)
        self.bucket = os.getenv('INFLUX_BUCKET', 'maintenance')

    def tokens(self):
        return json.loads(self.tokens_path.read_text(encoding='utf-8')) if self.tokens_path.exists() else {}

    def send(self, sink, result):
        if sink == 'influx':
            point = Point('telemetry').tag('machine_id', result['machine_id']).tag('model_version', result['model_version'])
            # Timestamp de réception stable lors des retries : réécriture idempotente du point.
            point.time(datetime.fromisoformat(result['received_at']))
            for key in NUMERIC + ['panne_probable', 'seuil_critique']:
                point.field(key, float(result[key]))
            for key in ['message_id', 'type', 'sent_at', 'status']:
                point.field(key, result[key])
            point.field('source_row', result['source_row']).field('payload', json.dumps(result))
            self.writer.write(bucket=self.bucket, record=point)
        elif sink == 'thingsboard':
            token = self.tokens().get(result['machine_id'])
            if not token:
                raise RuntimeError('Device ThingsBoard non provisionné : ' + result['machine_id'])
            values = {k: v for k, v in result.items() if v is not None}
            response = self.http.post(f'{self.tb_url}/api/v1/{token}/telemetry', json={
                'ts': int(datetime.fromisoformat(result['received_at']).timestamp() * 1000), 'values': values})
            response.raise_for_status()

    def sync_thresholds(self, service):
        for machine, token in self.tokens().items():
            response = self.http.get(f'{self.tb_url}/api/v1/{token}/attributes', params={'sharedKeys': 'seuil_critique,seuil_retour,clear_count'})
            response.raise_for_status()
            shared = response.json().get('shared', {})
            if 'seuil_critique' in shared:
                current = service.thresholds(machine)
                service.set_thresholds(machine, Thresholds(critical=shared['seuil_critique'],
                    clear=shared.get('seuil_retour', current.clear), clear_count=shared.get('clear_count', current.clear_count)))

    def history(self, machine, limit):
        # Valeurs échappées comme littéraux JSON ; pas d'interpolation de Flux brut.
        query = f'from(bucket: {json.dumps(self.bucket)}) |> range(start: -30d) |> filter(fn: (r) => r._measurement == "telemetry" and r._field == "payload")'
        if machine:
            query += f' |> filter(fn: (r) => r.machine_id == {json.dumps(machine)})'
        query += f' |> group() |> sort(columns: ["_time"], desc: true) |> limit(n: {limit})'
        records = [json.loads(record.get_value()) for table in self.influx.query_api().query(query) for record in table.records]
        return list(reversed(records))

    def close(self):
        self.http.close()
        if self.influx:
            self.writer.close(); self.influx.close()
