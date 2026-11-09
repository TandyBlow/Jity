"""Assistant-authored partial-achievement joint diagnostics; never inference.

Each variant is a newly constructed closed group and initial world, with new
identities. It reuses its original source group/split, not a production receipt
or an independent source. Complete constructed dice inputs govern admission,
not success. Semantic labels below are authored supervision pending review.
"""
from copy import deepcopy
import json

from run_pilot import digest


# Every limitation is present in the actual input world, not only a rubric.
# These cases mix material limits, mechanical obstruction, geometry, access,
# partial information obtainable by an action, and one explicit timed subgoal.
SCENES = {
 'buoy': {
  'object': '接线端松脱，可用绝缘钳夹紧；灯丝已经烧断，现有工具不能修复灯丝，世界中没有替换灯丝。',
  'tool': '绝缘钳完好，能够夹紧暴露的接线端，不能修复断裂灯丝。',
  'action': '{a}尝试在{b}稳住外壳时，用绝缘钳夹紧浮标灯的接线端并恢复照明。',
  'reaction': '{b}尝试为{a}稳住浮标灯的外壳。',
  'reason': '夹紧可接触的接线端这一明确子目标可以完成；断裂灯丝仍使照明无法恢复。不是全部失败，也不是缺少灯丝状态资料。'},
 'archive': {
  'object': '借阅牌完好，正由核验员拿着准备交出。',
  'tool': '封存夹的夹口被断裂的内部卡销卡死在闭合位置，现有工具无法打开夹口。',
  'action': '{a}尝试接过{b}递来的借阅牌，并把借阅牌夹入封存夹。',
  'reaction': '{b}尝试把手中的借阅牌交到{a}空出的左手。',
  'objectContainer': 'b',
  'reason': '双方交接方向一致且左手空闲，借阅牌可以交到行动者手中；封存夹有明确机械卡死，不能完成夹入。'},
 'dye': {
  'object': '染料碗中有两块松软、可被搅拌棒压碎的染料结块，另有一块与碗底烧结固定的硬结；现有搅拌棒不能破坏硬结。',
  'tool': '搅拌棒完好，能压碎松软结块；强度不足以破坏碗底烧结硬块。',
  'action': '{a}尝试在{b}稳住染料碗时，用搅拌棒压碎碗中全部结块。',
  'reaction': '{b}尝试为{a}稳住染料碗。',
  'reason': '可压碎的两块软结有明确达成，固定硬结不能被当前工具破坏；全部结块只清理一部分，信息完整。'},
 'swap': {
  'object': '校准箱箱角裸露，护角垫尺寸合适，可以直接包住箱角；箱体完好。',
  'tool': '护角垫完好，展开后可稳固包住校准箱的四个箱角。',
  'far': '仪器储存间唯一入口的门已锁死，门上没有可操作的外侧开锁机构；当前世界没有可用开锁工具。',
  'action': '{a}尝试在{b}让开时包好校准箱的护角，并把箱子送入仪器储存间。',
  'reaction': '{b}尝试退到{a}身侧，让出包护角和搬箱子的空间。',
  'objectContainer': 'a',
  'reason': '伙伴让开后可以包好匹配的护角，明确完成保护子目标；入口仍锁死，搬入存放间不成立，不把已包装的事实抹成完全失败。'},
 'drying': {
  'object': '海图表面有少量游离水珠，纸纤维内部已浸湿；仅靠表面轻压不能排尽纤维内部水分。',
  'tool': '吸水纸干燥且完好，足以吸走全部表面游离水珠，不能通过轻压抽干海图纤维内部水分。',
  'action': '{a}尝试在{b}稳住海图时，用吸水纸轻压并把整张海图完全弄干。',
  'reaction': '{b}尝试为{a}稳住海图边缘。',
  'reason': '表面游离水可被吸走，湿润程度有明确减少；内部纤维仍湿，完全干燥未达成。不是把等待时间短自动标partial。'},
 'conditional': {
  'object': '种子盒盖被内部锁扣锁死，当前世界没有可用开锁工具；盒盖外贴着已经松脱、徒手可揭下的封口签。',
  'tool': '封口签已松脱，轻轻一揭即可取下；封口签本身不是开锁工具。',
  'toolContainer': 'object',
  'action': '{a}尝试在{b}扶稳种子盒时，取下封口签并打开盒盖。',
  'reaction': '{b}尝试为{a}扶稳种子盒。',
  'reason': '松脱封口签可以取下，开锁条件明确不具备，盒盖不能打开；两个目标中仅一个成立，不是未知条件造成的弃答。'},
 'missing': {
  'object': '残缺陶碗的外沿缺口完全暴露，可供软尺测宽；内侧裂隙被固定不透明封盖遮住，现有工具不能拆开封盖。',
  'tool': '软尺刻度完整，能贴合暴露外沿；不能穿透不透明封盖或拆卸固定封盖。',
  'action': '{a}尝试在{b}扶稳残缺陶碗时，用软尺测出外沿缺口宽度和封盖下裂隙的深度。',
  'reaction': '{b}尝试为{a}扶稳残缺陶碗。',
  'reason': '外沿宽度可实测，封盖下深度无法由当前动作获得；已获得一个指定测量值，另一个未获得。未知测量值不等于输入缺少动作定义。'},
 'signal': {
  'object': '信号机本地插座完整，装好匹配插头即可接通本地接口；通往远端值守室的线路在站外彻底断开，本地插头操作不能修复远端线路。',
  'tool': '备用插头与本地插座匹配，插入即可固定接通本地接口。',
  'action': '{a}尝试在{b}扶稳信号机时插好备用插头，并用信号机向{off}发送道路封闭通知。',
  'reaction': '{b}尝试为{a}扶稳信号机。',
  'offTarget': True,
  'reason': '匹配插头可完成本地连接；已知站外断线使远端通知无法送达。远端人物的拒绝准入只决定是否反应，不是通信失败的因果。'},
 'gate': {
  'object': '闸门手柄活动顺畅，可压到关闭位置；关闭位置的销孔内径为3毫米，销孔为不可扩张的刚性金属。',
  'tool': '锁紧销直径为4毫米，材质为不可压缩的硬金属，当前工具不能削小它。',
  'action': '{a}尝试在{b}扶住闸门手柄时，把手柄压到关闭位置并插入锁紧销固定。',
  'reaction': '{b}尝试协助{a}扶住闸门手柄，避免手柄偏转。',
  'reason': '手柄可到关闭位置；尺寸不匹配使插销固定不成立。明确完成关闭子目标，不以准入骰点推导全部成功。'},
 'waiting': {
  'object': '记录仪的增益旋钮活动正常，目前在低档，规定档位为中档；稳定观测需要连续保持五分钟，当前观测刚开始。',
  'tool': '计时表完整可用，当前观测计时为零分钟。',
  'action': '{a}尝试在{b}保持安静时，把记录仪增益调到中档并完成连续五分钟稳定观测。',
  'reaction': '{b}尝试保持安静，不碰动{a}正在调整的记录仪。',
  'seconds': 120,
  'reason': '旋钮调到中档是独立且可完成的明确子目标；本结算点只推进两分钟，五分钟观测尚未完成。partial依据包含实际调档成果，不是时间不足一律partial。'},
 'jointlift': {
  'object': '标本托盘宽120厘米，两人可平稳抬起；标本固定方式要求托盘始终水平，不能倾斜或侧转。',
  'tool': '防滑垫完好，放在托盘下可帮助双手稳定托盘。',
  'far': '恒温存放间唯一入口净宽80厘米，通道无侧向绕行空间，不能拆门或扩大入口。',
  'action': '{a}尝试与{b}平稳抬起标本托盘，并保持托盘水平把它送入恒温存放间。',
  'reaction': '{b}尝试配合{a}托起标本托盘另一侧，并保持水平一同送入恒温存放间。',
  'bLabel': 'partial',
  'reason': '双方可共同平稳抬起托盘；水平宽120厘米不能通过80厘米入口，且姿态/路径限制明确。两人的复合尝试都只完成抬起部分。'},
 'newentity': {
  'object': '校时钟指针可用拨针杆手动对准当前时间，但驱动主发条已断裂；现有世界没有替换发条，手动拨针不能恢复持续走时。',
  'tool': '拨针杆完整，可以拨动指针，不能修复断裂发条。',
  'action': '{a}尝试在{b}扶稳校时钟时，用拨针杆把指针对准当前时间并恢复持续走时。',
  'reaction': '{b}尝试为{a}扶稳校时钟外壳。',
  'reason': '现有工具可完成静态对时，损坏主发条仍使持续走时失败；没有创造不存在的新零件或把缺零件说成缺世界资料。'},
}


def _rename_world(world, prefix):
    """Draft-only identity allocation; never edit an existing service world."""
    fields = {'id', 'worldId', 'protagonistId', 'parentLocationId', 'containerId', 'slotId',
              'entityId', 'ownerId', 'parentTaskId', 'sourcePointId'}
    ids = set()
    def collect(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in fields and isinstance(item, str): ids.add(item)
                collect(item)
        elif isinstance(value, list):
            for item in value: collect(item)
    collect(world)
    names = {key: prefix + ':' + key for key in ids}
    def rename(value):
        if isinstance(value, dict): return {names.get(k, k): rename(v) for k, v in value.items()}
        if isinstance(value, list): return [rename(v) for v in value]
        return names.get(value, value) if isinstance(value, str) else value
    return rename(world), names


def authored_partial_judgments(rows):
    """Return 12 new joint annotations + 24 primitive judgments; write nothing."""
    bases = {}
    for row in rows:
        if row['component'] == 'D05.2' and row['kind'] == 'annotation_only' and not row.get('semanticAbstention'):
            bases.setdefault(row['sourceGroup'], row)
    if {g.rsplit(':', 1)[-1] for g in bases} != set(SCENES):
        raise ValueError('partial supervision requires the original twelve source groups')
    output = []
    for group, original in sorted(bases.items()):
        scene = group.rsplit(':', 1)[-1]; spec = SCENES[scene]
        prefix = 'partial:' + scene
        world, ids = _rename_world(deepcopy(original['input']['context']['world']), prefix)
        a, b, off, obj, tool, loc, far = (ids[x] for x in ('a', 'b', 'off', 'object', 'tool', 'loc', 'far'))
        # This alternative starts from a fresh authored state. Old historical
        # description records are not repurposed as evidence for new mechanics.
        for kind in ('locations', 'items', 'characters'):
            for entity in world[kind].values():
                entity['appearanceChanges'] = []
                if kind == 'characters':
                    entity['personalityChanges'] = []
                    entity['sanity'] = world['initial'][kind][entity['id']]['initialSanity']
                    for task in entity['tasks'].values(): task['status'] = 'pending'
                    for task in world['initial'][kind][entity['id']]['tasks'].values(): task['status'] = 'pending'
        world['time'] = deepcopy(world['initial']['initialTime'])
        world['initial']['items'][obj]['initialAppearance'] = spec['object']
        world['initial']['items'][tool]['initialAppearance'] = spec['tool']
        world['initial']['locations'][loc]['initialAppearance'] = '操作空间充足，光线清楚，已有目标和工具均可接触。'
        world['initial']['locations'][far]['initialAppearance'] = spec.get('far', '独立侧室，与当前操作没有直接接触。')
        for person in (a, b):
            world['initial']['characters'][person]['initialAppearance'] = '双手可用，精神清醒，具备完成所述普通操作的体力。'
        world['initial']['characters'][off]['initialAppearance'] = '位于远端侧室，本轮已完成自己的行动。'
        positions = {a: loc, b: loc, off: far,
                     obj: ids[spec.get('objectContainer', 'loc')], tool: ids[spec.get('toolContainer', 'a')]}
        for key, parent in positions.items():
            kind = 'characters' if key in world['characters'] else 'items'
            position = {'containerId': parent, 'slotId': None, 'relativeTo': None}
            world[kind][key]['position'] = deepcopy(position)
            world['initial'][kind][key]['initialPosition'] = deepcopy(position)
        names = {key: world['initial']['characters'][ids[key]]['name'] for key in ('a', 'b', 'off')}
        group_id, point_id = prefix + ':group', prefix + ':point'
        members = []
        for actor, template in ((a, spec['action']), (b, spec['reaction'])):
            text = template.format(**names)
            members.append({'memberId': actor, 'actionText': text,
                            'fragments': [{'id': actor + ':attempt-1', 'text': text}]})
        targets = [{'sourceId': a, 'targetIds': [b] + ([off] if spec.get('offTarget') else [])},
                   {'sourceId': b, 'targetIds': [a]}]
        baseline = digest({'world': world, 'pointId': point_id, 'actedIds': [off], 'eligibleIds': [a, b]})
        judgments = []
        for target_row in targets:
            for target in target_row['targetIds']:
                index = len(judgments) + 1
                eligible = target != off
                value = 15 if eligible else 5  # Authored known inputs, not sampled/production dice.
                judgments.append({'sourceId': target_row['sourceId'], 'targetId': target,
                    'rollId': prefix + ':roll:' + str(index), 'triggerKey': prefix + ':trigger:' + str(index),
                    'groupId': group_id, 'ruleVersion': 'reaction-d20-v1', 'target': 11, 'result': value,
                    'eligibilityBaselineDigest': baseline, 'eligible': eligible,
                    'admitted': eligible and value >= 11})
        context = {'world': world, 'binding': {'worldId': world['worldId'], 'pointId': point_id, 'version': 1,
                    'requestId': prefix + ':request', 'epoch': 1, 'checkpointRevision': 0},
            'timeAdvance': {'boundary': 'elapsed', 'duration': {'amount': spec.get('seconds', 60), 'unit': 'second'}},
            'group': {'groupId': group_id, 'closed': True, 'memberIds': [a, b], 'members': members,
                      'confirmedTargets': targets, 'judgments': judgments, 'alreadyActedIds': [off]}}
        attempts = [{'attemptId': m['fragments'][0]['id'], 'memberId': m['memberId'], 'text': m['actionText']} for m in members]
        joint = {'judgments': [{'attemptId': attempts[0]['attemptId'], 'label': 'partial'},
                              {'attemptId': attempts[1]['attemptId'], 'label': spec.get('bLabel', 'achieved')}]}
        row = deepcopy(original)
        row['exampleId'] = original['exampleId'] + ':authored-partial-joint'
        row['input'] = {'context': context, 'inputHash': digest(context), 'attempts': attempts,
                        'relations': {'checkedActionIds': [a, b], 'relations': [{'sourceId': b, 'targetId': a, 'kind': 'supports'}]}}
        row['target'] = json.dumps(joint, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        row.update(inputProvenance='authored_new_closed_group_same_source_partial_diagnostic',
                   annotationStatus='assistant_draft', sourceStatus='unverified', reviewStatus='pending_human',
                   previousExposure=['short-intent-20261109-r1', 'short-all-20261109-r3'],
                   holdoutStatus='open_holdout_previously_inspected' if row['split'] == 'test' else 'same_source_revision',
                   derivedFromAnnotation=original['exampleId'], derivedFromSha256=original['contentSha256'],
                   expectedProgramCompletion='result', authorRationale=spec['reason'],
                   judgmentProvenance='assistant_constructed_known_roll_inputs_not_service_receipts_or_rng',
                   semanticIndependence='new_variant_same_source_group_not_independent_source',
                   partialDiagnostic={'newIdentities': True, 'partialAttemptIds': [j['attemptId'] for j in joint['judgments'] if j['label'] == 'partial'],
                                      'interpretation': 'a specified portion is attained and another specified portion is not; no missing semantic material'})
        row.pop('expectedProgramReason', None)
        row['contentSha256'] = digest({k: v for k, v in row.items() if k != 'contentSha256'})
        output.append(row)
        for decision in joint['judgments']:
            primitive = deepcopy(row)
            primitive.update(component='D05.2.label', kind='label', outputCodec='scalar',
                labels=['achieved', 'partial', 'not_achieved', 'incomplete'], target=decision['label'])
            primitive['input']['semanticQuery'] = {'attemptId': decision['attemptId']}
            primitive['exampleId'] = row['exampleId'] + ':primitive:' + decision['attemptId']
            primitive['derivedFromAnnotation'] = row['exampleId']; primitive['derivedFromSha256'] = row['contentSha256']
            primitive['contentSha256'] = digest({k: v for k, v in primitive.items() if k != 'contentSha256'})
            output.append(primitive)
    return output
