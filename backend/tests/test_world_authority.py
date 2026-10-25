"""Independent server-clock and credential boundary cases for A3 authority."""
import copy
from types import SimpleNamespace

import pytest

from app.schemas.world.contracts import MAX_SAFE
from app.schemas.world.v2.requests import AcquireLeaseData, NarrationClaimData
from app.services.world import authority
from app.services.world.control import ServiceRefusal


class ClockStore:
    def __init__(self):
        self.now = 1_792_617_600_000

    def clock_milli(self):
        return self.now


@pytest.fixture()
def current():
    store = ClockStore()
    record = {
        'headPointId': 'root_1', 'lease': None,
        'narrations': {'root_1': {'status': 'pending', 'text': None,
                                 'generation': 1, 'claim': None}},
        'control': {'phase': 'select_actor', 'paused': False, 'revision': 7,
                    'gate': {'status': 'none', 'generation': None,
                             'issuedAtEpochMilli': None, 'expiresAtEpochMilli': None}},
    }
    authority.initialize_world(store, record)
    return store, record


def lease_request(record, **fields):
    lease = record['lease']
    return SimpleNamespace(leaseToken=lease['leaseToken'], fenceEpoch=lease['fenceEpoch'], **fields)


def claim_request(record, mode='head', point_id=None, **fields):
    point_id = point_id or record['headPointId']
    entry = record['narrations'][point_id]
    claim = entry.get('claim') or {}
    body = dict(mode=mode, pointId=point_id, claimToken=claim.get('claimToken'),
                generation=entry['generation'], issuedAtEpochMilli=claim.get('issuedAtEpochMilli'))
    if mode == 'head':
        body.update(leaseToken=record['lease']['leaseToken'],
                    fenceEpoch=record['lease']['fenceEpoch'])
    body.update(fields)
    return SimpleNamespace(**body)


def assert_refusal(code, call):
    with pytest.raises(ServiceRefusal) as caught:
        call()
    assert caught.value.code == code
    return caught.value


def test_creation_issues_root_claim_and_default_separate_lifetimes(current):
    store, record = current
    claim = record['narrations']['root_1']['claim']
    assert record['lease']['expiresAtEpochMilli'] == store.now + 120_000
    assert claim['expiresAtEpochMilli'] == store.now + 180_000
    assert claim['mode'] == 'head' and claim['generation'] == claim['fenceEpoch'] == 1
    assert record['control']['gate']['generation'] == 1
    assert record['control']['revision'] == 7
    NarrationClaimData.model_validate({'pointId': 'root_1', **claim})


def test_credentials_are_fresh_random_values_not_holder_or_point_ids(current):
    store, record = current
    first = (record['lease']['leaseToken'], record['narrations']['root_1']['claim']['claimToken'])
    authority.initialize_world(store, record)
    second = (record['lease']['leaseToken'], record['narrations']['root_1']['claim']['claimToken'])
    assert len(set(first + second)) == 4
    assert all(len(token.split('_')[1]) == 64 for token in first + second)


def test_live_lease_cannot_be_acquired_even_by_same_holder(current):
    store, record = current
    before = copy.deepcopy(record)
    error = assert_refusal('lease_invalid', lambda: authority.handle_lease_acquire(
        store, record, SimpleNamespace(holderId='holder_1')))
    assert error.details == {'reason': 'lease_held'}
    assert record == before


@pytest.mark.parametrize('operation', ['check_lease', 'handle_lease_renew', 'handle_lease_release'])
def test_exact_expiry_rejects_all_old_authority_without_cleanup(current, operation):
    store, record = current
    request = lease_request(record)
    store.now = record['lease']['expiresAtEpochMilli']
    before = copy.deepcopy(record)
    assert_refusal('lease_invalid', lambda: getattr(authority, operation)(store, record, request))
    assert record == before


def test_expired_takeover_increments_epoch_and_fences_old_writer(current):
    store, record = current
    old = lease_request(record)
    store.now = record['lease']['expiresAtEpochMilli']
    result = authority.handle_lease_acquire(store, record, SimpleNamespace(holderId='holder_2'))
    AcquireLeaseData.model_validate(result)
    assert result['fenceEpoch'] == 2 and result['leaseToken'] != old.leaseToken
    assert_refusal('stale_epoch', lambda: authority.check_lease(store, record, old))


def test_release_does_not_reset_monotonic_epoch(current):
    store, record = current
    for epoch in (2, 3, 4):
        authority.handle_lease_release(store, record, lease_request(record))
        grant = authority.handle_lease_acquire(store, record, SimpleNamespace(holderId='next_holder'))
        assert grant['fenceEpoch'] == epoch


def test_lease_renew_preserves_token_epoch_and_does_not_extend_claim(current):
    store, record = current
    before = copy.deepcopy(record)
    store.now += 20_000
    result = authority.handle_lease_renew(store, record, lease_request(record))
    assert result['leaseToken'] == before['lease']['leaseToken']
    assert result['fenceEpoch'] == 1
    assert result['expiresAtEpochMilli'] == store.now + 120_000
    assert record['narrations'] == before['narrations']


def test_wrong_token_never_renews_even_with_current_epoch(current):
    store, record = current
    request = lease_request(record)
    request.leaseToken = 'unknown_credential'
    before = copy.deepcopy(record)
    assert_refusal('lease_invalid', lambda: authority.handle_lease_renew(store, record, request))
    assert record == before


def test_valid_claim_retrieval_preserves_generation_token_and_issue_time(current):
    store, record = current
    expected = copy.deepcopy(record['narrations']['root_1']['claim'])
    store.now += 10_000
    result = authority.handle_narration_claim(store, record, claim_request(record, currentClaim=None))
    assert result == {'pointId': 'root_1', **expected}
    assert record['control']['revision'] == 7


def test_claim_renew_has_its_own_clock_and_keeps_identity(current):
    store, record = current
    claim = copy.deepcopy(record['narrations']['root_1']['claim'])
    lease = copy.deepcopy(record['lease'])
    store.now += 20_000
    result = authority.handle_narration_renew(store, record, claim_request(record))
    assert result['generation'] == claim['generation']
    assert result['issuedAtEpochMilli'] == claim['issuedAtEpochMilli']
    assert result['expiresAtEpochMilli'] == store.now + 180_000
    assert record['narrations']['root_1']['claim']['claimToken'] == claim['claimToken']
    assert record['lease'] == lease
    assert record['control']['gate']['expiresAtEpochMilli'] == result['expiresAtEpochMilli']


@pytest.mark.parametrize('operation', ['handle_narration_renew', 'handle_narration_submit',
                                        'handle_narration_delete'])
def test_claim_issue_time_is_part_of_identity(current, operation):
    store, record = current
    request = claim_request(record, outcome='ready', text='same text', failureReason=None)
    request.issuedAtEpochMilli += 1
    before = copy.deepcopy(record)
    assert_refusal('claim_fenced', lambda: getattr(authority, operation)(store, record, request))
    assert record == before


def test_takeover_rotates_head_claim_without_waiting_for_claim_ttl(current):
    store, record = current
    old_claim = copy.deepcopy(record['narrations']['root_1']['claim'])
    store.now += 120_000
    authority.handle_lease_acquire(store, record, SimpleNamespace(holderId='holder_2'))
    assert store.now < old_claim['expiresAtEpochMilli']
    result = authority.handle_narration_claim(store, record, claim_request(record, currentClaim=None))
    assert result['generation'] == 2 and result['fenceEpoch'] == 2
    assert result['claimToken'] != old_claim['claimToken']
    old_request = claim_request(record, claimToken=old_claim['claimToken'], generation=1,
                                issuedAtEpochMilli=old_claim['issuedAtEpochMilli'])
    assert_refusal('claim_fenced', lambda: authority.handle_narration_renew(store, record, old_request))


def test_expired_claim_rejected_then_regenerated_under_still_live_lease(current):
    store, record = current
    store.claim_ttl_milli = 5_000
    authority.issue_head_claim(store, record)
    old = claim_request(record)
    store.now += 5_000
    before = copy.deepcopy(record)
    assert_refusal('claim_expired', lambda: authority.handle_narration_renew(store, record, old))
    assert record == before
    result = authority.handle_narration_claim(store, record, claim_request(record, currentClaim=None))
    assert result['generation'] == 2 and result['claimToken'] != old.claimToken


def test_resolve_expired_gate_preserves_pause_phase_and_revision(current):
    store, record = current
    store.claim_ttl_milli = 5_000
    authority.issue_head_claim(store, record)
    record['control']['paused'] = True
    store.now += 5_000
    assert authority.resolve_gate(store, record) == 'claim_expired'
    assert record['control']['gate']['status'] == 'none'
    assert record['control']['paused'] is True
    assert record['control']['phase'] == 'select_actor'
    assert record['control']['revision'] == 7
    assert authority.blocked_reasons(store, record) == ['claim_expired']
    authority.resolve_gate(store, record)
    assert authority.blocked_reasons(store, record) == ['claim_expired']


def test_gate_invalidated_by_epoch_is_cleared_without_unlocking_compute(current):
    store, record = current
    authority.handle_lease_release(store, record, lease_request(record))
    authority.handle_lease_acquire(store, record, SimpleNamespace(holderId='holder_2'))
    assert authority.resolve_gate(store, record) == 'claim_fenced'
    assert record['control']['gate']['status'] == 'none'
    assert authority.blocked_reasons(store, record) == ['claim_fenced']


def test_ready_text_survives_claim_expiry_and_does_not_clear_pause(current):
    store, record = current
    record['control']['paused'] = True
    authority.handle_narration_submit(store, record, claim_request(
        record, outcome='ready', text='已保存的文本\n保持原文。', failureReason=None))
    store.now += 180_000
    authority.handle_lease_acquire(store, record, SimpleNamespace(holderId='holder_2'))
    authority.resolve_gate(store, record)
    assert record['narrations']['root_1']['status'] == 'ready'
    assert record['narrations']['root_1']['text'] == '已保存的文本\n保持原文。'
    assert record['control']['paused'] is True
    assert record['control']['revision'] == 7
    assert authority.blocked_reasons(store, record) == []


def test_failed_retry_rotates_generation_and_late_failure_cannot_overwrite_ready(current):
    store, record = current
    old = claim_request(record, outcome='failed', text=None, failureReason='model_failed')
    authority.handle_narration_submit(store, record, old)
    result = authority.handle_narration_claim(store, record, claim_request(record, currentClaim=None))
    assert result['generation'] == 2
    authority.handle_narration_submit(store, record, claim_request(
        record, outcome='ready', text='重试成功。', failureReason=None))
    before = copy.deepcopy(record)
    assert_refusal('claim_fenced', lambda: authority.handle_narration_submit(store, record, old))
    assert record == before


def test_ready_generation_allows_same_text_but_rejects_text_change_and_failed_result(current):
    store, record = current
    request = claim_request(record, outcome='ready', text='原文', failureReason=None)
    authority.handle_narration_submit(store, record, request)
    authority.handle_narration_submit(store, record, request)
    for outcome, text, reason in [('ready', '替代', None), ('failed', None, 'late')]:
        before = copy.deepcopy(record)
        altered = copy.copy(request)
        altered.outcome, altered.text, altered.failureReason = outcome, text, reason
        assert_refusal('request_malformed', lambda: authority.handle_narration_submit(store, record, altered))
        assert record == before


def test_delete_invalidates_cache_and_old_claim_then_claim_regenerates_once(current):
    store, record = current
    authority.handle_narration_submit(store, record, claim_request(
        record, outcome='ready', text='old cache', failureReason=None))
    old = claim_request(record)
    result = authority.handle_narration_delete(store, record, old)
    assert result['invalidatedGeneration'] == 1
    assert record['narrations']['root_1']['status'] == 'missing'
    assert record['narrations']['root_1']['text'] is None
    assert_refusal('claim_fenced', lambda: authority.handle_narration_renew(store, record, old))
    regenerated = authority.handle_narration_claim(store, record, claim_request(record, currentClaim=None))
    assert regenerated['generation'] == 2 and regenerated['claimToken'] != old.claimToken


def test_history_claim_has_no_lease_and_never_changes_current_head_gate(current):
    store, record = current
    record['headPointId'] = 'point_2'
    record['narrations']['point_2'] = {'status': 'pending', 'text': None, 'generation': 1, 'claim': None}
    authority.issue_head_claim(store, record)
    head_before = copy.deepcopy(record['narrations']['point_2'])
    control_before = copy.deepcopy(record['control'])
    request = claim_request(record, mode='history', point_id='root_1', currentClaim=None)
    result = authority.handle_narration_claim(store, record, request)
    assert result['fenceEpoch'] is None and result['generation'] == 2
    current_claim = SimpleNamespace(**{key: result[key] for key in (
        'claimToken', 'generation', 'issuedAtEpochMilli')})
    assert_refusal('claim_fenced', lambda: authority.handle_narration_claim(store, record, request))
    request.currentClaim = current_claim
    same = authority.handle_narration_claim(store, record, request)
    assert same == result
    authority.handle_narration_submit(store, record, claim_request(
        record, mode='history', point_id='root_1', outcome='ready', text='历史文本', failureReason=None))
    assert record['narrations']['point_2'] == head_before
    assert record['control'] == control_before


def test_history_cannot_claim_current_head(current):
    store, record = current
    before = copy.deepcopy(record)
    assert_refusal('claim_fenced', lambda: authority.handle_narration_claim(
        store, record, claim_request(record, mode='history', currentClaim=None)))
    assert record == before


def test_epoch_exhaustion_refuses_instead_of_wraparound(current):
    store, record = current
    authority.handle_lease_release(store, record, lease_request(record))
    record['_leaseEpoch'] = MAX_SAFE
    before = copy.deepcopy(record)
    assert_refusal('version_mismatch', lambda: authority.handle_lease_acquire(
        store, record, SimpleNamespace(holderId='holder_2')))
    assert record == before


def test_read_projection_reports_lost_lease_and_complete_phase_without_mutation(current):
    store, record = current
    authority.handle_narration_submit(store, record, claim_request(
        record, outcome='ready', text='已完成', failureReason=None))
    record['control']['phase'] = 'complete'
    store.now = record['lease']['expiresAtEpochMilli']
    before = copy.deepcopy(record)
    assert authority.blocked_reasons(store, record) == ['lease_invalid', 'phase_not_computable']
    assert record == before
