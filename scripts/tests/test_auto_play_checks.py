"""CLI retries preserve the checked action, die, and timeline head."""

import argparse
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from auto_play_lib import api


def args():
    return argparse.Namespace(api_base_url='http://localhost:8000', timeout=1, retries=2,
                              model='test', style='', constraints='', seed=7)


def test_retry_reuses_one_check_and_does_not_append_result_text(monkeypatch):
    monkeypatch.setattr(api, 'api_get', Mock(return_value={'active_turn_id':42,'state':{'turn':3}}))
    generated = []
    previews = []
    def post(base, path, payload, timeout):
        if path.endswith('/check'):
            previews.append(payload.copy())
            return {'check':{'target':12}, 'option_index':1}
        generated.append(payload.copy())
        if len(generated) == 1:
            raise api.APIError('temporary failure')
        return {'ok':True}
    monkeypatch.setattr(api, 'api_post', post)
    monkeypatch.setattr(api.time, 'sleep', lambda _: None)
    assert api.generate_scene_with_retries(args(), 's', '调查档案') == {'ok':True}
    assert len(previews) == 1 and len(generated) == 2
    assert generated[0] == generated[1]
    assert generated[0]['player_action'] == '调查档案'
    assert generated[0]['timeline_node_id'] == 42
    assert generated[0]['action_check']['option_index'] == 1
    assert 1 <= generated[0]['action_check']['roll'] <= 20


def test_stale_generation_does_not_retry_against_a_new_head(monkeypatch):
    monkeypatch.setattr(api, 'prepare_generation', Mock(return_value={'timeline_node_id':42}))
    post=Mock(side_effect=api.APIError('head changed', status_code=409))
    monkeypatch.setattr(api, 'api_post', post)
    with pytest.raises(api.APIError, match='head changed'):
        api.generate_scene_with_retries(args(), 's', '调查档案')
    assert post.call_count == 1


def test_direct_action_has_no_invented_die(monkeypatch):
    monkeypatch.setattr(api, 'api_get', Mock(return_value={'active_turn_id':42,'state':{'turn':3}}))
    monkeypatch.setattr(api, 'api_post', Mock(return_value={'check':None,'option_index':0}))
    payload = api.prepare_generation(args(),'s','等待')
    assert 'action_check' not in payload
    assert payload['player_action'] == '等待'
    assert payload['option_index'] == 0
