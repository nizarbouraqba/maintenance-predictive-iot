"""Broker de test uniquement ; Mosquitto reste le broker du déploiement Docker."""
import asyncio
import logging
from amqtt.broker import Broker


async def main():
    logging.basicConfig(level=logging.ERROR)
    broker = Broker({'listeners': {'default': {'type': 'tcp', 'bind': '127.0.0.1:18883'}},
        'plugins': {'amqtt.plugins.authentication.AnonymousAuthPlugin': {'allow_anonymous': True}}})
    await broker.start()
    try:
        await asyncio.Event().wait()
    finally:
        await broker.shutdown()


if __name__ == '__main__':
    asyncio.run(main())
