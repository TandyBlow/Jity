"""Fetch one registered public checkpoint into D's ignored directory.

No shared Hugging Face cache, remote code, model execution or training.  Every
payload must match the immutable L2 source registration before being promoted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.request
from pathlib import Path

from lab import canonical_bytes, sha256_file

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / 'artifacts/world-components-logic/l2-model-sources-20261029.json'
M02 = 'IDEA-CCNL/Randeng-T5-77M-MultiTask-Chinese'
FILES = ('README.md', 'config.json', 'tokenizer_config.json',
         'special_tokens_map.json', 'spiece.model', 'model.safetensors')


def fetch_verified(spec: dict, destination: Path) -> dict:
    expected = spec.get('lfs_sha256') or spec.get('sha256_of_fetched_bytes')
    git_blob=spec.get('git_blob_sha1')
    if not expected and not git_blob:
        raise ValueError(f"unregistered payload identity: {spec['path']}")
    def verified(path):
        if path.stat().st_size!=spec['size_bytes']:return False
        if expected:return sha256_file(path)==expected
        raw=path.read_bytes()
        return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==git_blob
    size = spec['size_bytes']
    if destination.exists():
        if verified(destination):
            return {'path': destination.name, 'sha256': sha256_file(destination), 'bytes': size,
                    'cacheHit': True}
        raise ValueError(f'local payload differs: {destination}')
    part = destination.with_suffix(destination.suffix + '.part')
    for attempt in range(3):
        try:
            offset = part.stat().st_size if part.exists() else 0
            if offset > size:
                raise ValueError('partial file larger than registered payload')
            if offset < size:
                headers = {'User-Agent': 'Jity-D-L3-isolated-fetch/1'}
                if offset:
                    headers['Range'] = f'bytes={offset}-'
                with urllib.request.urlopen(urllib.request.Request(spec['url'], headers=headers), timeout=30) as response:
                    if offset and response.status == 206:
                        if not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-'):
                            raise ValueError('unexpected resumed byte range')
                        mode = 'ab'
                    else:
                        mode, offset = 'wb', 0
                    last_progress = offset
                    with part.open(mode) as output:
                        while chunk := response.read(1024 * 1024):
                            output.write(chunk)
                            offset += len(chunk)
                            if offset > size:
                                raise ValueError('payload exceeds registered size')
                            if offset - last_progress >= 32 * 1024 * 1024:
                                print(f"{spec['path']}: {offset}/{size} bytes", flush=True)
                                last_progress = offset
            if not verified(part):
                raise ValueError(f"payload verification failed: {spec['path']}")
            os.replace(part, destination)
            return {'path': destination.name, 'sha256': sha256_file(destination), 'bytes': size,
                    'cacheHit': False}
        except ValueError:
            raise
        except Exception as exc:
            if attempt == 2:
                raise RuntimeError(f"download failed for {spec['path']}: {type(exc).__name__}") from exc
            print(f"retry {attempt + 1}: {spec['path']} ({type(exc).__name__})", flush=True)
            time.sleep(attempt + 1)
    raise AssertionError('unreachable')


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--model',choices=('M02','M03'),default='M02');args=parser.parse_args()
    source = json.loads(REGISTRY.read_text(encoding='utf-8'))
    model = next(row for row in source['models'] if row['id'] == (M02 if args.model=='M02' else 'Qwen/Qwen2.5-0.5B-Instruct'))
    destination = ROOT / '.local/world-components-logic/models' / args.model / model['revision']
    destination.mkdir(parents=True, exist_ok=True)
    specifications = {row['path']: row for row in model['files']}
    start = time.perf_counter()
    files = [fetch_verified(specifications[name], destination / name) for name in (FILES if args.model=='M02' else tuple(specifications))]
    manifest = {
        'schema': 'jity-d-local-model-payload-v1', 'modelId': model['id'],
        'revision': model['revision'], 'sourceRegistrySha256': sha256_file(REGISTRY),
        'files': files, 'downloadWallMs': (time.perf_counter() - start) * 1000,
        'scope': 'independent payload verification; no model execution',
    }
    manifest_path=destination/'payload-manifest.json'
    if not manifest_path.exists():
        with manifest_path.open('xb') as f:f.write(canonical_bytes(manifest)+b'\n')
    print(json.dumps({'modelDirectory': str(destination), 'verifiedFiles': len(files),
                      'wallMs': manifest['downloadWallMs']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
