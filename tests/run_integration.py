"""Test réseau réel sans Docker + benchmark. Lancer depuis la racine du projet."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import httpx
import psutil
from websockets.sync.client import connect
from pdm.mqtt import client, wait_connected
from pdm.simulator import messages


def wait_port(port):
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=.5):
                return
        except OSError:
            time.sleep(.2)
    raise TimeoutError(f'Port {port} non disponible')


def main():
    processes = []
    with tempfile.TemporaryDirectory() as temp:
        env = {**os.environ, 'MQTT_HOST': '127.0.0.1', 'MQTT_PORT': '18883',
            'API_URL': 'http://127.0.0.1:18000', 'DATABASE_PATH': str(Path(temp)/'journal.sqlite'),
            'TB_ENABLED': '0', 'PYTHONPATH': str(Path.cwd())}
        env.pop('INFLUX_URL', None)
        os.environ.update({'MQTT_HOST': '127.0.0.1', 'MQTT_PORT': '18883'})
        def launch(args):
            process = subprocess.Popen([sys.executable, *args], env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            processes.append(process)
        try:
            launch(['tests/local_broker.py']); wait_port(18883)
            launch(['-m', 'uvicorn', 'pdm.api:app', '--host', '127.0.0.1', '--port', '18000']); wait_port(18000)
            launch(['-m', 'pdm.consumer']); time.sleep(2)
            publisher = client('integration-publisher'); wait_connected(publisher)
            expected = list(messages(count=5))
            with connect('ws://127.0.0.1:18000/ws') as ws:
                for item in expected:
                    publisher.publish('industrie/SIM_AI4I/telemetry', json.dumps(item), qos=1).wait_for_publish(5)
                    result = json.loads(ws.recv(timeout=15))
                    assert result['message_id'] == item['message_id']
                    assert 0 <= result['panne_probable'] <= 1
                publisher.publish('industrie/SIM_AI4I/telemetry', json.dumps(expected[0]), qos=1).wait_for_publish(5)
            publisher.disconnect(); publisher.loop_stop()
            time.sleep(.5)
            with httpx.Client(base_url='http://127.0.0.1:18000') as http:
                history = http.get('/api/history').json()
                assert len(history) == 5
                assert http.post('/api/telemetry', json=expected[0]).json()['duplicate']
                assert http.get('/health').json()['events'] == 5
            subprocess.run([sys.executable, '-m', 'pdm.benchmark', '--count', '100', '--broker-label', 'aMQTT 0.11.3 / Windows / loopback (broker de test)'], env=env, check=True)
            benchmark = json.loads(Path('reports/benchmark.json').read_text())
            assert all(r['unique_received'] == 100 for r in benchmark['results'])
            Path('reports/integration.json').write_text(json.dumps({'result':'passed','flow':'MQTT QoS1 -> consumer -> HTTP -> vrai modèle -> SQLite -> WebSocket',
                'unique_messages':5,'deduplication_verified':True,'broker':'aMQTT 0.11.3',
                'not_executed':['Mosquitto Docker','InfluxDB','Grafana','Node-RED runtime','ThingsBoard runtime']} , indent=2), encoding='utf-8')
            print('Intégration réseau réussie : 5 messages, déduplication, REST et WebSocket.')
        finally:
            children = []
            for process in processes:
                try:
                    children.extend(psutil.Process(process.pid).children(recursive=True))
                except psutil.NoSuchProcess:
                    pass
            for child in reversed(children):
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass
            for process in reversed(processes):
                process.terminate()
            for process in processes:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()
            _, alive = psutil.wait_procs(children, timeout=10)
            for child in alive:
                child.kill()
            psutil.wait_procs(alive, timeout=10)


if __name__ == '__main__':
    main()
