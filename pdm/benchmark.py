"""Comparaison réelle de trois transports sur un même collecteur de validation/écho."""
import argparse
import json
import random
import statistics
import threading
import time
import uuid
from pathlib import Path
import httpx
import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from websockets.sync.client import connect as ws_connect
from pdm.mqtt import client, connect
from pdm.schema import Telemetry
from pdm.simulator import messages


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--count', type=int, default=100)
    parser.add_argument('--port', type=int, default=8090)
    parser.add_argument('--broker-label', default='Mosquitto / Docker')
    args = parser.parse_args()
    if args.count < 100 or args.count > 2000:
        parser.error('Choisir entre 100 et 2000 messages par protocole.')
    run = uuid.uuid4().hex
    inbound, outbound = f'benchmark/{run}/in', f'benchmark/{run}/out'
    ready, ack = threading.Event(), threading.Event()
    received = []
    echo = client('bench-echo-' + run[:8])
    def echo_connected(c, u, f, rc, p):
        c.subscribe(inbound, qos=1)
    echo.on_connect = echo_connected
    echo.on_subscribe = lambda *a: ready.set()
    def echo_message(c, u, message):
        Telemetry.model_validate_json(message.payload)
        c.publish(outbound, message.payload, qos=1)
    echo.on_message = echo_message
    connect(echo); echo.loop_start()
    if not ready.wait(15):
        raise TimeoutError('Abonnement collecteur MQTT')
    sender = client('bench-send-' + run[:8])
    ready.clear()
    sender.on_connect = lambda c, u, f, rc, p: c.subscribe(outbound, qos=1)
    sender.on_subscribe = lambda *a: ready.set()
    def collect(c, u, message):
        received.append(message.payload)
        ack.set()
    sender.on_message = collect
    connect(sender); sender.loop_start()
    if not ready.wait(15):
        raise TimeoutError('Abonnement retour MQTT')
    app = FastAPI()
    @app.post('/echo')
    async def http_echo(request: Request):
        payload = await request.body()
        Telemetry.model_validate_json(payload)
        return Response(content=payload, media_type='application/json')
    @app.websocket('/echo')
    async def websocket_echo(ws: WebSocket):
        await ws.accept()
        try:
            while True:
                body = await ws.receive_text()
                Telemetry.model_validate_json(body)
                await ws.send_text(body)
        except WebSocketDisconnect:
            pass
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=args.port, log_level='error'))
    thread = threading.Thread(target=server.run, daemon=True); thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline:
            raise TimeoutError('Collecteur HTTP')
        time.sleep(.05)
    payloads = [json.dumps(m, separators=(',', ':')).encode() for m in messages(count=args.count)]
    order = ['MQTT', 'HTTP', 'WebSocket']; random.Random(42).shuffle(order)
    raw, summaries = [], []
    try:
        with httpx.Client(timeout=5) as http, ws_connect(f'ws://127.0.0.1:{args.port}/echo') as ws:
            def exchange(protocol, payload):
                if protocol == 'HTTP':
                    response = http.post(f'http://127.0.0.1:{args.port}/echo', content=payload, headers={'Content-Type': 'application/json'})
                    response.raise_for_status(); return response.content
                if protocol == 'WebSocket':
                    ws.send(payload.decode()); return ws.recv(timeout=5).encode()
                ack.clear()
                expected = json.loads(payload)['message_id']
                sender.publish(inbound, payload, qos=1)
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    ack.wait(max(0, deadline - time.monotonic())); ack.clear()
                    matching = [r for r in received if json.loads(r)['message_id'] == expected]
                    if matching:
                        return matching[-1]
                raise TimeoutError('Écho MQTT')
            for protocol in order:
                # Chauffe avec un id séparé : exclue des statistiques.
                warm = json.loads(payloads[0]); warm['message_id'] = 'warm-' + run
                exchange(protocol, json.dumps(warm).encode()); received.clear()
                latencies, unique, tx, rx = [], set(), 0, 0
                for payload in payloads:
                    mid = json.loads(payload)['message_id']; tx += len(payload)
                    start = time.perf_counter_ns()
                    try:
                        response = exchange(protocol, payload)
                        elapsed = (time.perf_counter_ns() - start) / 1e6
                        if json.loads(response) != json.loads(payload):
                            raise ValueError('Écho différent')
                        unique.add(mid); rx += len(response); latencies.append(elapsed)
                        raw.append({'protocol': protocol, 'message_id': mid, 'rtt_ms': elapsed, 'ok': True})
                    except Exception as error:
                        raw.append({'protocol': protocol, 'message_id': mid, 'ok': False, 'error': type(error).__name__})
                mqtt_ids = [json.loads(r)['message_id'] for r in received]
                duplicate_count = len(mqtt_ids) - len(set(mqtt_ids)) if protocol == 'MQTT' else 0
                summaries.append({'protocol': protocol, 'sent': len(payloads), 'unique_received': len(unique),
                    'delivery_pct': 100 * len(unique) / len(payloads), 'duplicates_observed': duplicate_count,
                    'mean_rtt_ms': statistics.mean(latencies) if latencies else None,
                    'median_rtt_ms': statistics.median(latencies) if latencies else None,
                    'p95_rtt_ms': sorted(latencies)[max(0, int(.95 * len(latencies) + .999) - 1)] if latencies else None,
                    'max_rtt_ms': max(latencies) if latencies else None,
                    'application_request_bytes': tx, 'application_echo_bytes': rx})
    finally:
        server.should_exit = True; thread.join(timeout=10)
        sender.disconnect(); sender.loop_stop(); echo.disconnect(); echo.loop_stop()
    Path('reports').mkdir(exist_ok=True)
    report = {'broker': args.broker_label, 'order': order, 'count_per_protocol': args.count,
        'method': 'RTT applicatif validation/écho, connexions réutilisées, localhost, séquentiel, sans ML ni stockage.',
        'volume_scope': 'Octets JSON applicatifs uniquement, hors en-têtes, handshakes, ACK, retransmissions et TCP/IP.',
        'results': summaries}
    Path('reports/benchmark.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    Path('reports/benchmark_raw.jsonl').write_text('\n'.join(json.dumps(r) for r in raw), encoding='utf-8')
    lines = ['# Comparaison expérimentale des protocoles', '', report['method'], '', f"Broker : {args.broker_label}. Ordre : {order}.", '',
        '| Protocole | Émis | Reçus uniques | Livraison | Moyenne RTT ms | P95 ms | Octets requêtes / échos |', '|---|---:|---:|---:|---:|---:|---:|']
    for r in summaries:
        lines.append(f"| {r['protocol']} | {r['sent']} | {r['unique_received']} | {r['delivery_pct']:.1f}% | {r['mean_rtt_ms']} | {r['p95_rtt_ms']} | {r['application_request_bytes']} / {r['application_echo_bytes']} |")
    lines += ['', report['volume_scope'], '', 'Le volume affiché ne permet pas de comparer le surcoût réseau. Une capture Wireshark est nécessaire pour cela. La livraison mesure les échos valides reçus avant timeout (5 s), sans perturbation réseau artificielle. Une exécution locale unique ne prouve pas la fiabilité en production.', '', 'MQTT comporte deux passages par le broker, HTTP et WebSocket un aller-retour direct. Répéter les essais pour étudier la variabilité. Les résultats ne représentent pas la latence de toute la chaîne ML.']
    Path('reports/comparaison_protocoles.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
