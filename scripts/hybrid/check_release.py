"""Fail a source-only release containing weights, secrets, LFS pointers or Windows-invalid paths."""
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[2]
WEIGHTS={'.pt','.pth','.safetensors','.gguf','.onnx','.bin','.h5','.msgpack','.ckpt'}
RESERVED={'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}

def main():
    entries=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode('utf-8').split('\0')
    errors=[]; seen={}; maximum=0; total=0; count=0
    for name in filter(None,entries):
        path=ROOT/name
        if not path.is_file():
            errors.append((name,'missing tracked file'));continue
        data=path.read_bytes(); size=len(data); total+=size; maximum=max(maximum,size);count+=1
        if size>2*1024*1024: errors.append((name,'file exceeds 2 MiB source limit'))
        if path.suffix.lower() in WEIGHTS: errors.append((name,'model/binary checkpoint extension'))
        if data.startswith(b'version https://git-lfs.github.com/spec/v1'): errors.append((name,'LFS pointer'))
        if path.name.startswith('.env') and path.name!='.env.example': errors.append((name,'local environment file'))
        if re.search(rb'sk-[A-Za-z0-9_-]{24,}',data) or (b'-----BEGIN ' + b'PRIVATE KEY-----') in data:
            # Report the filename only, never the matched credential.
            errors.append((name,'possible credential'))
        for part in name.split('/'):
            if re.search(r'[<>:"\\|?*]',part) or part.endswith((' ','.')) or part.split('.')[0].upper() in RESERVED:
                errors.append((name,'Windows-invalid path'))
        if name.casefold() in seen: errors.append((name,'case-insensitive path collision'))
        seen[name.casefold()]=name
    print(json.dumps({'trackedFiles':count,'totalBytes':total,'largestFileBytes':maximum,'errors':errors},ensure_ascii=False,indent=2))
    if errors: raise SystemExit(1)

if __name__=='__main__': main()
