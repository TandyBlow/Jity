"""Independent fixed bytes/hashes and projection exclusions, not apply answers."""
import copy
import hashlib
import json
from pathlib import Path

import pytest
from app.schemas.world.canonical import canonical_bytes, canonical_digest, parse_json
from app.schemas.world.v2 import SCHEMA_MODELS
from app.schemas.world.v2.projections import prefix_projection, request_projection

ROOT=Path(__file__).resolve().parents[2]/'design/world-protocol/v2'
VECTORS=json.loads((ROOT/'canonical-vectors.json').read_text(encoding='utf-8'))
MODELS={m.__name__:m for m in SCHEMA_MODELS}


@pytest.mark.parametrize('vector',VECTORS['vectors'],ids=lambda v:v['id'])
def test_fixed_canonical_vectors(vector):
    value=parse_json(vector['inputJson'])
    if vector['projectionKind']=='members':
        ids=value['memberIds']
        if len(ids)!=len(set(ids)):raise ValueError('duplicate member')
        value['memberIds']=sorted(ids)
    elif vector['projectionKind']=='prefix':
        value=prefix_projection(value['worldId'],value,value.get('timeScanCandidates'))
    elif vector.get('schema'):
        value=MODELS[vector['schema']].model_validate(value).model_dump(mode='json')
    raw=canonical_bytes(value)
    assert raw.decode()==vector['expectedCanonical']
    assert raw.hex()==vector['expectedUtf8Hex']
    assert hashlib.sha256(raw).hexdigest()==vector['expectedSha256']


def test_member_set_equivalence_and_outer_order_difference():
    values={v['id']:v['expectedSha256'] for v in VECTORS['vectors']}
    assert values['member_set_cd']==values['member_set_dc']
    assert values['outer_ab']!=values['outer_ba']
    assert values['full_prefix']==values['prefix_control_metadata_excluded']
    assert values['full_prefix']!=values['prefix_time_changed']


@pytest.mark.parametrize('raw',VECTORS['rejectedJson'])
def test_invalid_encoding_inputs(raw):
    with pytest.raises((ValueError,UnicodeError)):parse_json(raw)


def test_content_hash_preserves_original_utf8_and_line_endings():
    for v in VECTORS['rawContent']:
        raw=v['text'].encode('utf-8')
        assert raw.hex()==v['utf8Hex'] and hashlib.sha256(raw).hexdigest()==v['sha256']
        assert hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()!=v['sha256']


def test_request_hash_projection_includes_operation_and_all_normalized_bindings():
    request=json.loads((ROOT/'fixtures/api/checkpoint_pause/request.json').read_text(encoding='utf-8'))
    first=canonical_digest(request_projection('checkpoint_pause',request))
    changed={**request,'expectedCheckpointRevision':request['expectedCheckpointRevision']+1}
    assert first!=canonical_digest(request_projection('checkpoint_pause',changed))
    with pytest.raises(ValueError):request_projection('preview_point',{})
