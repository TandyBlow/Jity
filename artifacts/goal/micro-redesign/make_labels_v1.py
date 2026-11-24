# -*- coding: utf-8 -*-
"""Hand-written first labeling batch (60 rows, four tasks, adversarial cases)."""
import json
from pathlib import Path

OUT = Path('D:/others/Jity/artifacts/goal/micro-redesign')
OUT.mkdir(parents=True, exist_ok=True)

TARGETS = [
    ("路明非把红色电台递给阿豹，让他转交给裁判。\n在场：诺诺", "诺诺（nono）", []),
    ("路明非问诺诺红蓝区域怎么分。\n在场：诺诺", "诺诺（nono）", ["nono"]),
    ("路明非把护目镜递给芬格尔。\n在场：芬格尔", "芬格尔（fingel）", ["fingel"]),
    ("路明非沿着服务巷往里走。\n在场：诺诺、芬格尔", "诺诺（nono）、芬格尔（fingel）", []),
    ("路明非让林亦舟把演习枪放下。\n在场：林亦舟", "林亦舟（lin）", ["lin"]),
    ("路明非对诺诺说：你先走。\n在场：诺诺、芬格尔", "诺诺（nono）、芬格尔（fingel）", ["nono"]),
    ("路明非把短讯机塞给芬格尔，让她听。\n在场：诺诺、芬格尔", "诺诺（nono）、芬格尔（fingel）", ["fingel"]),
    ("路明非问起红蓝区域。\n在场：诺诺", "诺诺（nono）", ["nono"]),
    ("路明非把钥匙交给秦越。\n在场：秦越、诺诺", "秦越（qin）、诺诺（nono）", ["qin"]),
    ("路明非拦住正往门口走的林亦舟。\n在场：林亦舟、芬格尔", "林亦舟（lin）、芬格尔（fingel）", ["lin"]),
    ("路明非朝诺诺点了点头。\n在场：诺诺", "诺诺（nono）", ["nono"]),
    ("路明非把演习枪踢到林亦舟脚边。\n在场：林亦舟", "林亦舟（lin）", ["lin"]),
    ("路明非叫住正要离开的两个人。\n在场：诺诺、芬格尔", "诺诺（nono）、芬格尔（fingel）", ["nono", "fingel"]),
    ("路明非让阿豹把电台转交裁判。\n在场：诺诺", "诺诺（nono）", []),
    ("路明非问在场的人红蓝区域。\n在场：诺诺、芬格尔", "诺诺（nono）、芬格尔（fingel）", ["nono", "fingel"]),
]

POSITION = [
    ("路明非进了器材棚。", "西侧服务巷", "器材棚", ["西侧服务巷", "器材棚", "西回廊", "钟楼"], "器材棚"),
    ("路明非还站在巷口，没有动。", "西侧服务巷", "西侧服务巷", ["西侧服务巷", "器材棚", "西回廊"], "西侧服务巷"),
    ("路明非上了钟楼二层平台。", "钟楼门厅", "二层平台", ["钟楼门厅", "二层平台", "顶层旗台"], "二层平台"),
    ("路明非从器材棚回到服务巷。", "器材棚", "西侧服务巷", ["西侧服务巷", "器材棚", "庭院"], "西侧服务巷"),
    ("路明非没有进器材棚，仍留在巷里。", "西侧服务巷", "西侧服务巷", ["西侧服务巷", "器材棚", "西回廊"], "西侧服务巷"),
    ("路明非穿过西回廊往钟楼西门走。", "西回廊", "钟楼", ["西回廊", "钟楼", "庭院"], "钟楼"),
    ("路明非把诺诺扶进了西回廊。", "庭院", "西回廊", ["庭院", "西回廊", "器材棚"], "西回廊"),
    ("路明非朝庭院方向看了一眼，人还在廊下。", "西回廊", "西回廊", ["西回廊", "庭院"], "西回廊"),
    ("路明非进了检修口，下到地下通道。", "西侧服务巷", "地下通道", ["西侧服务巷", "地下通道", "庭院"], "地下通道"),
    ("路明非退回巷口，没有跨过黄黑绳。", "西侧服务巷", "西侧服务巷", ["西侧服务巷", "庭院"], "西侧服务巷"),
    ("路明非沿着器材棚外侧低姿快走到西回廊，贴着廊柱停住。", "西侧服务巷", "西回廊", ["西侧服务巷", "器材棚", "西回廊"], "西回廊"),
    ("路明非没有上楼，仍站在钟楼门厅。", "钟楼门厅", "钟楼门厅", ["钟楼门厅", "二层平台"], "钟楼门厅"),
    ("路明非把电台放回领用台，人在器材棚。", "器材棚", "器材棚", ["器材棚", "西侧服务巷"], "器材棚"),
    ("路明非从钟楼出来，走到庭院边。", "钟楼", "庭院", ["钟楼", "庭院", "西回廊"], "庭院"),
    ("路明非翻过矮墙进了庭院。", "西侧服务巷", "庭院", ["西侧服务巷", "庭院"], "庭院"),
]

INTENT = [
    ("角色：诺诺\n任务：把短讯机交给裁判\n现场：巷里只有路明非", "act"),
    ("角色：芬格尔\n任务：拍照记录演习\n现场：林亦舟靠在廊柱边", "act"),
    ("角色：林亦舟\n任务：无\n现场：脚踝肿了，靠着廊柱", "skip"),
    ("角色：秦越\n任务：看守器材笼\n现场：芬格尔靠近笼子", "act"),
    ("角色：诺诺\n任务：等待信号\n现场：枪声间隔变短", "act"),
    ("角色：芬格尔\n任务：无\n现场：路明非走过", "skip"),
    ("角色：林亦舟\n任务：守住西回廊\n现场：路明非进入回廊", "act"),
    ("角色：诺诺\n任务：无\n现场：巷里安静", "skip"),
    ("角色：秦越\n任务：清点弹药\n现场：弹匣少了一只", "act"),
    ("角色：芬格尔\n任务：等同伴\n现场：同伴没来", "skip"),
    ("角色：林亦舟\n任务：无\n现场：演习结束哨响", "act"),
    ("角色：诺诺\n任务：找阿豹\n现场：阿豹不在", "act"),
    ("角色：秦越\n任务：看守器材笼\n现场：没人靠近", "skip"),
    ("角色：芬格尔\n任务：拍照\n现场：相机没电", "skip"),
    ("角色：林亦舟\n任务：守住回廊\n现场：只有自己", "skip"),
]

JUDGE = [
    ("行动：路明非把护目镜递给诺诺\n目标：诺诺\n骰点：result 12，eligible=true，admitted=true", "achieved"),
    ("行动：路明非把护目镜递给诺诺\n目标：诺诺\n骰点：result 4，eligible=true，admitted=false", "not_achieved"),
    ("行动：路明非推器材棚的门\n目标：门\n骰点：无，门被顶住", "blocked"),
    ("行动：路明非观察巷口\n目标：无\n骰点：无", "no_change"),
    ("行动：路明非把电台递给阿豹\n目标：阿豹\n骰点：无，阿豹不在场", "blocked"),
    ("行动：路明非挪动器材箱\n目标：箱子\n骰点：result 9，eligible=true，admitted=true，只挪动一半", "partial"),
    ("行动：路明非把演习枪踢给林亦舟\n目标：林亦舟\n骰点：result 15，eligible=true，admitted=true", "achieved"),
    ("行动：路明非问诺诺红蓝区域\n目标：诺诺\n骰点：无，诺诺没有回答", "not_achieved"),
    ("行动：路明非在墙边等一分钟\n目标：无\n骰点：无，时间推进", "no_change"),
    ("行动：路明非把钥匙藏进口袋\n目标：钥匙\n骰点：无", "achieved"),
    ("行动：路明非翻过矮墙\n目标：矮墙\n骰点：result 3，eligible=true，admitted=false", "not_achieved"),
    ("行动：路明非扶林亦舟站起来\n目标：林亦舟\n骰点：result 5，eligible=true，admitted=false", "not_achieved"),
    ("行动：路明非把短讯机塞给芬格尔\n目标：芬格尔\n骰点：无，芬格尔后退", "blocked"),
    ("行动：路明非看赛区图\n目标：赛区图\n骰点：无", "no_change"),
    ("行动：路明非把电台交给裁判\n目标：裁判\n骰点：无，裁判不在场", "blocked"),
]

rows = []
for text, present, label in TARGETS:
    rows.append({'task': 'targets', 'input': f"行动：{text}", 'label': label})
for fact, current, dest, cands, label in POSITION:
    rows.append({'task': 'position', 'input': f"事实：{fact}\n当前：{current}\n候选：{'、'.join(cands)}", 'label': label})
for text, label in INTENT:
    rows.append({'task': 'intent', 'input': text, 'label': label})
for text, label in JUDGE:
    rows.append({'task': 'judgment', 'input': text, 'label': label})

path = OUT / 'labels-v1.jsonl'
with open(path, 'w', encoding='utf8') as handle:
    for row in rows:
        handle.write(json.dumps(row, ensure_ascii=False) + '\n')
print('rows', len(rows), '->', path)
