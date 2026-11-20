"""Add one already-written file to the frozen input manifest, as a new revision.

The manifest is append-only in spirit: existing entries keep their bytes, the new
entry is added, and previousPinSha256 records which manifest this one replaces.
Nothing outside the named file is copied or re-hashed here.
"""
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'experiments/world-components'))

INPUTS = ROOT / 'artifacts/next-inputs'


def main():
    name = sys.argv[1]
    path = INPUTS / name
    assert path.is_file(), path
    data = path.read_bytes()
    pin_path = INPUTS / 'pin.json'
    old_bytes = pin_path.read_bytes()
    pin = json.loads(old_bytes)
    assert name not in pin['files'], 'already pinned: ' + name
    pin['files'][name] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
                          'sourcePath': str(path), 'sourceWorktree': str(ROOT),
                          'note': 'Frozen with the target-audit round; see artifacts/validation-freeze-r1/'}
    pin['previousPinSha256'] = hashlib.sha256(old_bytes).hexdigest()
    pin['version'] = 'component-inputs/3'
    pin['createdAt'] = '2026-11-05T00:00:00+00:00'
    pin_path.write_text(json.dumps(pin, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    attrs = INPUTS / '.gitattributes'
    lines = attrs.read_text(encoding='utf-8').splitlines(True)
    if 'pin.json -text\n' not in lines:
        lines.insert(0, 'pin.json -text\n')
    if name + ' -text\n' not in lines:
        lines.append(name + ' -text\n')
    attrs.write_text(''.join(lines), encoding='utf-8', newline='\n')
    from component_paths import ComponentPaths
    print(json.dumps(ComponentPaths(ROOT).verify_inputs(), ensure_ascii=False))


if __name__ == '__main__':
    main()
