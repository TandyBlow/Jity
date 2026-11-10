"""Annotate the 20 API natural first outputs as pilot samples.

These labels are assistant drafts over real API text, not gold.  The raw call
metadata is retained so the natural stratum can be separated from authored
targeted cases.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import short_d02_checkers as checkers
from d02_pilot import ROOT, WORLDS, build_audits, document, expected_for, locate

RAW = ROOT / 'api' / 'natural-raw.jsonl'
OUT = ROOT / 'api-natural.jsonl'


def N(surface, roles, entity=None, basis='name', status='bound', diagnostic=(), occurrence=0,
      candidates=()):
    return {'surface': surface, 'roles': roles, 'entityId': entity, 'basis': basis,
            'status': status, 'diagnostic': list(diagnostic),
            'occurrence': occurrence, 'candidates': list(candidates)}


def I(code, surface, scope='main', blocking=True, step='s1'):
    return {'code': code, 'surface': surface, 'scope': scope,
            'blocking': blocking, 'stepId': step}


ANNOTATIONS = {
    'harbor-gate': dict(
        mentions=[N('林澈', ['subject'], 'lin'), N('铁门', ['object'], 'door'),
                  N('铜钥匙', ['tool'], 'key')],
        label='attempt', issues=[], mustCodes=[], tags=['explicit_name', 'natural_api'],
        note='含“尝试开锁”，没有提前写结果；仓库旁只作背景。'),
    'harbor-crate': dict(
        mentions=[N('林澈', ['subject'], 'lin', occurrence=0),
                  N('木箱', ['object'], 'crate', occurrence=0),
                  N('林澈', ['subject'], 'lin', occurrence=1),
                  N('周岚', ['subject'], 'zhou'),
                  N('木箱', ['object'], 'crate', occurrence=1),
                  N('码头', [], 'dock', diagnostic=['path']),
                  N('林澈', ['subject'], 'lin', occurrence=2),
                  N('胶带', ['tool'], 'tape'),
                  N('木箱', ['object'], 'crate', occurrence=2)],
        label='attempt', issues=[I('condition_scope', '要是木箱太滑或太重',
                                   'condition', False, 's3')],
        mustCodes=['diagnostic_role_requires_review'],
        tags=['explicit_name', 'joint_subject', 'path_diagnostic', 'condition', 'natural_api'],
        note='第二、三步是计划；码头是搬运行进方向，未写成已到达。'),
    'harbor-lamp': dict(
        mentions=[N('林澈', ['subject'], 'lin', occurrence=0),
                  N('提灯', ['object'], 'lamp', occurrence=0),
                  N('木箱', ['destination'], 'crate'),
                  N('林澈', ['subject'], 'lin', occurrence=1),
                  N('胶带', ['tool'], 'tape'),
                  N('提灯', ['object'], 'lamp', occurrence=1),
                  N('林澈', ['subject'], 'lin', occurrence=2)],
        label='attempt', issues=[], mustCodes=[], tags=['explicit_name', 'natural_api'],
        note='灯罩按提灯部件处理；全部为检查／缠紧步骤，没有断言灯火已恢复。'),
    'harbor-wait': dict(
        mentions=[N('林澈', ['subject'], 'lin', occurrence=0),
                  N('仓库', ['destination'], 'warehouse'),
                  N('提灯', ['object'], 'lamp'),
                  N('林澈', ['subject'], 'lin', occurrence=1)],
        label='attempt', issues=[], mustCodes=[], tags=['explicit_name', 'natural_api'],
        note='走进仓库是目的地；木箱旁和铁门位置只作背景，不参与角色。'),
    'harbor-key': dict(
        mentions=[N('林澈', ['subject'], 'lin', occurrence=0),
                  N('周岚', ['recipient'], 'zhou', occurrence=0),
                  N('铜钥匙', ['object'], 'key'),
                  N('她', ['recipient'], 'zhou', basis='pronoun', occurrence=0),
                  N('林澈', ['subject'], 'lin', occurrence=1),
                  N('周岚', ['recipient'], 'zhou', occurrence=1),
                  N('提灯', ['object'], 'lamp', occurrence=0),
                  N('她', ['recipient'], 'zhou', basis='pronoun', occurrence=1),
                  N('自己', ['recipient'], 'lin', basis='pronoun'),
                  N('林澈', ['subject'], 'lin', occurrence=2),
                  N('周岚', [], 'zhou', diagnostic=['source'], occurrence=2),
                  N('提灯', ['object'], 'lamp', occurrence=1)],
        label='mixed', issues=[I('unsettled_result', '接过提灯', 'main', True, 's3')],
        mustCodes=['reference_requires_review', 'diagnostic_role_requires_review'],
        tags=['pronoun', 'source_diagnostic', 'result_assertion', 'natural_api'],
        note='第三句“接过”断言提灯已经转移；前两句仍是指代和请求。'),
    'archive-badge': dict(
        mentions=[N('余荞', ['subject'], 'yu'),
                  N('借阅牌', ['object'], 'badge', occurrence=0),
                  N('郑栖', ['recipient'], 'zheng'),
                  N('郑栖', ['subject'], 'zheng', occurrence=1),
                  N('借阅牌', ['object'], 'badge', occurrence=1),
                  N('登记簿', ['object'], 'ledger')],
        label='mixed', issues=[I('unsettled_result', '接过借阅牌', 'main', True, 's2')],
        mustCodes=['actor_mismatch'], tags=['actor_mismatch', 'result_assertion', 'natural_api'],
        note='第二步主体是郑栖，不是当前执行人余荞；且“接过”是已发生结果。'),
    'archive-ledger': dict(
        mentions=[N('余荞', ['subject'], 'yu', occurrence=0),
                  N('印章', ['object'], 'stamp', occurrence=0),
                  N('档案柜', [], 'cabinet', diagnostic=['static_location']),
                  N('登记簿', ['object'], 'ledger', occurrence=0),
                  N('余荞', ['subject'], 'yu', occurrence=1),
                  N('登记簿', ['object'], 'ledger', occurrence=1),
                  N('印章', ['tool'], 'stamp', occurrence=1),
                  N('余荞', ['subject'], 'yu', occurrence=2),
                  N('印章', ['object'], 'stamp', occurrence=2),
                  N('档案柜', ['destination'], 'cabinet', occurrence=1),
                  N('登记簿', ['object'], 'ledger', occurrence=2)],
        label='attempt', issues=[], mustCodes=['diagnostic_role_requires_review'],
        tags=['explicit_name', 'static_location', 'natural_api'],
        note='从档案柜取出是来源场所，不是目的地；其余为检查／按压动作。'),
    'archive-cabinet': dict(
        mentions=[N('余荞', ['subject'], 'yu', occurrence=0),
                  N('登记簿', ['object'], 'ledger', occurrence=0),
                  N('她', ['subject'], 'yu', basis='pronoun'),
                  N('登记簿', ['object'], 'ledger', occurrence=1),
                  N('档案柜', ['destination'], 'cabinet', occurrence=0),
                  N('余荞', ['subject'], 'yu', occurrence=1),
                  N('档案柜', ['object'], 'cabinet', occurrence=1)],
        label='mixed', issues=[I('unsettled_result', '推合到位', 'main', True, 's3')],
        mustCodes=['reference_requires_review', 'unsettled_result'],
        tags=['pronoun', 'result_assertion', 'natural_api'],
        note='她回指余荞；最后一句把柜门推合写成到位结果。'),
    'archive-quote': dict(
        mentions=[N('余荞', ['subject'], 'yu', occurrence=0),
                  N('借阅牌', ['object'], 'badge'),
                  N('信封', ['destination'], 'envelope'),
                  N('余荞', ['subject'], 'yu', occurrence=1),
                  N('阅览室', [], 'room', diagnostic=['static_location']),
                  N('郑栖', [], 'zheng', diagnostic=['topic'])],
        label='mixed', issues=[I('unsettled_result', '封好封口', 'main', True, 's1')],
        mustCodes=['diagnostic_role_requires_review', 'unsettled_result'],
        tags=['result_assertion', 'static_location', 'topic', 'natural_api'],
        note='封好封口是结果断言；喊名字的目标是话题，不是接收人。'),
    'archive-ambig': dict(
        mentions=[N('余荞', ['subject'], 'yu', occurrence=0),
                  N('印章', ['object'], 'stamp', occurrence=0),
                  N('阅览桌', ['destination'], 'desk'),
                  N('余荞', ['subject'], 'yu', occurrence=1),
                  N('印章', ['object'], 'stamp', occurrence=1)],
        label='mixed', issues=[I('unsettled_result', '放稳', 'main', True, 's2')],
        mustCodes=['unsettled_result'], tags=['result_assertion', 'natural_api'],
        note='“放稳”是对目标状态的断言；本世界“印章”不歧义。'),
    'workshop-bowl': dict(
        mentions=[N('唐霁', ['subject'], 'tang', occurrence=0),
                  N('染料碗', ['object'], 'bowl', occurrence=0),
                  N('唐霁', ['subject'], 'tang', occurrence=1),
                  N('染料碗', ['object'], 'bowl', occurrence=1),
                  N('晾架', ['destination'], 'rack')],
        label='attempt', issues=[], mustCodes=[], tags=['explicit_name', 'natural_api'],
        note='端起、走向都是计划步骤，未写到达或放稳。'),
    'workshop-rod': dict(
        mentions=[N('唐霁', ['subject'], 'tang'),
                  N('染料碗', ['object'], 'bowl', occurrence=0),
                  N('搅拌棒', ['object'], 'rod', occurrence=0),
                  N('他', ['subject'], 'tang', basis='pronoun'),
                  N('搅拌棒', ['tool'], 'rod', occurrence=1)],
        label='attempt', issues=[], mustCodes=['reference_requires_review'],
        tags=['pronoun', 'natural_api'], note='“他”回指唐霁；搅动是尝试动作。'),
    'workshop-cloth': dict(
        mentions=[N('唐霁', ['subject'], 'tang'),
                  N('吸水纸', ['object'], 'paper', occurrence=0),
                  N('他', ['subject'], 'tang', basis='pronoun', occurrence=0),
                  N('吸水纸', ['tool'], 'paper', occurrence=1),
                  N('样布', ['object'], 'cloth', occurrence=0),
                  N('他', ['subject'], 'tang', basis='pronoun', occurrence=1),
                  N('吸水纸', ['tool'], 'paper', occurrence=2),
                  N('样布', ['object'], 'cloth', occurrence=1)],
        label='attempt', issues=[], mustCodes=['reference_requires_review'],
        tags=['pronoun', 'natural_api'], note='两处“他”都回指唐霁；查看干湿不是结果断言。'),
    'workshop-newentity': dict(
        mentions=[N('唐霁', ['subject'], 'tang', occurrence=0),
                  N('搅拌棒', ['object'], 'rod', occurrence=0),
                  N('他', ['subject'], 'tang', basis='pronoun'),
                  N('搅拌棒', ['object'], 'rod', occurrence=1),
                  N('染料碗', ['object'], 'bowl'),
                  N('唐霁', ['subject'], 'tang', occurrence=1),
                  N('吸水纸', ['tool'], 'paper'),
                  N('样布', ['tool'], 'cloth'),
                  N('晾架', [], 'rack', diagnostic=['static_location'])],
        label='attempt', issues=[I('condition_scope', '若仍不牢固',
                                   'condition', False, 's3')],
        mustCodes=['reference_requires_review', 'diagnostic_role_requires_review'],
        tags=['pronoun', 'static_location', 'condition', 'natural_api'],
        note='条件句内的“若仍不牢固”不是断言；晾架旁是静态场所。'),
    'workshop-bench': dict(
        mentions=[N('唐霁', ['subject'], 'tang', occurrence=0),
                  N('染料碗', ['object'], 'bowl', occurrence=0),
                  N('唐霁', ['subject'], 'tang', occurrence=1),
                  N('染料碗', ['object'], 'bowl', occurrence=1),
                  N('配色台', ['destination'], 'bench', occurrence=0),
                  N('唐霁', ['subject'], 'tang', occurrence=2),
                  N('染料碗', ['object'], 'bowl', occurrence=2),
                  N('配色台', ['destination'], 'bench', occurrence=1)],
        label='attempt', issues=[], mustCodes=[], tags=['explicit_name', 'natural_api'],
        note='最后是“查看是否稳稳落在”，不是断言已经放稳。'),
    'signal-radio': dict(
        mentions=[N('周苇', ['subject'], 'wei', occurrence=0),
                  N('信号机', ['object'], 'radio', occurrence=0),
                  N('值守室', [], 'room', diagnostic=['static_location']),
                  N('备用线', ['object'], 'cable'),
                  N('电池', ['object'], 'battery'),
                  N('信号机', ['object'], 'radio', occurrence=1),
                  N('谢迟', ['recipient'], 'xie')],
        label='mixed', issues=[I('unsettled_result', '调好信号机频率', 'main', True, 's1')],
        mustCodes=['diagnostic_role_requires_review', 'unsettled_result'],
        tags=['result_assertion', 'static_location', 'natural_api'],
        note='“连接好／调好”写成完成结果；值守室只是场所。'),
    'signal-cable': dict(
        mentions=[N('周苇', ['subject'], 'wei', occurrence=0),
                  N('备用线', ['object'], 'cable', occurrence=0),
                  N('周苇', ['subject'], 'wei', occurrence=1),
                  N('信号机', ['destination'], 'radio', occurrence=0),
                  N('备用线', ['object'], 'cable', occurrence=1),
                  N('周苇', ['subject'], 'wei', occurrence=2),
                  N('备用线', ['object'], 'cable', occurrence=2),
                  N('信号机', ['object'], 'radio', occurrence=1)],
        label='mixed', issues=[I('unsettled_result', '插紧', 'main', True, 's3')],
        mustCodes=['unsettled_result'], tags=['result_assertion', 'natural_api'],
        note='“确认备用线插紧”断言了连接状态。'),
    'signal-gate': dict(
        mentions=[N('周苇', ['subject'], 'wei'),
                  N('锁紧销', ['object'], 'pin', occurrence=0),
                  N('道口闸门', ['object'], 'gate', occurrence=0),
                  N('锁紧销', ['object'], 'pin', occurrence=1),
                  N('闸门', ['destination'], 'gate', basis='alias', occurrence=1),
                  N('闸门', ['object'], 'gate', basis='alias', occurrence=2)],
        label='attempt', issues=[], mustCodes=['unresolved_role_subject', 'alias_requires_review'],
        overrides={'s2': {'subject': {'status': 'insufficient', 'mentionIds': []}},
                   's3': {'subject': {'status': 'insufficient', 'mentionIds': []}}},
        implicit=['s2', 's3'], tags=['implicit_subject', 'natural_api'],
        note='第二、三步省略主语；程序必须报信息不足，不能补周苇。'),
    'signal-background': dict(
        mentions=[N('周苇', ['subject'], 'wei', occurrence=0),
                  N('值守室', [], 'room', diagnostic=['static_location']),
                  N('备用线', ['object'], 'cable', occurrence=0),
                  N('周苇', ['subject'], 'wei', occurrence=1),
                  N('备用线', ['object'], 'cable', occurrence=1)],
        label='attempt', issues=[], mustCodes=['diagnostic_role_requires_review'],
        tags=['static_location', 'natural_api'], note='值守室只是出处场所，不是目的地。'),
    'signal-hope': dict(
        mentions=[N('周苇', ['subject'], 'wei', occurrence=0),
                  N('信号机', ['object'], 'radio', occurrence=0),
                  N('备用线', ['object'], 'cable', occurrence=0),
                  N('他', ['subject'], 'wei', basis='pronoun', occurrence=0),
                  N('电池', ['object'], 'battery'),
                  N('备用线', ['object'], 'cable', occurrence=1),
                  N('信号机', ['object'], 'radio', occurrence=1),
                  N('他', ['subject'], 'wei', basis='pronoun', occurrence=1),
                  N('值守室', [], 'room', diagnostic=['static_location'])],
        label='attempt', issues=[], mustCodes=['reference_requires_review',
                                                'diagnostic_role_requires_review'],
        tags=['pronoun', 'static_location', 'natural_api'],
        note='两处“他”回指周苇；等待恢复是尝试，不是结果断言。'),
}


def build():
    raw = [json.loads(line) for line in RAW.read_text().splitlines() if line.strip()]
    samples = []
    failures = []
    for meta in raw:
        group = meta['scenarioGroup']
        ann = ANNOTATIONS.get(group)
        if ann is None:
            continue
        text, steps = document(meta['text'].split('\n'))
        case = {
            'text': meta['text'], 'bindings': ann['mentions'],
            'label': ann['label'], 'exprIssues': ann['issues'],
            'roleOverride': ann.get('overrides', {}),
            'implicit': False,
        }
        try:
            built = build_audits(group + ':natural', case, WORLDS[meta['worldId']],
                                 meta['actorId'])
        except ValueError as exc:
            raise SystemExit('locate failure at ' + group + ': ' + str(exc))
        role, expr = built['roleAudit'], built['expressionAudit']
        for step_id in ann.get('implicit', []):
            role['issues'].append({'code': 'implicit_subject',
                                   'message': 'subject omitted from the sentence',
                                   'blocking': True, 'stepId': step_id, 'scope': 'main'})
        m1 = checkers.validate_role_audit(built['text'], built['steps'], role,
                                          WORLDS[meta['worldId']], meta['actorId'])
        m2 = checkers.validate_expression_audit(built['text'], built['steps'], expr)
        combined = checkers.combine(m1, m2)
        codes = {row['code'] for row in combined.issues}
        missing = set(ann['mustCodes']) - codes
        if missing:
            failures.append({'sample': group, 'missing': sorted(missing),
                             'got': sorted(codes)})
        expected = expected_for(ann['mustCodes'], ann['label'])
        if (m1.decision, m2.decision, combined.decision) != expected:
            failures.append({'sample': group, 'expected': expected,
                             'got': [m1.decision, m2.decision, combined.decision]})
        samples.append({
            'schema': 'jity-d02-checker-pilot-sample-v1',
            'sampleId': group + ':natural',
            'scenarioGroup': group,
            'split': meta['split'],
            'source': 'api_first_output',
            'worldId': meta['worldId'],
            'actorId': meta['actorId'],
            'text': built['text'],
            'steps': built['steps'],
            'roleAudit': role,
            'expressionAudit': expr,
            'expected': {'m1': expected[0], 'm2': expected[1],
                         'combined': expected[2]},
            'tags': ann['tags'] + ['api_first_output'],
            'annotationStatus': 'assistant_draft_pending_human',
            'reviewNote': ann['note'] + ' API 首输出，助手草稿标注，非金标准。',
            'apiMeta': {key: meta.get(key) for key in
                        ('prompt', 'finishReason', 'usage', 'estimatedCny',
                         'latencyMs', 'requestId')},
        })
    if failures:
        raise SystemExit('natural annotation failures:\n' +
                         json.dumps(failures, ensure_ascii=False, indent=2))
    OUT.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in samples))
    print('wrote', OUT, 'samples', len(samples))


if __name__ == '__main__':
    build()
