"""Acquire the pinned public Qwen source into D's isolated resource directory.

Only original Qwen assets; the browser ONNX baseline is a separate registration.
Reuse the existing verified streaming downloader, never a shared model cache.
"""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

from fetch_model import fetch_verified
from lab import sha256_file
from run_pilot import exclusive, timestamp

ROOT=Path(__file__).resolve().parents[2]
MODEL='Qwen/Qwen3-0.6B'
REVISION='c1899de289a04d12100db370d81485cdf75e47ca'
FILES=('LICENSE','README.md','config.json','generation_config.json','merges.txt',
       'tokenizer.json','tokenizer_config.json','vocab.json','model.safetensors')
ART=ROOT/'artifacts/world-components-logic/qwen-short'
DIRECTORY=ROOT/'.local/world-components-logic/qwen/source'/REVISION


def acquire():
    ART.mkdir(parents=True,exist_ok=True);DIRECTORY.mkdir(parents=True,exist_ok=True)
    registry_path=ART/'qwen3-06b-source-registration.json'
    if registry_path.exists():registry=json.loads(registry_path.read_text())
    else:
        url=f'https://huggingface.co/api/models/{MODEL}/revision/{REVISION}?blobs=true'
        with urllib.request.urlopen(url,timeout=30) as response:metadata=json.load(response)
        if metadata['sha']!=REVISION or metadata.get('cardData',{}).get('license')!='apache-2.0':
            raise ValueError('unexpected source revision/license')
        siblings={f['rfilename']:f for f in metadata['siblings']};specs=[]
        for name in FILES:
            row=siblings[name];lfs=row.get('lfs',{})
            specs.append({'path':name,'size_bytes':row['size'],'lfs_sha256':lfs.get('sha256'),
                          'git_blob_sha1':None if lfs else row['blobId'],
                          'url':f'https://huggingface.co/{MODEL}/resolve/{REVISION}/{name}'})
        registry={'schema':'jity-qwen-source-registration-v1','registeredAt':timestamp(),
                  'modelId':MODEL,'revision':REVISION,'license':'apache-2.0','sourceApi':url,
                  'files':specs,'paidServices':False,'modelExecutions':0}
        exclusive(registry_path,registry)
    if registry['modelId']!=MODEL or registry['revision']!=REVISION:raise ValueError('source identity drift')
    started=time.perf_counter();files=[]
    for spec in registry['files']:
        files.append(fetch_verified(spec,DIRECTORY/spec['path']))
    manifest={'schema':'jity-qwen-source-payload-v1','modelId':MODEL,'revision':REVISION,
              'license':'apache-2.0','directory':str(DIRECTORY),'registry':str(registry_path),
              'registrySha256':sha256_file(registry_path),'files':files,
              'downloadWallMs':(time.perf_counter()-started)*1000,'modelExecutions':0,
              'sharedCacheModified':False}
    destination=ART/'qwen3-06b-source-payload.json'
    if not destination.exists():exclusive(destination,manifest)
    else:
        old=json.loads(destination.read_text())
        if [(x['path'],x['sha256']) for x in old['files']]!=[(x['path'],x['sha256']) for x in files]:
            raise ValueError('source payload changed')
    print(json.dumps({'directory':str(DIRECTORY),'files':len(files),'manifest':str(destination)}))


if __name__=='__main__':acquire()
