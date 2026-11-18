"""Crée une chaîne dédiée, un profil et SIM_AI4I dans une instance locale de démonstration."""
import argparse
import json
import os
from pathlib import Path
import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default=os.getenv('TB_URL', 'http://localhost:8080'))
    parser.add_argument('--username', default='tenant@thingsboard.org')
    parser.add_argument('--password', default=os.getenv('TB_PASSWORD', 'tenant'))
    args = parser.parse_args()
    with httpx.Client(base_url=args.url, timeout=30) as http:
        def request(method, url, **kwargs):
            result = http.request(method, url, **kwargs); result.raise_for_status()
            return result.json() if result.content else None
        token = request('POST', '/api/auth/login', json={'username': args.username, 'password': args.password})['token']
        http.headers['X-Authorization'] = 'Bearer ' + token
        # Réexécution : réutiliser les objets dédiés par nom ; ne touche pas la chaîne racine globale.
        name = 'Projet 11 - Maintenance AI4I'
        chains = request('GET', '/api/ruleChains', params={'pageSize': 100, 'page': 0, 'type': 'CORE', 'textSearch': name})['data']
        chain = next((c for c in chains if c['name'] == name), None)
        if chain is None:
            export = json.loads(Path('thingsboard/alarm_rule_chain.json').read_text(encoding='utf-8'))
            chain = request('POST', '/api/ruleChain', json=export['ruleChain'])
            metadata = export['metadata']; metadata['ruleChainId'] = chain['id']
            request('POST', '/api/ruleChain/metadata', json=metadata)
        profiles = request('GET', '/api/deviceProfiles', params={'pageSize': 100, 'page': 0, 'textSearch': name})['data']
        profile = next((p for p in profiles if p['name'] == name), None)
        if profile is None:
            profile = request('POST', '/api/deviceProfile', json={'name': name, 'type': 'DEFAULT',
                'transportType': 'DEFAULT', 'provisionType': 'DISABLED', 'default': False,
                'defaultRuleChainId': chain['id'], 'profileData': {'configuration': {'type': 'DEFAULT'},
                    'transportConfiguration': {'type': 'DEFAULT'}, 'alarms': []}})
        response = http.get('/api/tenant/devices', params={'deviceName': 'SIM_AI4I'})
        if response.status_code == 404:
            device = request('POST', '/api/device', json={'name': 'SIM_AI4I', 'type': name, 'deviceProfileId': profile['id']})
        else:
            response.raise_for_status(); device = response.json()
            device['deviceProfileId'] = profile['id']
            device = request('POST', '/api/device', json=device)
        device_id = device['id']['id']
        request('POST', f'/api/plugins/telemetry/DEVICE/{device_id}/SHARED_SCOPE', json={
            'seuil_critique': .7, 'seuil_retour': .5, 'clear_count': 3})
        credentials = request('GET', f'/api/device/{device_id}/credentials')
        Path('runtime').mkdir(exist_ok=True)
        Path('runtime/tb_devices.json').write_text(json.dumps({'SIM_AI4I': credentials['credentialsId']}), encoding='utf-8')
        Path('runtime/tb_setup.json').write_text(json.dumps({'device_id': device_id, 'rule_chain_id': chain['id']['id']}), encoding='utf-8')
        print('SIM_AI4I provisionné ; seuil 0,7 ; token enregistré dans runtime/tb_devices.json.')


if __name__ == '__main__':
    main()
