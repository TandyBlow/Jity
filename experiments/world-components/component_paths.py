"""Paths for independent component runs; no inference or filesystem writes on import."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

WORKTREE = Path(__file__).resolve().parents[2]


class ComponentPaths:
    def __init__(self, worktree=WORKTREE, input_root=None, output_root=None):
        self.worktree = Path(worktree).resolve()
        self.inputs = self._inside(input_root or os.environ.get('N4_INPUT_ROOT')
                                   or 'artifacts/next-inputs')
        self.outputs = self._inside(output_root or os.environ.get('N4_OUTPUT_ROOT')
                                    or 'artifacts/next-runs')
        if self.outputs == self.worktree or self.outputs.is_relative_to(self.inputs) or self.inputs.is_relative_to(self.outputs):
            raise ValueError('Input and output directories must be separate; output cannot be the worktree root')

    def _inside(self, value):
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = self.worktree / path
        path = path.resolve()
        if not path.is_relative_to(self.worktree):
            raise ValueError(f'Path escapes this worktree: {path}')
        return path

    def output(self, relative=''):
        """Resolve before any mkdir/write; reject ../, symlinks and junction escapes."""
        path = self._inside(self.outputs / relative)
        if not path.is_relative_to(self.outputs) or path.is_relative_to(self.inputs):
            raise ValueError(f'Output must stay under {self.outputs}: {path}')
        pin = self.inputs / 'pin.json'
        if pin.is_file():
            for record in self._pin()['files'].values():
                for copy in record.get('historicalCopies', []):
                    archived = self._inside(copy['path'])
                    if path.is_relative_to(archived) or archived.is_relative_to(path):
                        raise ValueError(f'Output overlaps immutable historical evidence: {archived}')
        return path

    def _pin(self):
        """Parsed pin.json; the cache key is the manifest's own bytes.

        A timestamp/size key would miss a same-size rewrite that keeps the mtime,
        so freshness is decided by hashing the manifest (196 KB, ~1 ms).
        """
        pin = self.inputs / 'pin.json'
        if not pin.is_file():
            raise FileNotFoundError(f'Missing frozen input manifest: {pin}')
        raw = pin.read_bytes()
        key = hashlib.sha256(raw).hexdigest()
        cached = getattr(self, '_pin_cache', None)
        if cached is not None and cached[0] == key:
            return cached[1]
        manifest = json.loads(raw.decode('utf-8'))
        self._pin_cache = (key, manifest)
        return manifest

    def _index(self):
        """Lookup tables for pin records, rebuilt only when pin.json changes.

        Only the manifest structure is cached: every call still re-reads and
        re-hashes the pinned bytes and their historical copies.
        """
        manifest = self._pin()
        key = self._pin_cache[0]
        cached = getattr(self, '_index_cache', None)
        if cached is not None and cached[0] == key:
            return cached[1]
        exact, under = {}, {}
        for name, record in manifest['files'].items():
            path = self.inputs / name
            exact.setdefault(path, []).append((name, record))
            for directory in path.parents:
                if not directory.is_relative_to(self.inputs):
                    break
                under.setdefault(directory, []).append((name, record))
        index = (exact, under)
        self._index_cache = (key, index)
        return index

    def input(self, relative):
        path = self._inside(self.inputs / relative)
        if not path.is_relative_to(self.inputs):
            raise ValueError(f'Input escapes frozen input directory: {path}')
        if not path.exists():
            raise FileNotFoundError(f'Missing frozen input: {path}')
        exact, under = self._index()
        selected = (exact.get(path) or []) + (under.get(path) or [])
        if not selected:
            raise ValueError(f'Input is not recorded in pin.json: {path}')
        for name, record in selected:
            source = self._inside(self.inputs / name)
            if not source.is_relative_to(self.inputs) or not source.is_file():
                raise FileNotFoundError(f'Missing pinned input: {name}')
            actual = hashlib.sha256(source.read_bytes()).hexdigest()
            if actual != record['sha256']:
                raise ValueError(f'Frozen input bytes changed: {name} ({actual} != {record["sha256"]})')
            for copy in record.get('historicalCopies', []):
                archived = self._inside(copy['path'])
                if not archived.is_file():
                    raise FileNotFoundError(f'Missing historical evidence copy: {archived}')
                if hashlib.sha256(archived.read_bytes()).hexdigest() != record['sha256']:
                    raise ValueError(f'Historical evidence drifted from pinned input: {archived}')
        return path

    def verify_inputs(self):
        records = self._pin()['files']
        for name in records:
            self.input(name)
        return {'files': len(records), 'inputRoot': str(self.inputs), 'verified': True,
                'historicalCopiesVerified': sum(len(r.get('historicalCopies', [])) for r in records.values())}

    def model(self, explicit=None):
        """Shared models are read-only resources; an explicit location is required."""
        value = explicit or os.environ.get('N4_MODEL_DIR')
        if not value:
            raise ValueError('Set --model/--ckpt or N4_MODEL_DIR to a local, read-only model directory')
        path = Path(value).expanduser().resolve()
        for name in ('config.json', 'spiece.model', 'model.safetensors'):
            if not (path / name).is_file():
                raise FileNotFoundError(f'Missing model file: {path / name}')
        return path

    def checkpoint(self, explicit):
        """Training destinations are explicit and remain inside this run's output tree."""
        if not explicit:
            raise ValueError('Training requires an explicit --out/--save-ckpt directory')
        path = self.output(explicit)
        model = os.environ.get('N4_MODEL_DIR')
        if model and (path.is_relative_to(Path(model).resolve()) or Path(model).resolve().is_relative_to(path)):
            raise ValueError('Training output overlaps the shared model directory')
        return path


PATHS = ComponentPaths()


if __name__ == '__main__':
    print(json.dumps(PATHS.verify_inputs(), ensure_ascii=False))
