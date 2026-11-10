"""D02 role/entity and expression-type checkers.

This module is a candidate-only checker.  It does not choose act/skip, generate
or rewrite action text, approve world feasibility, or decide requirement
coverage.  The program validates what a checker returned; it never fills in a
missing entity or turns uncertainty into a negative action.

Offsets on the wire are Unicode code-point offsets into the complete action
text.  Browser callers that use JavaScript string indices must convert with
``codepoint_to_utf16`` / ``utf16_to_codepoint`` at the boundary.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

ROLES = ('subject', 'object', 'tool', 'recipient', 'destination')
DIAGNOSTIC_ROLES = (
    'source', 'static_location', 'co_agent', 'beneficiary', 'possessor',
    'path', 'topic',
)
SCOPES = ('main', 'condition', 'negation', 'quote', 'hypothesis', 'background')
MENTION_STATUSES = ('bound', 'unknown_entity', 'ambiguous', 'insufficient')
ROLE_STATUSES = ('absent', 'bound', 'unknown_entity', 'ambiguous', 'insufficient')
BINDING_BASES = ('name', 'alias', 'marker', 'pronoun', 'ellipsis', 'context')
ABSTAIN_REASONS = (
    'low_confidence', 'ambiguous_input', 'input_too_long', 'out_of_support',
    'missing_context',
)
EXPRESSION_LABELS = (
    'attempt', 'result_assertion', 'non_action', 'mixed', 'uncertain',
)
INFORMATIONAL_CODES = frozenset({
    'success_word_in_condition', 'success_word_in_quote',
    'success_word_in_background', 'background_fact', 'joint_subject',
})
ROLE_SCHEMA = 'd02.role_audit.v1'
EXPRESSION_SCHEMA = 'd02.expression_audit.v1'
AUTO_BASES = frozenset({'name', 'marker'})
RESULT_CODES = frozenset({
    'unsettled_result', 'result_assertion', 'unsettled_result_assertion',
    'result_assertion_in_action', 'result_assertion_in_attempt',
})
ROLE_KIND = {
    'subject': frozenset({'character'}),
    'recipient': frozenset({'character'}),
    'tool': frozenset({'item'}),
    'destination': frozenset({'location', 'item'}),
    'object': frozenset({'character', 'item', 'location'}),
}
_CODE = re.compile(r'^[a-z][a-z0-9_]{2,63}$')


class CheckError(ValueError):
    """A checker answer is structurally unusable, not a semantic rejection."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class CheckResult:
    decision: str                 # accept | upgrade | incomplete
    issues: tuple                # program and model issues, all explicit
    reason: str | None = None
    diagnostics: dict | None = None

    def wire(self):
        return {
            'decision': self.decision,
            'issues': [dict(row) for row in self.issues],
            'reason': self.reason,
            'diagnostics': dict(self.diagnostics or {}),
        }


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _require(ok, code, message):
    if not ok:
        raise CheckError(code, message)


def _text(value, code):
    _require(isinstance(value, str) and bool(value.strip()), code, code)
    return value


def _keys(value, required, optional=(), code='invalid_object'):
    _require(isinstance(value, dict), code, code)
    missing = set(required) - set(value)
    extra = set(value) - set(required) - set(optional)
    _require(not missing and not extra, code,
             code + ': missing=' + ','.join(sorted(missing)) +
             ' extra=' + ','.join(sorted(extra)))
    return value


def _int(value, code):
    _require(type(value) is int, code, code)
    return value


def _string_list(value, code, allowed=None):
    _require(isinstance(value, list) and all(isinstance(x, str) and x for x in value),
             code, code)
    _require(len(value) == len(set(value)), code, code + ':duplicate')
    if allowed is not None:
        _require(set(value) <= set(allowed), code, code + ':unknown')
    return value


def _bool(value, code):
    _require(type(value) is bool, code, code)
    return value


def _span(text, start, end, code):
    _int(start, code)
    _int(end, code)
    _require(0 <= start < end <= len(text), code, code + ':range')
    return start, end


def _issue_rows(rows, text, step_index, *, require_scope=False):
    _require(isinstance(rows, list), 'invalid_issues', 'invalid_issues')
    normalized = []
    for row in rows:
        _keys(row, ('code', 'message', 'blocking'),
              ('stepId', 'start', 'end', 'scope'), 'invalid_issue')
        _text(row['code'], 'invalid_issue_code')
        _require(bool(_CODE.match(row['code'])), 'invalid_issue_code',
                 'invalid_issue_code:' + row['code'])
        _text(row['message'], 'invalid_issue_message')
        _bool(row['blocking'], 'invalid_issue_blocking')
        scope = row.get('scope')
        if require_scope:
            _require(scope in SCOPES, 'invalid_issue_scope', 'invalid_issue_scope')
        elif scope is not None:
            _require(scope in SCOPES, 'invalid_issue_scope', 'invalid_issue_scope')
        step_id = row.get('stepId')
        if step_id is not None:
            _require(step_id in step_index, 'unknown_issue_step', 'unknown_issue_step')
        has_start, has_end = 'start' in row, 'end' in row
        _require(has_start == has_end, 'partial_issue_span', 'partial_issue_span')
        if has_start:
            _span(text, row['start'], row['end'], 'invalid_issue_span')
            _require(step_id is not None, 'issue_span_without_step',
                     'issue_span_without_step')
            _require(step_index[step_id][0] <= row['start'] and row['end'] <= step_index[step_id][1],
                     'issue_span_outside_step', 'issue_span_outside_step')
            _require(scope is not None, 'issue_span_without_scope',
                     'issue_span_without_scope')
        elif require_scope:
            _require(scope is not None, 'missing_issue_scope', 'missing_issue_scope')
        normalized.append({
            'code': row['code'], 'message': row['message'],
            'blocking': row['blocking'], 'scope': scope, 'stepId': step_id,
            'start': row.get('start'), 'end': row.get('end'), 'source': 'model',
        })
    return normalized


def normalize_steps(text, steps):
    """Validate the step partition and return id -> (start, end, text)."""
    _text(text, 'missing_text')
    _require(isinstance(steps, list) and steps, 'missing_steps', 'missing_steps')
    rows = []
    for row in steps:
        _keys(row, ('stepId', 'start', 'end'), code='invalid_step')
        _text(row['stepId'], 'invalid_step_id')
        start, end = _span(text, row['start'], row['end'], 'invalid_step_span')
        rows.append((row['stepId'], start, end))
    _require(len({row[0] for row in rows}) == len(rows), 'duplicate_step_id',
             'duplicate_step_id')
    rows.sort(key=lambda row: row[1])
    _require(rows[0][1] >= 0, 'invalid_step_span', 'invalid_step_span')
    for left, right in zip(rows, rows[1:]):
        _require(left[2] <= right[1], 'overlapping_steps', 'overlapping_steps')
    return {step_id: (start, end, text[start:end]) for step_id, start, end in rows}


def _step_for(step_index, start, end):
    matches = [step_id for step_id, (lo, hi, _) in step_index.items()
               if lo <= start < end <= hi]
    _require(len(matches) == 1, 'span_crosses_step', 'span_crosses_step')
    return matches[0]


def normalize_world(world):
    """Return id -> {kind, name, aliases}; reject lossy or ambiguous registries."""
    _require(isinstance(world, dict), 'invalid_world', 'invalid_world')
    rows = {}
    if 'entities' in world:
        _require(isinstance(world['entities'], dict), 'invalid_world', 'invalid_world')
        for key, row in world['entities'].items():
            _keys(row, ('type', 'name'), ('aliases',), code='invalid_entity')
            _text(key, 'invalid_entity_id')
            kind = row['type']
            _require(kind in ('character', 'item', 'location'), 'invalid_entity_type',
                     'invalid_entity_type')
            name = _text(row['name'], 'invalid_entity_name')
            aliases = _string_list(row.get('aliases', []), 'invalid_entity_aliases')
            _require(name not in aliases, 'invalid_entity_aliases', 'name repeated as alias')
            rows[key] = {'id': key, 'kind': kind, 'name': name, 'aliases': tuple(aliases)}
    elif 'initial' in world and isinstance(world.get('initial'), dict):
        kinds = {'characters': 'character', 'items': 'item', 'locations': 'location'}
        for plural, kind in kinds.items():
            bucket = world['initial'].get(plural, {})
            _require(isinstance(bucket, dict), 'invalid_world', 'invalid_world')
            for key, row in bucket.items():
                _require(isinstance(row, dict) and row.get('id') == key,
                         'invalid_world_identity', 'invalid_world_identity')
                name = _text(row.get('name'), 'invalid_entity_name')
                rows[key] = {'id': key, 'kind': kind, 'name': name, 'aliases': ()}
    else:
        for plural, kind in (('characters', 'character'), ('items', 'item'),
                             ('places', 'location')):
            bucket = world.get(plural)
            if bucket is None:
                continue
            _require(isinstance(bucket, list), 'invalid_world', 'invalid_world')
            for row in bucket:
                _keys(row, ('id', 'name'), ('aliases',), code='invalid_entity')
                kind_value = row.get('type', kind)
                _require(kind_value in ('character', 'item', 'location'),
                         'invalid_entity_type', 'invalid_entity_type')
                aliases = _string_list(row.get('aliases', []), 'invalid_entity_aliases')
                rows[row['id']] = {'id': row['id'], 'kind': kind_value,
                                   'name': row['name'], 'aliases': tuple(aliases)}
    _require(rows, 'empty_world', 'empty_world')
    return rows


def _entity(entities, entity_id, code='unknown_entity_id'):
    _require(isinstance(entity_id, str) and entity_id in entities, code, code)
    return entities[entity_id]


def _mention_surface_matches(text, row, entity, representation):
    start, end = row['start'], row['end']
    surface = text[start:end]
    _require(row['surface'] == surface, 'surface_mismatch', 'surface_mismatch')
    basis = row['bindingBasis']
    if row['status'] != 'bound':
        return
    if basis == 'name':
        _require(representation == 'natural', 'basis_representation_mismatch',
                 'name basis in references representation')
        _require(surface == entity['name'], 'surface_name_mismatch',
                 'surface_name_mismatch')
    elif basis == 'marker':
        _require(representation == 'references', 'basis_representation_mismatch',
                 'marker basis in natural representation')
        _require(surface == '[[' + entity['id'] + ']]', 'surface_marker_mismatch',
                 'surface_marker_mismatch')
    elif basis == 'alias':
        _require(representation == 'natural', 'basis_representation_mismatch',
                 'alias basis in references representation')
        _require(surface in entity['aliases'], 'surface_alias_mismatch',
                 'surface_alias_mismatch')


def validate_role_audit(text, steps, audit, world, actor_id, *, representation='natural'):
    """Validate M1 and return accept/upgrade/incomplete; never act/skip."""
    try:
        _text(text, 'missing_text')
        step_index = normalize_steps(text, steps)
        entities = normalize_world(world)
        _require(actor_id in entities, 'unknown_actor', 'unknown_actor')
        _require(entities[actor_id]['kind'] == 'character', 'actor_not_character',
                 'actor_not_character')
        _require(representation in ('natural', 'references'), 'invalid_representation',
                 'invalid_representation')
        _keys(audit, ('schema', 'textSha256', 'steps', 'issues'), code='invalid_audit')
        _require(audit['schema'] == ROLE_SCHEMA, 'wrong_schema', 'wrong_schema')
        _require(audit['textSha256'] == digest(text), 'stale_audit',
                 'stale_audit:text digest mismatch')
        _require(isinstance(audit['steps'], list), 'invalid_audit', 'invalid_audit')
        model_issues = _issue_rows(audit['issues'], text, step_index)
        rows = {}
        for step in audit['steps']:
            _keys(step, ('stepId', 'mentions', 'roleStatus'), ('issues',),
                  code='invalid_step_audit')
            _text(step['stepId'], 'invalid_step_id')
            _require(step['stepId'] in step_index, 'unknown_step', 'unknown_step')
            _require(step['stepId'] not in rows, 'duplicate_step', 'duplicate_step')
            _require(isinstance(step['mentions'], list), 'invalid_mentions',
                     'invalid_mentions')
            _keys(step['roleStatus'], ROLES, code='invalid_role_status')
            step_issues = []
            for issue in step.get('issues', []):
                if 'stepId' not in issue:
                    issue = dict(issue, stepId=step['stepId'])
                step_issues.append(issue)
            model_issues.extend(_issue_rows(step_issues, text, step_index))
            rows[step['stepId']] = step
        _require(set(rows) == set(step_index), 'step_coverage', 'step_coverage')

        all_mentions = {}
        for step_id, step in rows.items():
            lo, hi, _ = step_index[step_id]
            step_mentions = []
            seen_ids, seen_spans = set(), set()
            for mention in step['mentions']:
                _keys(mention, ('mentionId', 'start', 'end', 'surface', 'roles',
                                'status', 'bindingBasis', 'scope'),
                      ('entityId', 'candidates', 'diagnosticRoles', 'confidence',
                       'issueCodes'), code='invalid_mention')
                _text(mention['mentionId'], 'invalid_mention_id')
                _require(mention['mentionId'] not in seen_ids, 'duplicate_mention_id',
                         'duplicate_mention_id')
                seen_ids.add(mention['mentionId'])
                start, end = _span(text, mention['start'], mention['end'],
                                   'invalid_mention_span')
                _require(lo <= start and end <= hi, 'mention_outside_step',
                         'mention_outside_step')
                _require((start, end) not in seen_spans, 'duplicate_mention_span',
                         'duplicate_mention_span')
                seen_spans.add((start, end))
                _text(mention['surface'], 'missing_surface')
                roles = _string_list(mention['roles'], 'invalid_roles', ROLES)
                diagnostic = _string_list(mention.get('diagnosticRoles', []),
                                          'invalid_diagnostic_roles', DIAGNOSTIC_ROLES)
                _require(bool(roles) or bool(diagnostic), 'mention_without_role',
                         'mention_without_role')
                _require(not (set(roles) & set(diagnostic)), 'public_diagnostic_overlap',
                         'public and diagnostic roles overlap')
                _require(mention['status'] in MENTION_STATUSES, 'invalid_mention_status',
                         'invalid_mention_status')
                _require(mention['bindingBasis'] in BINDING_BASES,
                         'invalid_binding_basis', 'invalid_binding_basis')
                _require(mention['scope'] in SCOPES, 'invalid_scope', 'invalid_scope')
                _string_list(mention.get('issueCodes', []), 'invalid_mention_issue_codes')
                if 'confidence' in mention:
                    value = mention['confidence']
                    _require(type(value) in (int, float) and 0 <= value <= 1,
                             'invalid_confidence', 'invalid_confidence')
                candidates = _string_list(mention.get('candidates', []),
                                          'invalid_candidates')
                entity_id = mention.get('entityId')
                if mention['status'] == 'bound':
                    entity = _entity(entities, entity_id)
                    _require(not candidates, 'bound_with_candidates',
                             'bound_with_candidates')
                    _require(mention['bindingBasis'] in AUTO_BASES or
                             mention['bindingBasis'] in ('alias', 'pronoun', 'ellipsis', 'context'),
                             'invalid_binding_basis', 'invalid_binding_basis')
                    _mention_surface_matches(text, mention, entity, representation)
                elif mention['status'] == 'unknown_entity':
                    _require(entity_id is None, 'unknown_with_entity',
                             'unknown_with_entity')
                    _require(not candidates, 'unknown_with_candidates',
                             'unknown_with_candidates')
                elif mention['status'] == 'ambiguous':
                    _require(entity_id is None, 'ambiguous_with_entity',
                             'ambiguous_with_entity')
                    _require(len(candidates) >= 2, 'ambiguous_needs_candidates',
                             'ambiguous_needs_candidates')
                    for candidate in candidates:
                        _entity(entities, candidate)
                else:
                    _require(entity_id is None, 'insufficient_with_entity',
                             'insufficient_with_entity')
                    _require(len(candidates) <= 1, 'insufficient_candidates',
                             'insufficient_candidates')
                    for candidate in candidates:
                        _entity(entities, candidate)
                step_mentions.append(mention)
                _require(mention['mentionId'] not in all_mentions, 'duplicate_mention_id',
                         'duplicate_mention_id')
                all_mentions[mention['mentionId']] = (step_id, mention)
            by_id = {m['mentionId']: m for m in step_mentions}
            for role in ROLES:
                slot = step['roleStatus'][role]
                _keys(slot, ('status', 'mentionIds'), code='invalid_role_slot')
                _require(slot['status'] in ROLE_STATUSES, 'invalid_role_status',
                         'invalid_role_status')
                mention_ids = _string_list(slot['mentionIds'], 'invalid_role_mentions')
                _require(set(mention_ids) <= set(by_id), 'role_mentions_unknown',
                         'role_mentions_unknown')
                with_role = {m['mentionId'] for m in step_mentions if role in m['roles']}
                eligible = [by_id[m] for m in mention_ids]
                for mention in eligible:
                    _require(role in mention['roles'], 'role_mention_missing_role',
                             'role_mention_missing_role')
                if slot['status'] == 'absent':
                    _require(not mention_ids and not with_role, 'absent_with_mentions',
                             'absent_with_mentions')
                elif slot['status'] == 'insufficient' and not mention_ids:
                    _require(role == 'subject', 'empty_insufficient_role',
                             'only an implicit subject may have no span')
                    _require(any(issue['code'] == 'implicit_subject'
                                 for issue in model_issues if issue['stepId'] == step_id),
                             'implicit_subject_without_issue', 'implicit_subject_without_issue')
                else:
                    _require(set(mention_ids) == with_role, 'role_mention_coverage',
                             'role_mention_coverage')
                    statuses = {m['status'] for m in eligible}
                    if 'ambiguous' in statuses:
                        derived = 'ambiguous'
                    elif 'unknown_entity' in statuses:
                        derived = 'unknown_entity'
                    elif 'insufficient' in statuses:
                        derived = 'insufficient'
                    else:
                        derived = 'bound'
                    _require(slot['status'] == derived, 'role_status_mismatch',
                             'role_status_mismatch')
    except CheckError as exc:
        return CheckResult('incomplete', (
            {'code': exc.code, 'message': exc.message, 'blocking': True,
             'scope': 'main', 'stepId': None, 'start': None, 'end': None,
             'source': 'program'},
        ), reason='checker_output_invalid:' + exc.code)

    issues = list(model_issues)
    diagnostics = {'autoAcceptEligible': True, 'mentions': len(all_mentions)}

    def add(code, message, step_id=None, start=None, end=None, scope='main'):
        issues.append({'code': code, 'message': message, 'blocking': True,
                       'scope': scope, 'stepId': step_id, 'start': start,
                       'end': end, 'source': 'program'})
        diagnostics['autoAcceptEligible'] = False

    for step_id, step in rows.items():
        for role in ROLES:
            slot = step['roleStatus'][role]
            if slot['status'] in ('unknown_entity', 'ambiguous', 'insufficient'):
                add('unresolved_role_' + role,
                    'role has no safe registered binding', step_id)
            if slot['status'] == 'absent' and role == 'subject':
                add('missing_subject', 'action has no subject binding', step_id)
        for mention in step['mentions']:
            if mention['status'] != 'bound':
                add('unresolved_mention', 'mention is not bound to one entity',
                    step_id, mention['start'], mention['end'])
                continue
            entity = entities[mention['entityId']]
            if mention['bindingBasis'] == 'alias':
                add('alias_requires_review', 'alias is outside the first auto-accept scope',
                    step_id, mention['start'], mention['end'])
            elif mention['bindingBasis'] in ('pronoun', 'ellipsis', 'context'):
                add('reference_requires_review',
                    'pronoun/ellipsis/context binding requires API review',
                    step_id, mention['start'], mention['end'])
            if not mention['roles']:
                add('diagnostic_role_requires_review',
                    'mention only carries an internal diagnostic role',
                    step_id, mention['start'], mention['end'])
            for role in mention['roles']:
                allowed = ROLE_KIND[role]
                if entity['kind'] not in allowed:
                    add('role_type_mismatch',
                        role + ' is incompatible with registered entity type ' + entity['kind'],
                        step_id, mention['start'], mention['end'])
            diagnostic_kind = {
                'source': frozenset({'character'}),
                'co_agent': frozenset({'character'}),
                'beneficiary': frozenset({'character'}),
                'possessor': frozenset({'character'}),
                'static_location': frozenset({'location'}),
                'path': frozenset({'location', 'item'}),
                'topic': frozenset({'character', 'item', 'location'}),
            }
            for role in mention['diagnosticRoles']:
                if entity['kind'] not in diagnostic_kind[role]:
                    add('diagnostic_role_type_mismatch',
                        role + ' is incompatible with registered entity type ' + entity['kind'],
                        step_id, mention['start'], mention['end'])
        subjects = [m for m in step['mentions']
                    if 'subject' in m['roles'] and m['status'] == 'bound']
        if step['roleStatus']['subject']['status'] == 'bound':
            subject_ids = {m['entityId'] for m in subjects}
            if actor_id not in subject_ids:
                add('actor_mismatch',
                    'text subject does not include the current actor', step_id)
            elif len(subject_ids) > 1:
                issues.append({'code': 'joint_subject', 'message': 'multiple explicit subjects',
                               'blocking': False, 'scope': 'main', 'stepId': step_id,
                               'start': None, 'end': None, 'source': 'program'})

    blocking = [issue for issue in issues if issue['blocking']]
    diagnostics['blockingCodes'] = sorted({issue['code'] for issue in blocking})
    return CheckResult('upgrade' if blocking else 'accept', tuple(issues),
                       None, diagnostics)


def validate_expression_audit(text, steps, audit):
    """Validate M2; only the expression type and issue location, not world truth."""
    try:
        _text(text, 'missing_text')
        step_index = normalize_steps(text, steps)
        _keys(audit, ('schema', 'textSha256', 'label', 'issues', 'abstain'),
              code='invalid_audit')
        _require(audit['schema'] == EXPRESSION_SCHEMA, 'wrong_schema', 'wrong_schema')
        _require(audit['textSha256'] == digest(text), 'stale_audit',
                 'stale_audit:text digest mismatch')
        _require(audit['label'] is None or audit['label'] in EXPRESSION_LABELS,
                 'invalid_label', 'invalid_label')
        model_issues = _issue_rows(audit['issues'], text, step_index,
                                   require_scope=True)
        abstain = audit['abstain']
        if abstain is not None:
            _keys(abstain, ('reason', 'detail'), code='invalid_abstain')
            _require(abstain['reason'] in ABSTAIN_REASONS, 'invalid_abstain_reason',
                     'invalid_abstain_reason')
            _text(abstain['detail'], 'invalid_abstain_detail')
            _require(audit['label'] is None, 'abstain_with_label', 'abstain_with_label')
        else:
            _require(audit['label'] is not None, 'missing_label', 'missing_label')
    except CheckError as exc:
        return CheckResult('incomplete', (
            {'code': exc.code, 'message': exc.message, 'blocking': True,
             'scope': 'main', 'stepId': None, 'start': None, 'end': None,
             'source': 'program'},
        ), reason='checker_output_invalid:' + exc.code)

    issues = list(model_issues)
    blocking = [issue for issue in issues if issue['blocking']]
    diagnostics = {'label': audit['label'], 'abstain': abstain,
                   'blockingCodes': sorted({issue['code'] for issue in blocking})}
    if abstain is not None:
        reason = abstain['reason']
        decision = 'incomplete' if reason in ('input_too_long', 'out_of_support',
                                             'missing_context') else 'upgrade'
        return CheckResult(decision, tuple(issues),
                           'abstain:' + reason, diagnostics)

    label = audit['label']
    if label == 'attempt':
        decision = 'upgrade' if blocking else 'accept'
    elif label in ('mixed', 'result_assertion'):
        main_result = [issue for issue in blocking
                       if issue['scope'] == 'main' and issue['code'] in RESULT_CODES]
        if not main_result:
            issues.append({'code': 'inconsistent_result_label',
                           'message': 'result label needs a main-scope unsettled result',
                           'blocking': True, 'scope': 'main', 'stepId': None,
                           'start': None, 'end': None, 'source': 'program'})
        decision = 'upgrade'
    elif label == 'non_action':
        decision = 'upgrade'
    else:  # uncertain
        decision = 'upgrade'
    return CheckResult(decision, tuple(issues), None, diagnostics)


def combine(*results):
    """Conservative AND: any incomplete wins, then any upgrade, then accept."""
    _require(results and all(isinstance(row, CheckResult) for row in results),
             'invalid_combination', 'invalid_combination')
    issues = tuple(issue for row in results for issue in row.issues)
    diagnostics = {}
    for row in results:
        diagnostics.update(row.diagnostics or {})
    for decision in ('incomplete', 'upgrade'):
        if any(row.decision == decision for row in results):
            return CheckResult(decision, issues,
                               next((row.reason for row in results if row.decision == decision), None),
                               diagnostics)
    return CheckResult('accept', issues, None, diagnostics)


def check_once(text, steps, role_audit, expression_audit, world, actor_id, *,
               representation='natural'):
    """Validate both checker answers against the same bytes and step partition."""
    m1 = validate_role_audit(text, steps, role_audit, world, actor_id,
                             representation=representation)
    m2 = validate_expression_audit(text, steps, expression_audit)
    return combine(m1, m2)


def run_bounded_check(text, check, *, repair=None, coverage=None, max_repairs=1,
                      skip=False):
    """One initial attempt plus at most one aggregated API repair by default.

    ``check(text)`` must return CheckResult.  ``repair(issues, text)`` is the
    only API path that may produce new action text.  It receives every issue
    from the round, not a selected subset.  A local acceptance after repair is
    recorded as ``api_repair``; it is not a small-model pass.
    """
    _require(type(max_repairs) is int and 0 <= max_repairs <= 1,
             'repair_budget', 'repair budget must be 0 or 1')
    if skip:
        return {'decision': 'skip', 'acceptedVia': 'api_skip', 'rounds': [],
                'text': text}
    rounds = []

    def one(current, source):
        result = check(current)
        _require(isinstance(result, CheckResult), 'invalid_check_result',
                 'invalid_check_result')
        rounds.append({'source': source, 'textSha256': digest(current),
                       'decision': result.decision,
                       'issues': [dict(row) for row in result.issues],
                       'reason': result.reason})
        return result

    result = one(text, 'initial')
    if result.decision == 'accept':
        return {'decision': 'accept', 'acceptedVia': 'local_checks',
                'rounds': rounds, 'text': text}
    if result.decision == 'incomplete':
        return {'decision': 'incomplete', 'acceptedVia': None,
                'rounds': rounds, 'text': text,
                'reason': result.reason or 'initial_incomplete'}
    for _ in range(max_repairs):
        if result.decision != 'upgrade' or repair is None:
            break
        repaired = repair(list(result.issues), text)
        _require(repaired is None or isinstance(repaired, str),
                 'invalid_repair', 'invalid_repair')
        if repaired is None or not repaired.strip():
            return {'decision': 'incomplete', 'acceptedVia': None,
                    'rounds': rounds, 'text': text, 'reason': 'repair_empty'}
        if repaired == text:
            return {'decision': 'incomplete', 'acceptedVia': None,
                    'rounds': rounds, 'text': text, 'reason': 'repair_no_change'}
        text = repaired
        result = one(text, 'api_repair')
        if result.decision == 'accept':
            if coverage is not None and coverage(text) is not True:
                return {'decision': 'incomplete', 'acceptedVia': None,
                        'rounds': rounds, 'text': text,
                        'reason': 'coverage_regressed_after_repair'}
            return {'decision': 'accept', 'acceptedVia': 'api_repair',
                    'rounds': rounds, 'text': text}
        if result.decision == 'incomplete':
            return {'decision': 'incomplete', 'acceptedVia': None,
                    'rounds': rounds, 'text': text,
                    'reason': result.reason or 'repair_incomplete'}
    return {'decision': 'incomplete', 'acceptedVia': None, 'rounds': rounds,
            'text': text, 'reason': 'unresolved_after_repair'}


def codepoint_to_utf16(text, index):
    """Convert a Python code-point boundary to a JavaScript UTF-16 boundary."""
    _require(isinstance(text, str), 'invalid_text', 'invalid_text')
    _int(index, 'invalid_index')
    _require(0 <= index <= len(text), 'index_range', 'index_range')
    return len(text[:index].encode('utf-16-le')) // 2


def utf16_to_codepoint(text, index):
    """Convert a JavaScript UTF-16 boundary to a code-point boundary.

    A boundary inside a surrogate pair is rejected rather than rounded.
    """
    _require(isinstance(text, str), 'invalid_text', 'invalid_text')
    _int(index, 'invalid_index')
    _require(0 <= index <= len(text.encode('utf-16-le')) // 2, 'index_range',
             'index_range')
    units = 0
    for position, char in enumerate(text):
        if units == index:
            return position
        width = 2 if ord(char) > 0xFFFF else 1
        units += width
        if units > index:
            raise CheckError('utf16_split_surrogate', 'index splits a surrogate pair')
    _require(units == index, 'index_range', 'index_range')
    return len(text)
