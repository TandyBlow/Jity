"""Byte-level export, independent manifest coverage and deliberate mutations."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend/scripts'))
import export_world_protocol as exporter
from app.schemas.world.v2.registry import OPERATION_BY_NAME

BASE = ROOT / 'design/world-protocol/v2'


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    target = tmp_path / 'v2'
    shutil.copytree(BASE, target)
    pin = tmp_path / 'frontend/src/lib/world-engine/contract-digest.json'
    pin.parent.mkdir(parents=True)
    pin.write_bytes((ROOT / 'frontend/src/lib/world-engine/contract-digest.json').read_bytes())
    monkeypatch.setattr(exporter, 'ROOT', tmp_path)
    return target, pin


def snapshot(directory):
    return {p.relative_to(directory).as_posix(): p.read_bytes() for p in directory.rglob('*') if p.is_file()}


def test_check_is_read_only_and_reproducible(isolated):
    target, pin = isolated
    before, pin_bytes = snapshot(target), pin.read_bytes()
    exporter.run_export('v2', target, check=True)
    exporter.run_export('v2', target, check=True)
    assert snapshot(target) == before
    assert pin.read_bytes() == pin_bytes


@pytest.mark.parametrize('mutation', ['generated_crlf', 'authored_crlf', 'bom', 'response_field',
    'missing', 'extra', 'manifest', 'pin', 'pin_crlf', 'dynamic_digest'])
def test_check_rejects_drift_without_repairing_it(isolated, mutation):
    target, pin = isolated
    path = target / 'world-protocol.schema.json'
    if mutation == 'generated_crlf': path.write_bytes(path.read_bytes().replace(b'\n', b'\r\n'))
    elif mutation == 'authored_crlf':
        path = target / 'fixtures/api/checkpoint_resume/success.json'
        path.write_bytes(path.read_bytes().replace(b'\n', b'\r\n'))
    elif mutation == 'bom': path.write_bytes(b'\xef\xbb\xbf' + path.read_bytes())
    elif mutation == 'response_field':
        path = target / 'fixtures/api/checkpoint_resume/success.json'
        value = json.loads(path.read_bytes()); del value['control']
        path.write_bytes(exporter.json_bytes(value))
    elif mutation == 'missing': (target / 'canonical-vectors.json').unlink()
    elif mutation == 'extra': (target / 'fixtures/undeclared.json').write_bytes(b'{}\n')
    elif mutation == 'manifest': (target / 'manifest.json').write_bytes(b'{}\n')
    elif mutation == 'pin': pin.write_bytes(exporter.json_bytes({'protocolVersion': 2, 'contractDigest': '0' * 64}))
    elif mutation == 'pin_crlf': pin.write_bytes(pin.read_bytes().replace(b'\n', b'\r\n'))
    else:
        path = target / 'traces/T07.json'
        value = json.loads(path.read_bytes())
        key = next(iter(value['samples'][1]['expectedDigests']))
        value['samples'][1]['expectedDigests'][key] = '0' * 64
        path.write_bytes(exporter.json_bytes(value))
    before, pin_bytes = snapshot(target), pin.read_bytes()
    with pytest.raises((ValueError, FileNotFoundError)):
        exporter.run_export('v2', target, check=True)
    assert snapshot(target) == before
    assert pin.read_bytes() == pin_bytes


def test_export_never_rewrites_authored_fixtures_or_updates_pin_implicitly(isolated):
    target, pin = isolated
    path = target / 'traces/T01.json'
    path.write_bytes(path.read_bytes() + b'\n')
    authored = {n: data for n, data in snapshot(target).items() if n not in (*exporter.V2_GENERATED, 'manifest.json')}
    pin.write_bytes(b'pin is deliberately stale\n')
    exporter.run_export('v2', target)
    assert all((target / name).read_bytes() == data for name, data in authored.items())
    assert pin.read_bytes() == b'pin is deliberately stale\n'
    with pytest.raises(ValueError, match='pin'): exporter.run_export('v2', target, check=True)


def test_closed_references_are_checked(isolated):
    target, _ = isolated
    path = target / 'trace.schema.json'
    value = json.loads(path.read_bytes())
    value['properties']['steps']['items']['$ref'] = '#/$defs/DoesNotExist'
    path.write_bytes(exporter.json_bytes(value))
    with pytest.raises(ValueError, match='unresolved reference'): exporter.validate_artifacts(target)


def test_contract_digest_uses_only_fixed_interface_file_set(isolated):
    target, _ = isolated
    before = exporter.contract_digest(target)
    for name in ['canonical-vectors.json', 'fixtures/api/operations.json', 'storage-contract.sql']:
        path = target / name
        path.write_bytes(path.read_bytes() + b'\n')
    assert exporter.contract_digest(target) == before
    path = target / 'versions.json'; path.write_bytes(path.read_bytes() + b'\n')
    assert exporter.contract_digest(target) != before
    digest = hashlib.sha256()
    for name in sorted(exporter.CONTRACT_FILES):
        data = (target / name).read_bytes()
        digest.update(name.encode() + b'\0' + str(len(data)).encode() + b'\0' + data)
    assert exporter.contract_digest(target) == digest.hexdigest()


def test_default_v1_output_dir_and_check_cli_are_compatible(tmp_path):
    script = ROOT / 'backend/scripts/export_world_protocol.py'
    for args in [[], ['--version', 'v1', '--check']]:
        result = subprocess.run([sys.executable, '-X', 'utf8', str(script), '--output-dir', str(tmp_path), *args], cwd=ROOT, capture_output=True)
        assert result.returncode == 0, result.stderr.decode('utf8')
    exported = snapshot(tmp_path)
    assert len(exported) == 12
    assert all(data == (ROOT / 'design/world-protocol/v1' / name).read_bytes() for name, data in exported.items())


def test_failure_specs_have_explicit_runtime_acceptance_sites():
    value = json.loads((BASE / 'failure-cases.json').read_bytes())
    assert value['acceptance'] == 'specification_only_runtime_A3_pending'
    assert {c['id'] for c in value['cases']} == {f'FC{i:02}' for i in range(1, 33)}
    assert len({c['runtimeTest']['case'] for c in value['cases']}) == len(value['cases'])
    for case in value['cases']:
        assert case['operation'] in OPERATION_BY_NAME
        assert case['preState']['scenario'] in {f'T{i:02}' for i in range(1, 10)}
        assert case['preState']['arrange']
        assert (BASE / case['requestFixture']).is_file()
        assert (BASE / case['trace']).is_file()
        assert case['faultAt'] and case['expected']
        assert case['validationLayer'] == 'service_transaction'
        assert case['runtimeTest']['stage'] == 'A3'
        assert case['runtimeTest']['module'] == 'backend/tests/test_world_transactions.py'
        assert case['runtimeTest']['case'].startswith('test_')
        assert 'TBD' not in json.dumps(case)
