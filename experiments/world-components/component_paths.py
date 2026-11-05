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
        return path

    def _pin(self):
        pin = self.inputs / 'pin.json'
        if not pin.is_file():
            raise FileNotFoundError(f'Missing frozen input manifest: {pin}')
        return json.loads(pin.read_text(encoding='utf-8'))

    def input(self, relative):
        path = self._inside(self.inputs / relative)
        if not path.is_relative_to(self.inputs):
            raise ValueError(f'Input escapes frozen input directory: {path}')
        if not path.exists():
            raise FileNotFoundError(f'Missing frozen input: {path}')
        records = self._pin()['files']
        selected = [(name, record) for name, record in records.items()
                    if self.inputs / name == path or (self.inputs / name).is_relative_to(path)]
        if not selected:
            raise ValueError(f'Input is not recorded in pin.json: {path}')
        for name, record in selected:
            source = self._inside(self.inputs / name)
            if not source.is_relative_to(self.inputs) or not source.is_file():
                raise FileNotFoundError(f'Missing pinned input: {name}')
            actual = hashlib.sha256(source.read_bytes()).hexdigest()
            if actual != record['sha256']:
                raise ValueError(f'Frozen input bytes changed: {name} ({actual} != {record["sha256"]})')
        return path

    def verify_inputs(self):
        records = self._pin()['files']
        for name in records:
            self.input(name)
        return {'files': len(records), 'inputRoot': str(self.inputs), 'verified': True}

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
