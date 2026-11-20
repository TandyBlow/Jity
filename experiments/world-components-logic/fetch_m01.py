"""Fetch the already-registered M01 into D's private ignored payload path."""
import json
from pathlib import Path

from fetch_model import fetch_verified, REGISTRY, ROOT
from lab import canonical_bytes, sha256_file


def main():
    registry = json.loads(REGISTRY.read_text(encoding='utf-8'))
    model = next(m for m in registry['models'] if m['id'] == 'hfl/minirbt-h256')
    destination = ROOT/'.local/world-components-logic/models/M01'/model['revision']
    destination.mkdir(parents=True, exist_ok=True)
    rows = [fetch_verified(f, destination/f['path']) for f in model['files']]
    value = {'schema': 'jity-d-local-model-payload-v1', 'modelId': model['id'],
             'revision': model['revision'], 'sourceRegistrySha256': sha256_file(REGISTRY),
             'files': rows, 'scope': 'file_verification_only_no_model_execution'}
    path = destination/'payload-manifest.json'
    if not path.exists():
        with path.open('xb') as handle: handle.write(canonical_bytes(value)+b'\n')
    print(json.dumps({'directory': str(destination), 'verifiedFiles': len(rows)}))


if __name__ == '__main__': main()
