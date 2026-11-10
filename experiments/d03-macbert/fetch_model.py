"""Fetch only pinned official MacBERT inference files into an isolated directory."""
import hashlib
import json
from pathlib import Path
import requests

MODEL = 'hfl/chinese-macbert-base'
REVISION = 'a986e004d2a7f2a1c2f5a3edef4e20604a974ed1'
ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / '.local/d03-macbert/base'
FILES = ['config.json', 'pytorch_model.bin', 'tokenizer.json',
         'tokenizer_config.json', 'special_tokens_map.json', 'added_tokens.json', 'vocab.txt']

def main():
    DEST.mkdir(parents=True, exist_ok=True)
    manifest = {'model': MODEL, 'revision': REVISION, 'files': {}}
    for name in FILES:
        path = DEST / name
        url = f'https://huggingface.co/{MODEL}/resolve/{REVISION}/{name}'
        with requests.get(url, stream=True, timeout=(30, 180)) as response:
            response.raise_for_status()
            digest = hashlib.sha256()
            temporary = path.with_suffix(path.suffix + '.part')
            with temporary.open('wb') as output:
                for chunk in response.iter_content(1024 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
            temporary.replace(path)
        manifest['files'][name] = {'sha256': digest.hexdigest(), 'bytes': path.stat().st_size}
        print(name, path.stat().st_size, flush=True)
    (DEST / 'manifest.json').write_text(json.dumps(manifest, indent=2))

if __name__ == '__main__':
    main()
