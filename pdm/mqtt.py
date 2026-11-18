import os
import threading
import paho.mqtt.client as mqtt


def client(client_id, manual_ack=False):
    instance = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id,
        clean_session=False, manual_ack=manual_ack)
    instance.reconnect_delay_set(min_delay=1, max_delay=30)
    if os.getenv('MQTT_USER'):
        instance.username_pw_set(os.environ['MQTT_USER'], os.environ['MQTT_PASSWORD'])
    return instance


def connect(instance):
    instance.connect(os.getenv('MQTT_HOST', 'localhost'), int(os.getenv('MQTT_PORT', '1883')), 60)


def wait_connected(instance, timeout=15):
    ready = threading.Event()
    instance.on_connect = lambda c, u, f, rc, p: ready.set() if not rc.is_failure else None
    connect(instance); instance.loop_start()
    if not ready.wait(timeout):
        instance.loop_stop()
        raise TimeoutError('Connexion MQTT impossible')
