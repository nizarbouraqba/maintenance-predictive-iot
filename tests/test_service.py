from datetime import datetime, timezone
import json
import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pdm.api import create_app
from pdm.schema import Telemetry, Thresholds
from pdm.service import Conflict, Service


class FakePipeline:
    def predict_proba(self, frame):
        score = frame.iloc[0].torque_nm / 100
        return np.array([[1-score, score]])


ARTIFACT = {'pipeline': FakePipeline(), 'version': 'test-only'}


def sample(mid='m1', score=.8, machine='SIM_AI4I'):
    return Telemetry(message_id=mid, machine_id=machine, sent_at=datetime.now(timezone.utc),
        source_row=1, type='L', air_temperature_k=300, process_temperature_k=310,
        rotational_speed_rpm=1500, torque_nm=score*100, tool_wear_min=100)


@pytest.fixture
def service(tmp_path):
    instance = Service(ARTIFACT, str(tmp_path/'db.sqlite'), ['influx'])
    yield instance
    instance.close()


def test_strict_threshold_and_hysteresis(service):
    assert service.ingest(sample('a', .7))[0]['status'] == 'NORMAL'
    assert service.ingest(sample('b', .71))[0]['status'] == 'CRITICAL'
    for mid in ['c','d']:
        assert service.ingest(sample(mid, .4))[0]['status'] == 'CRITICAL'
    assert service.ingest(sample('e', .5))[0]['low_count'] == 0
    for mid in ['f','g']:
        assert service.ingest(sample(mid, .4))[0]['status'] == 'CRITICAL'
    assert service.ingest(sample('h', .4))[0]['status'] == 'NORMAL'


def test_dedup_conflict_and_outbox(service):
    message = sample()
    first, duplicate = service.ingest(message)
    second, duplicate = service.ingest(message)
    assert duplicate and first == second
    assert service.stats() == {'events': 1, 'pending_deliveries': 1}
    with pytest.raises(Conflict):
        service.ingest(message.model_copy(update={'torque_nm': 1}))
    service.delivered('m1', 'influx')
    assert not service.pending()


def test_dedup_survives_restart(tmp_path):
    database = str(tmp_path/'db.sqlite'); message = sample()
    first = Service(ARTIFACT, database); first.ingest(message); first.close()
    second = Service(ARTIFACT, database)
    assert second.ingest(message)[1]
    assert second.ingest(sample('low', .4))[0]['status'] == 'CRITICAL'
    second.close()


def test_dynamic_thresholds_and_machine_isolation(service):
    service.set_thresholds('SIM_AI4I', Thresholds(critical=.9))
    assert service.ingest(sample())[0]['status'] == 'NORMAL'
    assert service.ingest(sample('other', .8, 'M02'))[0]['status'] == 'CRITICAL'
    assert len(service.history('M02')) == 1


@pytest.mark.parametrize('update', [
    {'torque_nm': float('nan')}, {'air_temperature_k': -2}, {'type': 'X'},
    {'sent_at': '2026-01-01T12:00:00'}, {'TWF': 1}, {'rotational_speed_rpm': -1}])
def test_invalid_telemetry(update):
    data = sample().model_dump(); data.update(update)
    with pytest.raises(ValidationError):
        Telemetry.model_validate(data)


def test_invalid_thresholds():
    with pytest.raises(ValidationError):
        Thresholds(critical=.4, clear=.5)


def test_rest_websocket_and_history(tmp_path, monkeypatch):
    for key in ['INFLUX_URL', 'TB_ENABLED']:
        monkeypatch.delenv(key, raising=False)
    with TestClient(create_app(ARTIFACT, str(tmp_path/'db.sqlite'))) as api:
        with api.websocket_connect('/ws') as ws:
            payload = sample().model_dump(mode='json')
            assert api.post('/api/telemetry', json=payload).status_code == 200
            assert ws.receive_json()['message_id'] == 'm1'
            assert api.post('/api/telemetry', json=payload).json()['duplicate']
        assert len(api.get('/api/history').json()) == 1
        assert api.get('/api/history?source=influx').status_code == 503
        assert api.get('/api/history?limit=-1').status_code == 422
        assert api.put('/api/config/SIM_AI4I', json={'critical': .4, 'clear': .5}).status_code == 422
        assert api.post('/api/telemetry', json={**payload,'torque_nm': 1}).status_code == 409
        assert api.get('/health').json()['events'] == 1


def test_artifacts_and_splits():
    import joblib
    import pandas as pd
    from pdm.schema import FEATURES
    frames = {n: pd.read_csv(f'data/{n}.csv') for n in ['train','validation','test']}
    ids = [set(frame.UDI) for frame in frames.values()]
    assert sum(map(len,ids)) == 10000
    for i in range(3):
        for j in range(i+1,3):
            assert ids[i].isdisjoint(ids[j])
    artifact = joblib.load('models/random_forest.joblib')
    assert artifact['features'] == FEATURES
    scores = artifact['pipeline'].predict_proba(frames['test'][FEATURES].head())[:,1]
    assert np.isfinite(scores).all() and ((scores >= 0) & (scores <= 1)).all()
