"""Prepare 90 source-card drafts for human review, never model execution.

Source cards are authoring material. They are not lab.py inputs, frozen cases,
independently certified sources, training data, or an approved run manifest.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

from lab import canonical_bytes, load_jsonl, sha256_file
from round1_scenarios import SECTIONS

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
DATA = BASE / 'data/round1'
ARTIFACTS = ROOT / 'artifacts/world-components-logic'
RULE_COMMIT = '6aabd75072be8e60eb6f13fe2d590c2141cb3dba'
RULE_PATHS = ('design/browser-world-state-workflow.md',
              'design/world-engine-reports/components-logic/evaluation-plan.md')
QUESTIONS = {
    'D02': '当前人物应行动还是合理不行动？若行动，可接受的尝试是什么？',
    'D03': '已冻结的这个源会牵连完整名册中的哪些人物？当前关系的未来骰点不可见。',
    'D04': '程序应调用、复用还是阻断？允许调用时，反应应尊重哪些已知条件？',
    'D05': '资料允许联合结算吗？允许时，全组后果需要满足哪些约束？',
    'CHAIN': '这条短链应覆盖什么依赖和边界？哪些步骤仍须真实模型产生？',
}
REFS = {'D02': ['R01', 'R02', 'R06'], 'D03': ['R07', 'R08'],
        'D04': ['R07', 'R08'], 'D05': ['R01', 'R07', 'R08'],
        'CHAIN': ['R06', 'R07', 'R08', 'R13']}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()


def rows_bytes(rows):
    return b''.join(canonical_bytes(row) + b'\n' for row in rows)


def build_cards():
    inputs, reviews = [], []
    for (task, split), specs in SECTIONS.items():
        prefix = 'dev' if split == 'development' else 'sealed'
        for index, spec in enumerate(specs, 1):
            identity = f'r1-{prefix}-{task.lower()}-{index:02d}'
            group = identity + '-source'
            inputs.append({'caseId': identity, 'sourceGroup': group,
                           'task': task, 'split': split, 'anchorCase': True,
                           'derivedFrom': None, 'purpose': 'source_card_draft',
                           'stageCut': 'authoring_material_not_model_input',
                           'input': {'sourceCard': {'title': spec['title'],
                                     'facts': spec['facts'], 'question': QUESTIONS[task]}}})
            reviews.append({'caseId': identity, 'sourceGroup': group,
                            'coverageTags': spec['tags'], 'ruleRefs': REFS[task],
                            'sourceNote': spec['title'], 'humanReview': 'pending',
                            'author': 'assistant',
                            'draftExpected': {**spec['expected'],
                                'mustRespect': [spec['must']], 'forbidden': [spec['forbidden']],
                                'acceptableAlternatives': [],
                                'annotationStatus': 'draft_pending_human_review'}})
    return inputs, reviews


def validate_cards(inputs, reviews):
    def require(ok, why):
        if not ok:
            raise ValueError(why)
    require(len(inputs) == len(reviews) == 90, '必须是90张来源卡及配对判据')
    by_id = {r['caseId']: r for r in reviews}
    require(len(by_id) == 90, '判据题号重复')
    require(len({r['caseId'] for r in inputs}) == 90, '来源卡题号重复')
    require(len({r['sourceGroup'] for r in inputs}) == 90, '来源组重复：需重新分组与补足配额')
    require({r['caseId'] for r in inputs} == set(by_id), '卡片与判据未一一对应')
    require(len({r['input']['sourceCard']['facts'] for r in inputs}) == 90, '场景正文完全重复')
    buckets = Counter((r['task'], r['split']) for r in inputs)
    expected = {(t, s): 10 for t in ('D02', 'D03', 'D04', 'D05')
                for s in ('development', 'sealed_candidate')}
    expected.update({('CHAIN', 'development'): 4, ('CHAIN', 'sealed_candidate'): 6})
    require(buckets == expected, '任务/split来源组配额不符')
    for row in inputs:
        review = by_id[row['caseId']]
        require(row['sourceGroup'] == review['sourceGroup'], '来源组与判据串题')
        require(row['purpose'] == 'source_card_draft' and row['stageCut'] == 'authoring_material_not_model_input', '不得冒充执行输入')
        require(row['anchorCase'] is True and row['derivedFrom'] is None, '本版只登记基础卡，派生case须另立同源登记')
        require(set(row['input']) == {'sourceCard'}, '输入混入判据或执行字段')
        require(set(row['input']['sourceCard']) == {'title', 'facts', 'question'}, '来源卡字段不符')
        require(all(isinstance(v, str) and v.strip() for v in row['input']['sourceCard'].values()), '来源卡正文不能为空')
        require(review['humanReview'] == 'pending' and review['draftExpected']['annotationStatus'] == 'draft_pending_human_review', '草稿不得代签人审')
        require(bool(review['draftExpected']['mustRespect']) and bool(review['draftExpected']['forbidden']), '判据缺少必要/禁止约束')
    for split in ('development', 'sealed_candidate'):
        task_rows = {t: [by_id[r['caseId']] for r in inputs if r['task'] == t and r['split'] == split]
                     for t in ('D02', 'D03', 'D04', 'D05')}
        tags = {t: Counter(tag for r in rows for tag in r['coverageTags']) for t, rows in task_rows.items()}
        for tag, count in {'protagonist': 6, 'npc': 4, 'pending': 4, 'consumed': 3,
                           'expired': 3, 'act': 5, 'skip': 5}.items():
            require(tags['D02'][tag] == count, f'{split}/D02/{tag}配额错误')
        for r in task_rows['D02']:
            require(r['draftExpected']['kind'] in r['coverageTags'], '行动标签与判据不一致')
        require(tags['D03']['empty_targets'] >= 3 and tags['D03']['multiple_targets'] >= 3, '目标空集/多目标不足')
        for tag in ('one_target', 'already_acted', 'reaction_as_source', 'cycle', 'same_target_multiple_sources', 'future_admission_hidden'):
            require(tags['D03'][tag] > 0, f'{split}/D03缺覆盖{tag}')
        for t, calls in (('D04', 6), ('D05', 7)):
            require(sum(r['draftExpected'].get('expectedCall') is True for r in task_rows[t]) == calls, f'{split}/{t}语义分母错误')
            require(sum(r['draftExpected'].get('expectedCall') is False for r in task_rows[t]) == 10-calls, f'{split}/{t}守卫分母错误')
        for tag in ('frozen_threat', 'dice_contrast', 'admitted_chain', 'skipped_not_acted', 'multiple_frozen_threats', 'not_admitted', 'already_acted_reuse', 'missing_frozen_source_text', 'missing_judgment'):
            require(tags['D04'][tag] > 0, f'{split}/D04缺覆盖{tag}')
        for tag in ('conflicting_actions', 'multi_member', 'cycle', 'already_acted_judgment', 'denied_relation', 'dice_contrast', 'partial_failure', 'missing_member_action', 'missing_judgment', 'group_not_closed'):
            require(tags['D05'][tag] > 0, f'{split}/D05缺覆盖{tag}')
    chain_tags = {tag for row in inputs if row['task'] == 'CHAIN' for tag in by_id[row['caseId']]['coverageTags']}
    require({'action_empty_targets', 'admission_reaction_targets', 'cycle_termination',
             'same_target_multiple_sources', 'already_acted_judgment', 'skip_then_reaction',
             'conflicting_joint_result', 'freeze_cancel_resume', 'segment_linked_boundary',
             'g03_npc_before_protagonist'} <= chain_tags, '短链计划覆盖不足')
    return {'sourceCardCount': 90, 'proposedSourceGroupCount': 90,
            'developmentGroups': 44, 'sealedCandidateGroups': 46,
            'runtimeCaseCount': None, 'executableInputsBuilt': False,
            'coverageCheck': 'declared_tags_only_not_semantic_approval',
            'humanReview': 'pending', 'sourceIndependence': 'unverified',
            'formalEvaluationAllowed': False, 'modelExecutionAuthorized': False}


def build_files():
    inputs, reviews = build_cards()
    summary = validate_cards(inputs, reviews)
    input_bytes, review_bytes = rows_bytes(inputs), rows_bytes(reviews)
    rules = []
    for path in RULE_PATHS:
        raw = subprocess.check_output(['git', 'show', f'{RULE_COMMIT}:{path}'], cwd=ROOT)
        rules.append({'path': path, 'commit': RULE_COMMIT, 'sha256': digest(raw)})
    coverage = {f'{task}/{split}': {
                    tag: [c['caseId'] for c, r in zip(inputs, reviews)
                          if c['task'] == task and c['split'] == split and tag in r['coverageTags']]
                    for tag in sorted({tag for c, r in zip(inputs, reviews)
                                       if c['task'] == task and c['split'] == split
                                       for tag in r['coverageTags']})}
                for task, split in SECTIONS}
    manifest = {
        'schema': 'jity-d-round1-source-cards-v1', 'createdDate': '2026-10-31',
        'status': 'draft_not_frozen', **summary,
        'authoring': {'author': 'assistant_in_current_codex_conversation',
                      'method': 'new_source_card_drafts_from_rules_and_coverage',
                      'exactAssistantModelConfiguration': 'not_exposed_to_authoring_code',
                      'candidateModelCalls': 0, 'trainingUses': [],
                      'protectedBCSampleBodiesRead': False,
                      'old42ReusedAsNewGroups': False,
                      'semanticIndependenceIncludingOldDAndAcrossSplits': 'pending_human_review'},
        'files': {'source-cards.jsonl': digest(input_bytes), 'rubric-drafts.jsonl': digest(review_bytes)},
        'authoringCode': {name: sha256_file(BASE/name) for name in ('round1_scenarios.py', 'prepare_round1.py')},
        'ruleSources': rules,
        'humanRoles': {'initialReviewer': None, 'secondReviewer': None, 'adjudicator': None},
        'sourceReceipts': {'B': None, 'C': None},
        'declaredCoverage': coverage,
        'executionGaps': ['complete_entity_world_and_original_task_personality_text',
                          'stage_cut_inputs_and_program_judgment_identity',
                          'derived_dice_cases_within_the_same_source_group',
                          'D02_missing_input_and_cancellation_probes',
                          'chain_runner_actual_predictions_and_trace',
                          'all_required_human_and_source_receipts'],
        'groups': [{'sourceGroup': c['sourceGroup'], 'cardId': c['caseId'],
                    'task': c['task'], 'split': c['split'], 'derivedCaseIds': [],
                    'inputSha256': digest(canonical_bytes(c['input'])),
                    'reviewSha256': digest(canonical_bytes(r)),
                    'sourceType': 'assistant_authored_draft', 'humanReview': 'pending'}
                   for c, r in zip(inputs, reviews)],
    }
    manifest_bytes = json_bytes(manifest)
    packet = make_packet(inputs, reviews, digest(input_bytes), digest(review_bytes), digest(manifest_bytes))
    from prepare_review import render_source_cards
    coverage_md = ['# L3 第三步：90 张来源卡的覆盖计划', '',
                   '日期：2026-10-31。来源卡草稿，未冻结、未运行；标签配额核对不证明场景语义已覆盖。', '',
                   '开发 44 组（四任务各 10 + 短链 4）；封存候选 46 组（四任务各 10 + 短链 6）。',
                   '90 是拟议来源组/基础卡数；可执行 case 数和调用数仍未知。骰点派生必须留在同组同 split。',
                   '新卡本人初审 0/90；原 42 题意见不迁入。B/C、D 内部及跨 split 的语义同源复核均待完成。', '',
                   '| 卡片 | 用途 | 场景 | 计划覆盖标签 |', '|---|---|---|---|']
    for c, r in zip(inputs, reviews):
        label = '开发' if c['split'] == 'development' else '封存候选（未冻结）'
        coverage_md.append(f"| {c['caseId']} | {label} | {r['sourceNote']} | {', '.join(r['coverageTags'])} |")
    coverage_md += ['', '未完成：完整实体/任务/个性原文、阶段投影、骰点身份与同源派生、D02 缺输入/取消探针、短链运行器、人审和来源回执。',
                    '这些卡片不能传给候选模型或用于训练；正式筛选仍需完整协议与独立核验。', '']
    return {DATA/'source-cards.jsonl': input_bytes,
            DATA/'rubric-drafts.jsonl': review_bytes,
            DATA/'source-manifest.json': manifest_bytes,
            ARTIFACTS/'l3-3-source-coverage.md': '\n'.join(coverage_md).encode('utf-8'),
            ARTIFACTS/'l3-3-source-review.html': render_source_cards(packet).encode('utf-8')}, summary


def make_packet(inputs, reviews, input_hash, review_hash, provenance_hash):
    by_id = {r['caseId']: r for r in reviews}
    return {'schema': 'jity-d-human-review-packet-v1', 'materialKind': 'source_card_draft',
            'inputSha256': input_hash, 'reviewDraftSha256': review_hash,
            'provenanceSha256': provenance_hash,
            'cases': [{**c, 'inputSha256': digest(canonical_bytes(c['input'])),
                       'reviewSha256': digest(canonical_bytes(by_id[c['caseId']])),
                       'review': by_id[c['caseId']],
                       'guard': {'reason': 'source_card_not_executable'}} for c in inputs]}


def build_packet():
    inputs, reviews = load_jsonl(DATA/'source-cards.jsonl'), load_jsonl(DATA/'rubric-drafts.jsonl')
    validate_cards(inputs, reviews)
    expected_files, _ = build_files()
    for path, expected in expected_files.items():
        if path.parent == DATA and path.read_bytes() != expected:
            raise ValueError(f'来源卡/登记已改版，须重新生成并复核：{path.name}')
    return make_packet(inputs, reviews, sha256_file(DATA/'source-cards.jsonl'),
                       sha256_file(DATA/'rubric-drafts.jsonl'), sha256_file(DATA/'source-manifest.json'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--write-new', action='store_true', help='独占新建；已有不同内容一律拒绝覆盖')
    args = parser.parse_args()
    files, summary = build_files()
    # Preflight every path before any mutation; never replace an existing draft.
    for path, content in files.items():
        if path.exists() and path.read_bytes() != content:
            raise ValueError(f'已有版本不同，不能覆盖：{path}')
        if args.check and not path.exists():
            raise ValueError(f'缺交付文件：{path}')
    if args.write_new:
        for path, content in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                with path.open('xb') as stream:
                    stream.write(content)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
