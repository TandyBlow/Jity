"""Internal D contracts. These are candidates, never the A/B wire authority.

Model adapters must preserve complete input and return explicit completion.
No fallback in this module invents a semantic negative answer.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import math
import time
from dataclasses import dataclass
from typing import Any, Callable


class ContractError(ValueError):
    pass


def json_value(value):
    if dataclasses.is_dataclass(value):
        return {f.name: json_value(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        if any(not isinstance(k, str) for k in value):
            raise ContractError('non_string_json_key')
        return {k: json_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(v) for v in value]
    return value


def digest(value):
    return hashlib.sha256(json.dumps(json_value(value), ensure_ascii=False,
        sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class Completion:
    status: str
    value: Any = None
    reason: str | None = None

    def __post_init__(self):
        if self.status not in ('result', 'empty', 'incomplete'):
            raise ContractError('invalid_completion_status')
        if self.status == 'result' and (self.value is None or self.reason is not None):
            raise ContractError('result_requires_value_without_error')
        if self.status == 'empty' and (self.value is not None or self.reason is not None):
            raise ContractError('empty_cannot_carry_result_or_error')
        if self.status == 'incomplete' and (not isinstance(self.reason, str) or
                not self.reason.strip() or self.value is not None):
            raise ContractError('incomplete_requires_reason_not_partial_answer')


def result(value):
    return Completion('result', copy.deepcopy(value))


def empty():
    return Completion('empty')


def incomplete(reason):
    return Completion('incomplete', reason=reason)


@dataclass(frozen=True)
class ModelIdentity:
    model: str
    weights: str
    adapter: str
    tokenizer: str
    precision: str
    implementation: str
    capability: str = 'unvalidated'

    def __post_init__(self):
        if any(not isinstance(v, str) or not v.strip() for v in dataclasses.asdict(self).values()):
            raise ContractError('model_identity_incomplete')


class ModelSession:
    """Bound calls, exact-input cache, append-only attempts, explicit cancellation.

    The enclosing experiment supervisor enforces process timeout/RSS; a late
    adapter answer is rejected here as well. Cache is optional and off by
    default. It never crosses model, adapter, tokenizer, precision or epoch.
    """
    def __init__(self, provider: Callable | None, *, binding: dict,
                 identity: ModelIdentity, retries=0, max_calls=512,
                 timeout_ms=120000, cache=False, journal=None):
        if not isinstance(binding, dict) or not binding:
            raise ContractError('missing_request_binding')
        if type(retries) is not int or not 0 <= retries <= 2:
            raise ContractError('retry_policy_out_of_range')
        if (type(max_calls) is not int or max_calls < 1 or type(timeout_ms) not in (int, float)
                or not math.isfinite(timeout_ms) or timeout_ms <= 0):
            raise ContractError('invalid_resource_policy')
        if not isinstance(identity, ModelIdentity):
            raise ContractError('missing_model_identity')
        self.provider, self.binding, self.identity = provider, copy.deepcopy(binding), identity
        self.retries, self.max_calls, self.timeout_ms = retries, max_calls, timeout_ms
        self.cache_enabled, self.journal = cache, journal
        self.attempts, self._cache = [], {}
        self._replay, self.replay_events, self.cache_events = {}, [], []
        self.cancelled = False
        self.generation = 0

    def cancel(self):
        self.cancelled = True
        self.generation += 1
        self._cache.clear()
        self._replay.clear()

    def checkpoint(self):
        state = {'binding': self.binding, 'identity': dataclasses.asdict(self.identity),
                 'generation': self.generation, 'attempts': self.attempts,
                 'policy': {'retries': self.retries, 'max_calls': self.max_calls, 'timeout_ms': self.timeout_ms}}
        return {'state': copy.deepcopy(state), 'sha256': digest(state)}

    def restore(self, checkpoint):
        """Exact successful-call replay; no unfinished call becomes a negative.

        The outer runner verifies the frozen plan/journal provenance before
        supplying this checkpoint. This digest detects corruption, not forgery.
        A/B allocation and preview callbacks must remain idempotent and bound.
        """
        s = checkpoint.get('state')
        if checkpoint.get('sha256') != digest(s):
            raise ContractError('corrupt_model_checkpoint')
        if (self.attempts or self.cancelled or s['binding'] != self.binding
                or s['identity'] != dataclasses.asdict(self.identity)
                or s['policy'] != {'retries': self.retries, 'max_calls': self.max_calls, 'timeout_ms': self.timeout_ms}):
            raise ContractError('model_checkpoint_identity_or_policy_mismatch')
        replay = {}
        for event in s['attempts']:
            bound = {k: event[k] for k in ('component', 'binding', 'generation', 'identity', 'input')}
            if (event['binding'] != self.binding or event['identity'] != dataclasses.asdict(self.identity)
                    or event['cacheKey'] != digest(bound) or event['inputHash'] != digest(event['input'])):
                raise ContractError('model_checkpoint_input_mismatch')
            completion = Completion(**event['completion'])
            if completion.status != event['status']:
                raise ContractError('model_checkpoint_completion_mismatch')
            if completion.status != 'incomplete':
                key = digest({k: bound[k] for k in ('component', 'binding', 'identity', 'input')})
                if key in replay and digest(replay[key]) != digest(completion):
                    raise ContractError('conflicting_completed_replay')
                replay[key] = completion
        self.attempts = copy.deepcopy(s['attempts'])
        self._replay = replay
        self.generation = s['generation'] + 1

    def _record(self, event):
        event = copy.deepcopy(event)
        self.attempts.append(event)
        if self.journal is not None:
            self.journal('short_component', json_value(event))

    def call(self, component, payload):
        if self.cancelled:
            return incomplete('cancelled')
        if not isinstance(payload, dict):
            return incomplete('input_not_object')
        snapshot = copy.deepcopy(payload)
        epoch = self.generation
        bound = {'component': component, 'binding': copy.deepcopy(self.binding),
                 'generation': epoch, 'identity': dataclasses.asdict(self.identity), 'input': snapshot}
        try:
            key = digest(bound)
            semantic_key = digest({k: bound[k] for k in ('component', 'binding', 'identity', 'input')})
        except (ValueError, TypeError) as exc:
            return incomplete('invalid_json_input:' + str(exc))
        if semantic_key in self._replay:
            event = {'component': component, 'inputHash': digest(snapshot), 'source': 'verified_checkpoint',
                     'generation': epoch, 'modelCalled': False}
            self.replay_events.append(event)
            if self.journal is not None:
                self.journal('short_component_replay', event)
            return copy.deepcopy(self._replay[semantic_key])
        if self.cache_enabled and key in self._cache:
            event = {'component': component, 'inputHash': digest(snapshot), 'cacheKey': key,
                     'source': 'exact_input_cache', 'generation': epoch, 'modelCalled': False}
            self.cache_events.append(event)
            if self.journal is not None:
                self.journal('short_component_cache', event)
            return copy.deepcopy(self._cache[key])
        for retry in range(self.retries + 1):
            if len(self.attempts) >= self.max_calls:
                return incomplete('budget_paused')
            started = time.perf_counter()
            event = dict(bound, inputHash=digest(snapshot), cacheKey=key,
                         attempt=retry, status='started', rawOutput=None)
            # Start survives an exception/worker kill through the shared journal.
            if self.journal is not None:
                self.journal('short_component_start', json_value(event))
            try:
                answer = incomplete('model_unavailable') if self.provider is None else self.provider(component, copy.deepcopy(snapshot))
                if not isinstance(answer, Completion):
                    raise ContractError('adapter_missing_completion_evidence')
                event['rawOutput'] = json_value(answer)
                if self.cancelled or self.generation != epoch:
                    answer = incomplete('cancelled_or_stale_output')
                elif digest(self.binding) != digest(bound['binding']) or self.identity != ModelIdentity(**bound['identity']):
                    answer = incomplete('binding_changed_during_call')
                elif (time.perf_counter() - started) * 1000 > self.timeout_ms:
                    answer = incomplete('timeout')
            except Exception as exc:
                answer = incomplete(f'{type(exc).__name__}: {exc}')
            event.update(status=answer.status, completion=json_value(answer),
                         elapsedMs=(time.perf_counter() - started) * 1000)
            self._record(event)
            if answer.status != 'incomplete':
                if self.cache_enabled:
                    self._cache[key] = copy.deepcopy(answer)
                return answer
            if self.cancelled:
                return answer
        return answer


def require_fields(value, fields):
    if not isinstance(value, dict) or any(k not in value for k in fields):
        raise ContractError('missing_fields:' + ','.join(fields))
    return value


def exact_coverage(actual, expected, label='coverage'):
    actual, expected = list(actual), list(expected)
    if len(actual) != len(set(actual)) or set(actual) != set(expected):
        raise ContractError(label + '_mismatch')


def integer_0_100(value):
    if type(value) is not int or not 0 <= value <= 100:
        raise ContractError('expected_integer_0_100')
    return value


class FrozenValue:
    """Canonical bytes prevent nested caller mutation after freezing."""
    def __init__(self, value):
        self._bytes = json.dumps(json_value(value), ensure_ascii=False, sort_keys=True,
                                 separators=(',', ':'), allow_nan=False).encode()
        self.hash = hashlib.sha256(self._bytes).hexdigest()

    def read(self):
        return json.loads(self._bytes)


class CostLedger:
    """One measured wall interval; component buckets never subtract from it."""
    BUCKETS = ('d_model', 'program_service', 'c_generation', 'gate_wait', 'cold_load', 'request_load')

    def __init__(self, workload):
        if not isinstance(workload, dict) or not workload:
            raise ContractError('workload_not_registered')
        self.workload = FrozenValue(workload)
        self.started = time.perf_counter()
        self.events = []

    def record(self, bucket, elapsed_ms, status='complete'):
        if bucket not in self.BUCKETS or not isinstance(elapsed_ms, (int, float)) or elapsed_ms < 0:
            raise ContractError('invalid_timing')
        if not __import__('math').isfinite(elapsed_ms):
            raise ContractError('invalid_timing')
        self.events.append({'bucket': bucket, 'elapsedMs': elapsed_ms, 'status': status})

    def finish(self, *, scope, completed, real_models, c_ready):
        wall = (time.perf_counter() - self.started) * 1000
        eligible = scope == 'complete_request' and completed and real_models and c_ready
        return {'workload': self.workload.read(), 'scope': scope, 'wallMs': wall,
                'events': copy.deepcopy(self.events), 'completed': completed,
                'performance500ms': ('pass' if wall <= 500 else 'fail') if eligible else 'unverified'}
