"""Assistant-authored semantic-abstention diagnostic variants, data only.

No runtime model imports this helper. The twelve variants reuse existing source
groups/splits and are not independent sources. Missing semantic instructions are
different from missing world fields, unknown attempt outcomes, or an explicit
choice to skip. Original rows are never modified.
"""
from copy import deepcopy
import json

from run_pilot import digest


MATERIALS = {
    'buoy': ('浮标接线补充方案', '接线的指定后续步骤'),
    'archive': ('借阅手续三步清单', '核验后指定的办理步骤'),
    'dye': ('染料交接附件', '交接时指定的额外处理'),
    'swap': ('校准箱转移补充方案', '转移后指定的检查步骤'),
    'drying': ('海图干燥操作附件', '干燥后指定的局部处理'),
    'conditional': ('种子盒封口处理清单', '封口检查后指定的条件步骤'),
    'missing': ('陶碗测量三步附件', '尺寸记录后的指定步骤'),
    'signal': ('道路封闭通知补充方案', '通知后指定的后续联络'),
    'gate': ('防潮闸检查附件', '关闸后的指定检查步骤'),
    'waiting': ('稳定观测补充清单', '观测结束后的指定操作'),
    'jointlift': ('标本托盘交接附件', '托盘交接后的指定处理'),
    'newentity': ('校时钟调整补充方案', '校时后的指定检查步骤'),
}


def _finish(row, original, suffix, rationale):
    row['exampleId'] = original['exampleId'] + ':semantic-abstention:' + suffix
    row['derivedFromAnnotation'] = original['exampleId']
    row['derivedFromSha256'] = original['contentSha256']
    row['inputProvenance'] = 'authored_semantic_abstention_diagnostic_same_source'
    row['annotationStatus'] = 'assistant_draft'
    row['sourceStatus'] = 'unverified'
    row['reviewStatus'] = 'pending_human'
    row['holdoutStatus'] = ('open_holdout_previously_inspected' if row['split'] == 'test'
                            else 'same_source_revision')
    row['previousExposure'] = ['short-intent-20261109-r1', 'short-all-20261109-r3']
    row['authorRationale'] = rationale
    row['semanticIndependence'] = 'same_source_template_variant_not_new_source'
    row['contentSha256'] = digest({k: v for k, v in row.items() if k != 'contentSha256'})
    return row


def authored_semantic_abstentions(rows):
    """Return 60 new rows from all 12 existing sources, without writing files.

    Per source: D02 missing instruction / deliberate skip / fully stated attempt
    controls; D05 complete aggregate diagnostic and its new incomplete primitive.
    The trainer updates all old/new vocabularies together in a new frozen batch.
    """
    bases = {}
    for row in rows:
        component = row['component']
        if component not in ('D02.1', 'D05.2'):
            continue
        if component == 'D02.1' and row['target'] != 'act':
            continue
        if component == 'D05.2' and row['kind'] != 'annotation_only':
            continue
        bases.setdefault(row['sourceGroup'], {}).setdefault(component, row)
    output = []
    for group, originals in sorted(bases.items()):
        scene = group.rsplit(':', 1)[-1]
        if scene not in MATERIALS or set(originals) != {'D02.1', 'D05.2'}:
            raise ValueError('abstention source requires matching D02/D05 material: ' + group)
        title, missing_detail = MATERIALS[scene]
        base = originals['D02.1']
        actor = base['input']['context']['actorId']
        name = base['input']['context']['world']['initial']['characters'][actor]['name']
        joint_base = originals['D05.2']
        member = next(m for m in joint_base['input']['context']['group']['members'] if m['memberId'] == actor)
        controls = (
            ('missing_instructions', 'incomplete',
             f'本次只让{name}严格执行《{title}》中的全部指定步骤。附件正文尚未提供，'
             f'其中的{missing_detail}没有写在当前输入或世界中。不要自行补写、省略或改做其他行动。',
             f'世界、任务、人物及消费状态完整，但玩家把本次行动唯一限定为未提供的《{title}》；'
             f'缺少{missing_detail}，无法确定完整意图。不能把缺资料改为主动skip或自行规划替代动作。'),
            ('explicit_skip', 'skip',
             f'{name}在本次行动机会明确不行动；不要启动当前任务，也不要提出替代行动。',
             '玩家明确选择本机会不行动；不是资料缺失，也不是把模型不能判断伪装成skip。'),
            ('attempt_without_promised_success', 'act',
             '请完整执行以下尝试，不要求预先保证成功；原文中的条件仍然适用：\n' + member['actionText'],
             '尝试的主体、对象、步骤及条件已在完整上下文和行动原文中给出。结果尚未知并不妨碍提出尝试，不能因无成功保证而弃答。'),
        )
        for suffix, target, text, rationale in controls:
            row = deepcopy(base)
            row['labels'] = ['act', 'skip', 'incomplete']
            row['target'] = target
            row['input']['context']['advance']['inputText'] = text
            row['input']['context']['advance']['intentStatus'] = 'pending'
            if target == 'incomplete':
                row['semanticAbstention'] = {
                    'kind': 'required_material_missing', 'expectedComponent': 'D02.1',
                    'expectedAttemptIds': [], 'expectedCompletion': 'incomplete',
                    'expectedReason': 'semantic_incomplete:D02.1'}
                row['expectedProgramCompletion'] = 'incomplete'
                row['expectedProgramReason'] = 'semantic_incomplete:D02.1'
            else:
                row['abstentionControl'] = target
            output.append(_finish(row, base, suffix, rationale))

        # Defensive D05 diagnostic. D02 should not admit the unspecified step;
        # a legacy/restored supplied action is nevertheless not a license for
        # D05 to fabricate its result. Existing world/rolls/actions are retained,
        # and the appended step is explicitly after the original attempts.
        row = deepcopy(joint_base)
        payload = row['input']
        members = payload['context']['group']['members']
        member = next(m for m in members if m['memberId'] == actor)
        attempt_id = actor + ':fragment-missing-supplement'
        if attempt_id in {a['attemptId'] for a in payload['attempts']}:
            raise ValueError('abstention attempt identity collision')
        text = (f'在上述已有尝试结束之后，{name}还尝试执行《{title}》规定的{missing_detail}；'
                '本轮输入没有该补充方案正文。')
        if 'fragments' not in member:
            raise ValueError('abstention diagnostics require original frozen fragments')
        member['fragments'].append({'id': attempt_id, 'text': text})
        member['actionText'] = '\n'.join(f['text'] for f in member['fragments'])
        # The source is a new authored alternative, never a patched service
        # receipt. Existing drafts currently have no service actionDigest.
        if 'actionDigest' in member:
            raise ValueError('cannot rewrite a claimed service-frozen action')
        payload['attempts'].append({'attemptId': attempt_id, 'memberId': actor, 'text': text})
        payload['inputHash'] = digest(payload['context'])
        joint = json.loads(row['target'])
        joint['judgments'].append({'attemptId': attempt_id, 'label': 'incomplete'})
        row['target'] = json.dumps(joint, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        reason = 'semantic_incomplete:D05.2:' + attempt_id
        row['expectedProgramCompletion'] = 'incomplete'
        row['expectedProgramReason'] = reason
        row['semanticAbstention'] = {'kind': 'required_material_missing', 'expectedComponent': 'D05.2',
                                   'expectedAttemptIds': [attempt_id], 'expectedCompletion': 'incomplete',
                                   'expectedReason': reason}
        rationale = (f'防御诊断，不声称D02应接受该行动：在同源已指定尝试之后追加《{title}》的未知步骤，'
                     f'全部世界、实际骰点和既有尝试保留，但{missing_detail}未提供。新增尝试不能判成功、部分成功或失败；'
                     '原尝试标签仅沿用此助手同源诊断设定，未有人审，整体不得继续生成结果事实。')
        row = _finish(row, joint_base, 'missing_supplement_joint', rationale)
        output.append(row)
        primitive = deepcopy(row)
        primitive.update(component='D05.2.label', kind='label', outputCodec='scalar',
                         labels=['achieved', 'partial', 'not_achieved', 'incomplete'], target='incomplete')
        primitive['input']['semanticQuery'] = {'attemptId': attempt_id}
        for key in ('semanticAbstention', 'expectedProgramCompletion', 'expectedProgramReason'):
            primitive.pop(key, None)
        primitive['abstentionPrimitive'] = True
        primitive['derivedFromAnnotation'] = row['exampleId']
        primitive['derivedFromSha256'] = row['contentSha256']
        primitive['exampleId'] = row['exampleId'] + ':primitive-incomplete'
        primitive['contentSha256'] = digest({k: v for k, v in primitive.items() if k != 'contentSha256'})
        output.append(primitive)
    if {group.rsplit(':', 1)[-1] for group in bases} != set(MATERIALS):
        raise ValueError('all twelve existing source groups required; no invented source fallback')
    return output
