import json
from types import SimpleNamespace
import httpx
import pytest
from pdm.integrations import Integrations
from pdm.schema import Thresholds


def test_shared_attributes_sync_and_validation(tmp_path, monkeypatch):
    monkeypatch.delenv('INFLUX_URL', raising=False)
    path = tmp_path/'tokens.json'
    path.write_text(json.dumps({'SIM_AI4I': 'test-token'}))
    monkeypatch.setenv('TB_TOKENS_PATH', str(path))
    integration = Integrations(); integration.http.close()
    settings = {'value': Thresholds()}
    service = SimpleNamespace(thresholds=lambda m: settings['value'],
        set_thresholds=lambda m,t: settings.update(value=t))
    integration.http = httpx.Client(transport=httpx.MockTransport(lambda request:
        httpx.Response(200, json={'shared': {'seuil_critique': .85, 'seuil_retour': .45, 'clear_count': 4}})))
    integration.sync_thresholds(service)
    assert settings['value'].critical == .85 and settings['value'].clear_count == 4
    integration.http.close()
    integration.http = httpx.Client(transport=httpx.MockTransport(lambda request:
        httpx.Response(200, json={'shared': {'seuil_critique': .3, 'seuil_retour': .5}})))
    with pytest.raises(ValueError):
        integration.sync_thresholds(service)
    assert settings['value'].critical == .85
    integration.close()


def test_thingsboard_timestamp_and_retry_payload(tmp_path, monkeypatch):
    monkeypatch.delenv('INFLUX_URL', raising=False)
    path = tmp_path/'tokens.json'; path.write_text('{"SIM_AI4I":"test-token"}')
    monkeypatch.setenv('TB_TOKENS_PATH', str(path))
    integration = Integrations(); integration.http.close(); calls=[]
    def receive(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200)
    integration.http = httpx.Client(transport=httpx.MockTransport(receive))
    result = {'machine_id':'SIM_AI4I','received_at':'2026-01-01T00:00:00+00:00', 'measured_at':None,'panne_probable':.8,'seuil_critique':.7}
    integration.send('thingsboard',result); integration.send('thingsboard',result)
    assert calls[0] == calls[1]
    assert calls[0]['ts'] == 1767225600000
    assert 'measured_at' not in calls[0]['values']
    integration.close()
