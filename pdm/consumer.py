"""MQTT QoS1 -> API. Acquittement après écriture du journal, retry des erreurs temporaires."""
import json
import logging
import os
import queue
import time
from pathlib import Path
import httpx
from pdm.mqtt import client, connect

log = logging.getLogger('consumer')


def main():
    logging.basicConfig(level=logging.INFO)
    pending = queue.Queue(maxsize=1000)
    mqtt = client('pdm-consumer-v1', manual_ack=True)
    mqtt.on_connect = lambda c, u, f, rc, p: c.subscribe('industrie/+/telemetry', qos=1) if not rc.is_failure else None
    def receive(c, u, message):
        try:
            pending.put_nowait(message)
        except queue.Full:
            # Quitter sans ACK : le superviseur redémarre avec la session persistante.
            log.error('File pleine : redémarrage requis')
            os._exit(1)
    mqtt.on_message = receive
    for attempt in range(60):
        try:
            connect(mqtt); break
        except OSError:
            if attempt == 59:
                raise
            time.sleep(2)
    mqtt.loop_start()
    api = os.getenv('API_URL', 'http://localhost:8000')
    try:
        with httpx.Client(timeout=30) as http:
            while True:
                message = pending.get()
                while True:
                    try:
                        response = http.post(api + '/api/telemetry', content=message.payload, headers={'Content-Type': 'application/json'})
                        if response.status_code in (400, 409, 422):
                            Path('runtime').mkdir(exist_ok=True)
                            with open('runtime/rejected.jsonl', 'a', encoding='utf-8') as file:
                                file.write(json.dumps({'topic': message.topic, 'payload': message.payload.decode(errors='replace'), 'error': response.text}) + '\n')
                            log.warning('Message rejeté et archivé : %s', response.status_code)
                        else:
                            response.raise_for_status()
                        mqtt.ack(message.mid, message.qos)
                        break
                    except httpx.HTTPError as error:
                        log.warning('API indisponible (%s), nouvel essai dans 2 s', type(error).__name__)
                        time.sleep(2)
    finally:
        mqtt.disconnect(); mqtt.loop_stop()


if __name__ == '__main__':
    main()
