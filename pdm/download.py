"""Télécharge uniquement le CSV du dépôt UCI, conserve sa provenance."""
import hashlib
import io
import json
import zipfile
from pathlib import Path
from urllib.request import urlopen

URL = 'https://archive.ics.uci.edu/static/public/601/ai4i+2020+predictive+maintenance+dataset.zip'


def main():
    target = Path('data/ai4i2020.csv')
    target.parent.mkdir(exist_ok=True)
    if not target.exists():
        with urlopen(URL, timeout=60) as response:
            with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
                member = next(n for n in archive.namelist() if n.endswith('ai4i2020.csv'))
                target.write_bytes(archive.read(member))
    manifest = {'url': URL, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                'citation': 'Matzka, S. (2020). AI4I 2020 Predictive Maintenance Dataset. UCI. DOI: 10.24432/C5HS5C',
                'license': 'CC BY 4.0', 'synthetic': True}
    Path('data/provenance.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(target, manifest['sha256'])


if __name__ == '__main__':
    main()
