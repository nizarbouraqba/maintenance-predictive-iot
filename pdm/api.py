import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Literal
import joblib
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pdm.integrations import Integrations
from pdm.schema import Telemetry, Thresholds
from pdm.service import Conflict, Service

log = logging.getLogger('pdm')


def create_app(artifact=None, database=None):
    queues = set()

    @asynccontextmanager
    async def lifespan(app):
        loaded = artifact if artifact is not None else joblib.load(os.getenv('MODEL_PATH', 'models/random_forest.joblib'))
        sinks = tuple(s for s, enabled in [('influx', os.getenv('INFLUX_URL')), ('thingsboard', os.getenv('TB_ENABLED') == '1')] if enabled)
        app.state.service = Service(loaded, database or os.getenv('DATABASE_PATH', 'runtime/journal.sqlite'), sinks)
        app.state.integrations = Integrations()
        app.state.integration_errors = {}
        async def delivery_loop():
            tick = 0
            while True:
                # Ordre conservé par destination ; arrêter cette destination après une erreur.
                failed = set()
                for mid, sink, result in app.state.service.pending():
                    if sink in failed:
                        continue
                    try:
                        await asyncio.to_thread(app.state.integrations.send, sink, result)
                        app.state.service.delivered(mid, sink)
                        app.state.integration_errors.pop(sink, None)
                    except Exception as error:
                        failed.add(sink)
                        app.state.integration_errors[sink] = type(error).__name__
                        log.warning('Livraison %s différée (%s)', sink, type(error).__name__)
                if 'thingsboard' in sinks and tick % 5 == 0:
                    try:
                        await asyncio.to_thread(app.state.integrations.sync_thresholds, app.state.service)
                        app.state.integration_errors.pop('attributes', None)
                    except Exception as error:
                        app.state.integration_errors['attributes'] = type(error).__name__
                tick += 1
                await asyncio.sleep(1)
        worker = asyncio.create_task(delivery_loop())
        try:
            yield
        finally:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker
            app.state.integrations.close(); app.state.service.close()

    app = FastAPI(title='Projet 11 — Maintenance IoT', version='1.0.0', lifespan=lifespan)

    @app.get('/')
    def index():
        return FileResponse(Path(__file__).parent / 'static' / 'index.html')

    @app.get('/health')
    def health():
        return {'status': 'degraded' if app.state.integration_errors else 'ok',
            'model': app.state.service.artifact['version'], 'sinks': app.state.service.sinks,
            'integration_errors': app.state.integration_errors, **app.state.service.stats()}

    @app.post('/api/telemetry')
    async def telemetry(body: Telemetry):
        try:
            result, duplicate = await asyncio.to_thread(app.state.service.ingest, body)
        except Conflict as error:
            raise HTTPException(409, str(error)) from error
        if not duplicate:
            for queue in tuple(queues):
                if queue.full():
                    queue.get_nowait()  # L'historique REST permet le rattrapage.
                queue.put_nowait(result)
        return {**result, 'duplicate': duplicate}

    @app.get('/api/history')
    def history(machine: str | None = None, limit: int = Query(100, ge=1, le=10000), source: Literal['local', 'influx'] = 'local'):
        if source == 'influx':
            if not app.state.integrations.influx:
                raise HTTPException(503, 'InfluxDB non configuré')
            try:
                return app.state.integrations.history(machine, limit)
            except Exception as error:
                raise HTTPException(503, 'InfluxDB indisponible') from error
        return app.state.service.history(machine, limit)

    @app.get('/api/config/{machine}')
    def get_config(machine: str):
        return app.state.service.thresholds(machine)

    @app.put('/api/config/{machine}')
    def config(machine: str, body: Thresholds):
        if os.getenv('TB_ENABLED') == '1':
            raise HTTPException(409, 'Modifier les attributs partagés dans ThingsBoard, source de configuration active.')
        app.state.service.set_thresholds(machine, body)
        return body

    @app.websocket('/ws')
    async def websocket(ws: WebSocket):
        await ws.accept()
        queue = asyncio.Queue(maxsize=100)
        queues.add(queue)
        async def receive_disconnect():
            while True:
                await ws.receive_text()
        receiver = asyncio.create_task(receive_disconnect())
        try:
            while not receiver.done():
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=10)
                except asyncio.TimeoutError:
                    await ws.send_json({'event': 'heartbeat'})
                else:
                    await ws.send_json(item)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            queues.discard(queue); receiver.cancel()
            with suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
                await receiver

    return app


app = create_app()
