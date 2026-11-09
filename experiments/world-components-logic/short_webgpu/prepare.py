"""Prepare isolated, byte-verified browser assets; never load a model.

The original ONNX conversion is an untrained-for-Jity baseline. Fine-tuned
exports use register_local with explicit training/export provenance instead.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(BASE.parent))
from lab import canonical_bytes, sha256_file
from run_pilot import digest

REVISION = '58ca03a5e7b354b480b1a82b34bde8dc7b854cc0'
MODEL_ID = 'onnx-community/Qwen3-0.6B-ONNX'
RUNTIME_VERSION = '3.8.1'
FILES = ('config.json', 'generation_config.json', 'tokenizer.json',
         'tokenizer_config.json', 'special_tokens_map.json', 'chat_template.jinja',
         'onnx/model_q4f16.onnx')
LOCAL = ROOT / '.local/world-components-logic/webgpu'


def write_new(path, value):
    raw = canonical_bytes(value) + b'\n'
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError('immutable_manifest_already_exists:' + str(path))
    else:
        with path.open('xb') as stream:
            stream.write(raw)


def fetch(url, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['curl', '--fail', '--location', '--silent', '--show-error',
                    '--retry', '3', '--retry-all-errors', '--connect-timeout', '20',
                    '--max-time', '1800', url, '-o', str(path)], check=True)


def fetch_source_file(row, destination):
    target = destination / row['path']
    def matches(path):
        if not path.exists() or path.stat().st_size != row['size']:
            return False
        if row.get('lfs'):
            return sha256_file(path) == row['lfs']['oid']
        raw = path.read_bytes()
        return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == row['oid']
    if target.exists() and not matches(target):
        raise ValueError('existing_model_bytes_differ:' + str(target))
    if not target.exists():
        part = target.with_suffix(target.suffix + '.part')
        fetch(f'https://huggingface.co/{MODEL_ID}/resolve/{REVISION}/{row["path"]}', part)
        if not matches(part):
            raise ValueError('download_identity_mismatch:' + row['path'])
        part.replace(target)
    return {'path': row['path'], 'size': target.stat().st_size,
            'sha256': sha256_file(target), 'sourceGitOid': row['oid'],
            'sourceLfsSha256': row.get('lfs', {}).get('oid')}


def install_runtime(destination=LOCAL / 'runtime-r2'):
    destination.mkdir(parents=True, exist_ok=True)
    for name in ('package.json', 'package-lock.json'):
        src, dst = BASE / name, destination / name
        if dst.exists() and dst.read_bytes() != src.read_bytes():
            raise ValueError('runtime_lock_changed_use_new_directory')
        if not dst.exists():
            shutil.copyfile(src, dst)
    subprocess.run(['npm', 'ci', '--prefix', str(destination), '--ignore-scripts',
                    '--no-audit', '--no-fund'], check=True)
    package = destination / 'node_modules/@huggingface/transformers'
    if json.loads((package / 'package.json').read_text())['version'] != RUNTIME_VERSION:
        raise ValueError('runtime_version_mismatch')
    # The npm web distribution has bare onnxruntime imports. Bundle the exact
    # locked graph instead of passing unresolved package specifiers to browsers.
    if not (destination / 'built/metafile.json').exists():
        subprocess.run(['node', str(BASE / 'bundle.mjs'), str(destination)], check=True)
    metadata = json.loads((destination / 'built/metafile.json').read_text())
    inputs = [{'path': name, 'sha256': sha256_file(destination / name),
               'size': (destination / name).stat().st_size} for name in sorted(metadata['inputs'])]
    # Only these browser files are served; Node native binaries are never loaded.
    sources = {'transformers.web.min.js': destination / 'built/transformers.web.min.js',
               'LICENSE': package / 'LICENSE'}
    ort = destination / 'node_modules/onnxruntime-web'
    for path in (ort / 'dist').glob('ort-wasm-simd-threaded.jsep.*'):
        sources['ort/' + path.name] = path
    sources['ort/package.json'] = ort / 'package.json'
    served = destination / 'served'
    records = []
    for name, source in sorted(sources.items()):
        target = served / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and sha256_file(target) != sha256_file(source):
            raise ValueError('served_runtime_bytes_changed')
        if not target.exists():
            shutil.copyfile(source, target)
        records.append({'path': name, 'sha256': sha256_file(target), 'size': target.stat().st_size})
    manifest = {'schema': 'jity-d-webgpu-runtime-v1', 'package': '@huggingface/transformers',
                'version': RUNTIME_VERSION, 'lockSha256': sha256_file(BASE / 'package-lock.json'),
                'ortVersion': json.loads((ort / 'package.json').read_text())['version'],
                'directory': str(served.resolve()), 'files': records,
                'license': 'Apache-2.0', 'source': 'https://github.com/huggingface/transformers.js/tree/3.8.1'}
    manifest['build'] = {'tool': 'esbuild', 'version': '0.25.5', 'platform': 'browser', 'format': 'esm',
                         'sourceSha256': sha256_file(BASE / 'bundle.mjs'),
                         'metafileSha256': sha256_file(destination / 'built/metafile.json'), 'inputs': inputs}
    manifest.update(ortLicense='MIT', ortLicenseSource='https://github.com/microsoft/onnxruntime/blob/89f8206ba4/LICENSE')
    manifest['identity'] = digest({k: v for k, v in manifest.items() if k != 'directory'})
    write_new(destination / 'runtime-manifest.json', manifest)
    return destination / 'runtime-manifest.json'


def register_local(directory, *, provenance, out):
    """Register exact local export bytes; training identity is never inferred."""
    directory = Path(directory).resolve()
    config = json.loads((directory / 'config.json').read_text())
    if config.get('model_type') != 'qwen3':
        raise ValueError('only_qwen3_export_supported')
    if not isinstance(provenance, dict) or not provenance.get('sourceModel') or not provenance.get('capability'):
        raise ValueError('explicit_source_and_capability_required')
    selected = list(FILES)
    # External data is allowed only under the exact ONNX model name.
    selected.extend(p.relative_to(directory).as_posix() for p in sorted((directory / 'onnx').glob('model_q4f16.onnx_data*')))
    records = []
    for name in selected:
        path = directory / name
        if name == 'chat_template.jinja' and not path.exists():
            continue  # tokenizer_config's frozen template remains mandatory.
        records.append({'path': name, 'size': path.stat().st_size, 'sha256': sha256_file(path)})
    token = json.loads((directory / 'tokenizer_config.json').read_text())
    if not token.get('chat_template'):
        raise ValueError('missing_frozen_chat_template')
    generation = json.loads((directory / 'generation_config.json').read_text())
    eos = generation.get('eos_token_id', config.get('eos_token_id'))
    eos = eos if isinstance(eos, list) else [eos]
    if not eos or any(type(i) is not int or i < 0 for i in eos):
        raise ValueError('missing_eos_identity')
    manifest = {'schema': 'jity-d-webgpu-model-v1', 'directory': str(directory),
                'modelType': 'qwen3', 'dtype': 'q4f16', 'device': 'webgpu',
                'maxContextTokens': config['max_position_embeddings'], 'eosTokenIds': eos,
                'files': records, 'provenance': provenance}
    from short_webgpu import validate_model_qualification
    validate_model_qualification(manifest)
    manifest['identity'] = digest({k: v for k, v in manifest.items() if k != 'directory'})
    write_new(Path(out), manifest)
    return Path(out)


def prepare_baseline():
    LOCAL.mkdir(parents=True, exist_ok=True)
    metadata = LOCAL / ('source-tree-' + REVISION + '.json')
    if not metadata.exists():
        fetch(f'https://huggingface.co/api/models/{MODEL_ID}/tree/{REVISION}?recursive=true&expand=false', metadata)
    tree = {r['path']: r for r in json.loads(metadata.read_text()) if r['type'] == 'file'}
    selected = list(FILES) + [p for p in tree if p.startswith('onnx/model_q4f16.onnx_data')]
    destination = LOCAL / 'models' / REVISION
    source_files = [fetch_source_file(tree[name], destination) for name in selected]
    out = destination / 'model-manifest.json'
    register_local(destination, provenance={
        'sourceModel': MODEL_ID, 'sourceRevision': REVISION,
        'originalModel': 'Qwen/Qwen3-0.6B', 'sourceFiles': source_files,
        'sourceTreeSha256': sha256_file(metadata), 'capability': 'pretrained_baseline_unvalidated_for_Jity',
        'trainingSteps': 0, 'license': 'Apache-2.0',
        'licenseSource': 'https://huggingface.co/Qwen/Qwen3-0.6B',
        'conversionSource': f'https://huggingface.co/{MODEL_ID}/tree/{REVISION}'}, out=out)
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', action='store_true')
    parser.add_argument('--model', action='store_true')
    parser.add_argument('--runtime-directory', type=Path, default=LOCAL / 'runtime-r2')
    args = parser.parse_args()
    if args.runtime:
        print(install_runtime(args.runtime_directory), flush=True)
    if args.model:
        print(prepare_baseline(), flush=True)
