# -*- coding: utf-8 -*-
"""Hand-authored condition/fact pairs for the task proposer pilot.

Each row is one task condition and one fact, labelled keyword / attempt /
satisfied / none. The author also wrote the continuation rules; this is a
pilot, not independent evaluation.
"""
import json
from collections import Counter
from pathlib import Path

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-workflow'
WORLD = json.loads((ROOT / 'data/worlds/dragon-raja-free-day.world.json').read_text(encoding='utf8'))
TASK_GOALS = {
    task['id']: task['goal']
    for character in WORLD['characters'].values()
    for task in character['tasks'].values()
}

ROWS = [
 ('task_lu_goggles','c1','item：路明非的护目镜',
  '路明非把护目镜拿在手里。','路明非伸手去拿护目镜，但还没碰到。','墙上挂着路明非的护目镜。'),
 ('task_lu_goggles','c2','confirmation：确认',
  '路明非检查镜片，确认没有裂纹。','路明非想检查镜片，但光线太暗。','有人说镜片没有裂纹。'),
 ('task_lu_goggles','c3','action：戴好',
  '路明非把护目镜戴好。','路明非把护目镜举到眼前，又放下。','护目镜的镜带松着。'),
 ('task_lu_choice','c1','target：诺诺',
  '路明非向诺诺问起局势。','路明非想找诺诺，但诺诺已经走开。','诺诺站在巷口。'),
 ('task_lu_choice','c2','confirmation：问清',
  '诺诺回答路明非，他可以保持中立。','路明非问了诺诺，诺诺只说很乱。','诺诺知道红蓝局势。'),
 ('task_nono_battery','c1','item：诺诺的故障短讯机',
  '诺诺把故障短讯机拿在手里。','诺诺伸手去拿短讯机，但被器材箱挡住。','故障短讯机放在桌上。'),
 ('task_nono_battery','c2','target：凯撒',
  '诺诺用短讯机联系上凯撒。','诺诺呼叫凯撒，频道没有回应。','凯撒在红方集结点。'),
 ('task_nono_battery','c3','action：恢复',
  '诺诺修好短讯机，频道恢复。','诺诺拆开短讯机检查，还没有修好。','短讯机需要恢复。'),
 ('task_caesar_win','c1','time：15:45',
  '时间到了15:45，停赛通知发布。','时间接近15:45，通知还没发。','15:45是停赛时间。'),
 ('task_caesar_win','c2','confirmation：确认',
  '裁判确认红方控制旗台。','红方报告旗台已被控制，尚未确认。','旗台上有红方旗。'),
 ('task_tang_ammo','c1','action：更换',
  '唐骁卸下空弹匣，换上满弹匣。','唐骁摸到备用弹匣，还没换上。','空弹匣在脚边。'),
 ('task_lin_leave','c1','location：演习医护处置室',
  '林亦舟到达演习医护处置室。','林亦舟向医护处置室走了一半。','医护处置室在附楼。'),
 ('task_lin_leave','c2','action：到达',
  '林亦舟走进医护处置室。','林亦舟朝医护处置室走，但停在门口。','医护处置室的门开着。'),
 ('task_su_report','c1','location：跨溪小桥',
  '苏茜来到跨溪小桥边。','苏茜向小桥方向走，被护栏挡住。','跨溪小桥在溪上。'),
 ('task_su_report','c2','target：楚子航',
  '苏茜向楚子航报告小桥情况。','苏茜想找楚子航，但他在钟楼。','楚子航守在钟楼。'),
 ('task_su_report','c3','confirmation：报告',
  '苏茜向楚子航报告了三名蓝方人员和松动护栏。','苏茜只说小桥有人。','报告需要包含人员和护栏。'),
 ('task_zhou_rope','c1','location：外廊',
  '周映走到外廊边缘。','周映向外廊走，被门挡住。','外廊在旗台外侧。'),
 ('task_zhou_rope','c2','confirmation：确认',
  '周映确认安全绳另一端固定。','周映拉了拉安全绳，但还没确认固定。','安全绳挂在墙上。'),
 ('task_zhou_rope','c3','action：扣好',
  '周映把安全绳扣好。','周映拿起安全绳，还没扣上。','安全绳的扣环开着。'),
 ('task_qin_stretcher','c1','confirmation：报告',
  '秦越接到林亦舟的真实扭伤报告。','秦越听说有人受伤，但报告还没核实。','有人在医护区。'),
 ('task_qin_stretcher','c2','action：开笼',
  '秦越打开器材笼，放出担架。','秦越走到器材笼前，还没开锁。','器材笼锁着。'),
 ('task_manstein_clock','c1','time：15:45',
  '曼施坦因在15:45发布停赛通知。','时间快到15:45，通知还没发。','15:45是停赛时间。'),
 ('task_manstein_clock','c2','confirmation：核对',
  '曼施坦因核对旗台最终状态。','曼施坦因看了一眼旗台，还没核对。','旗台状态需要核对。'),
 ('task_manstein_clock','c3','action：发布',
  '曼施坦因发布停赛通知。','曼施坦因写好停赛通知，还没发布。','停赛通知在桌上。'),
]

# Hard negatives from the real 2026-11-26 turn: "拿起护目镜" was scored as a
# satisfied "戴好"/"进入" action, which satisfied task_lu_kit after one turn.
EXTRA = [
 ('task_lu_goggles', 'c3', 'action：戴好', '路明非拿起护目镜。', 'attempt'),
 ('task_lu_goggles', 'c2', 'confirmation：确认', '路明非检查诺诺的短讯机有没有裂纹。', 'keyword'),
 ('task_lu_kit', 'c1', 'item：护目镜', '路明非拿起护目镜。', 'satisfied'),
 ('task_lu_kit', 'c2', 'action：进入', '路明非拿起护目镜。', 'keyword'),
 ('task_lu_kit', 'c2', 'action：进入', '路明非走向交火区。', 'attempt'),
 ('task_lu_kit', 'c2', 'action：进入', '路明非进入交火区。', 'satisfied'),
 ('task_zhou_rope', 'c3', 'action：扣好', '周映拿起安全绳。', 'attempt'),
 ('task_tang_ammo', 'c1', 'action：更换', '唐骁摸到备用弹匣。', 'attempt'),
 ('task_lin_leave', 'c2', 'action：到达', '林亦舟走向医护处置室。', 'attempt'),
 ('task_lu_match', 'c2', 'confirmation：确认', '路明非检查镜片有没有裂纹。', 'keyword'),
 ('task_lu_choice', 'c2', 'confirmation：问清', '路明非检查镜片有没有裂纹。', 'keyword'),
 ('task_lu_match', 'c2', 'confirmation：确认', '路明非向诺诺问清当前局势。', 'satisfied'),
 ('task_lu_choice', 'c2', 'confirmation：问清', '诺诺回答路明非，他可以保持中立。', 'satisfied'),
]

UNRELATED = [
 '诺诺把红色识别带缠在左臂。','唐骁在庭院里换弹匣。','楚子航在钟楼顶层架起枪。',
 '凯撒在红方集结点清点人数。','沈澄在休息区喝了一口水。','苏茜在东回廊检查遮光帘。',
 '芬格尔在器材棚换相机电池。','林亦舟扶着墙走向医护室。','曼施坦因在控制室核对计分板。',
 '周映在外廊扣安全绳。',
]


def main():
    v1 = []
    for task_id, condition_id, label, satisfied, attempt, keyword in ROWS:
        for fact, verdict in ((satisfied, 'satisfied'), (attempt, 'attempt'), (keyword, 'keyword')):
            v1.append({'task_id': task_id, 'condition_id': condition_id, 'condition': label,
                       'fact': fact, 'label': verdict})
    for fact in UNRELATED:
        v1.append({'task_id': None, 'condition_id': None, 'condition': 'none', 'fact': fact, 'label': 'none'})
    v2 = []
    for row in v1:
        v2.append({**row, 'goal': TASK_GOALS.get(row['task_id'], '')})
    for task_id, condition_id, label, fact, verdict in EXTRA:
        v2.append({'task_id': task_id, 'condition_id': condition_id, 'condition': label,
                   'goal': TASK_GOALS.get(task_id, ''), 'fact': fact, 'label': verdict})
    # Fixed from the 2026-11-26 report so the held-out comparison stays the
    # same three tasks while new hard negatives enter train.
    held = {'task_caesar_win', 'task_manstein_clock', 'task_tang_ammo'}
    for rows, name in ((v1, 'task-condition-data.jsonl'), (v2, 'task-condition-data-v2.jsonl')):
        for row in rows:
            row['split'] = 'test' if row['task_id'] in held else 'train'
        (PUB / name).write_text(
            ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf8')
        print(name, 'rows', len(rows), 'labels', dict(Counter(row['label'] for row in rows)))


if __name__ == '__main__':
    main()
