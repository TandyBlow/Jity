# -*- coding: utf-8 -*-
"""Hand-authored pilot data for the two heads the corpus could not label.

Both files are balanced and each row carries `source: authored`. The act/skip
rows are real character sheets from the static world plus a hand-written
situation; the appearance rows are real entity lines plus a hand-written fact.
These labels are the reviewer's, not the model's, and they are not used by the
product.
"""
import json
from pathlib import Path

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-workflow'
WORLD = ROOT / 'data/worlds/dragon-raja-free-day.world.json'

ACT = [
    '对手的掩护位突然空了，器材棚的门半开着。',
    '回廊尽头传来两声短促的哨响，旗手正朝钟楼移动。',
    '一名蓝方队员在拐角跌倒，四周暂时没有别人。',
    '广播报出旗台还有十分钟易手，队友在等回复。',
    '服务巷的检修盖被人从里面推开，铁梯露了出来。',
    '对手的短讯机落在长椅旁，屏幕还亮着。',
    '旗台方向升起一股白烟，守备员离开了原位。',
    '有人在小桥边挥手，示意护栏已经松动。',
    '器材棚里传出金属碰撞声，门缝里有影子晃动。',
    '红方的信号旗突然降了一半，周围没人去扶。',
    '医护通道的门被撞开，里面有人喊需要担架。',
    '对手把长椅推倒当掩体，侧面留出了一条通道。',
    '无线电里传来一句清楚的坐标，重复了两遍。',
    '顶层玻璃门反射出一道人影，正往旗台靠近。',
    '蓝方队员把备用弹匣落在花槽边，人已经走远。',
    '中央庭院的水迹一直延伸到检修口，盖子没盖严。',
    '裁判的哨声响起，比赛暂停三十秒。',
    '有人从西回廊朝你这边跑来，手势很急。',
    '钟楼门厅的翻倒长桌后面传来压低了的说话声。',
    '红方旗手回头看了一眼，像是在等一个信号。',
    '对手的脚步声停在墙后，呼吸声清楚可闻。',
    '医护附楼的门开着，顾岚在门口招手。',
    '旗台底座的安全绳松了一半，风一吹就晃。',
    '蓝方短讯机突然亮起，频道里有人在呼叫。',
    '器材笼的挂锁掉在地上，门开着一条缝。',
    '西回廊的窗内有人影贴着墙移动。',
    '小桥上的护栏被踩得吱呀作响。',
    '红方集结点传来集合的掌声，人数不齐。',
    '顶层传来旗绳滑动的声音，旗面正在下降。',
    '有人在庭院中央停下，朝你的方向张望。',
    '检修通道里亮起一道手电光，越来越近。',
    '对手的枪口从长椅后抬起，又缩了回去。',
    '蓝方信号旗被风吹落，掉在回廊外。',
    '裁判朝旗台举牌，示意需要一名见证人。',
    '医护区传来一声短促的叫喊，随后安静。',
    '唐骁的满弹匣从背心上滑落，滚到脚边。',
    '服务巷尽头有人敲了三下铁门，停了一秒又敲两下。',
    '钟楼门厅的广播话筒被碰倒，发出刺耳的杂音。',
    '红方地图桌旁围了人，正指着庭院的一角。',
    '东回廊的遮光帘被拉开，窗口完全暴露。',
]

SKIP = [
    '巷子里只剩风，远处的声音还隔着两道墙。',
    '医护区的门关着，外面没有新的伤情报告。',
    '对手都缩在掩体后，没有任何移动的迹象。',
    '无线电里只有杂音，下一次联络还有五分钟。',
    '旗台方向很安静，白旗没有动。',
    '器材棚的门锁着，里面没有声音。',
    '回廊里只有自己的脚步，队友都在远处。',
    '小桥边没有人，护栏的绳子还在原处。',
    '广播重复着同一句停赛通知，没有新的指令。',
    '检修口的盖子合着，周围没有脚印。',
    '医护休息区灯还亮着，床上的人睡着了。',
    '庭院里没有人经过，长椅还倒在那里。',
    '对手的短讯机一直没有响，频道里没人说话。',
    '顶层玻璃门关着，里面没有灯光。',
    '花槽边的弹匣还在原处，没有人靠近。',
    '钟楼门厅里没有声音，长桌保持原样。',
    '裁判席的方向没有旗语，比赛还在暂停。',
    '西回廊尽头空着，没有人朝这边来。',
    '红方旗手站在原地，没有下一步动作。',
    '蓝方集结点没有动静，队员都在等命令。',
    '服务巷里没有人，铁门关得严实。',
    '庭院的水迹已经干了，地面恢复原样。',
    '东回廊的遮光帘垂着，窗口没有动静。',
    '器材笼的锁挂在门上，钥匙还插着。',
    '小桥上空无一人，溪水声压过了别的动静。',
    '旗台底座的绳子系得很紧，旗面一动不动。',
    '医护附楼的灯灭了，门口没有人进出。',
    '钟楼顶层的旗绳垂着，风吹不动。',
    '红方地图桌旁空着，图还摊在原处。',
    '对手的枪口一直停在长椅后，没有抬起。',
    '蓝方信号旗插在原位，没有人去碰。',
    '裁判席的人坐着，没有举牌。',
    '唐骁的弹匣还挂在背心上，扣子扣着。',
    '检修通道里没有光，铁梯上没有脚步声。',
    '广播话筒立着，没有人靠近。',
    '中央庭院的长椅还倒着，没有人经过。',
    '服务巷的检修盖合着，铁链缠了两圈。',
    '医护区的登记夹挂在门上，没有人翻动。',
    '红方集结点的掌声停了，队伍已经散开。',
    '钟楼门厅的翻倒长桌后面没有声音。',
]

# (entityId, memberId, positive fact, negative fact)
PAIRS = [
    ('goggles_lu', 'lu', '路明非用袖子把护目镜的镜片擦得发亮。', '路明非把护目镜拿在手里看了看。'),
    ('jacket_lu', 'lu', '演习背心的前襟沾了一片湿泥。', '路明非把演习背心叠好放在脚边。'),
    ('red_band_nono', 'nono', '诺诺把红色识别带从手臂上解下来。', '诺诺摸了摸手臂上的红色识别带。'),
    ('radio_nono', 'nono', '故障短讯机的屏幕裂开一道细缝。', '诺诺把故障短讯机收回腰间。'),
    ('pistol_nono', 'nono', '短枪的保险被推到合上的位置。', '诺诺握着短枪，没有开枪。'),
    ('map', 'lu', '赛区路线图被雨水打湿，边角卷了起来。', '路明非展开赛区路线图看了一眼。'),
    ('lane', 'lu', '服务巷的检修盖被挪开，露出下面的铁梯。', '路明非在服务巷停下脚步。'),
    ('yard', 'tang', '庭院中央的花岗岩地面多了一摊新鲜的水迹。', '唐骁穿过庭院，没有停留。'),
    ('west_arcade', 'lin', '西回廊的第三根廊柱后被粉笔划了一道记号。', '林亦舟靠在西回廊的柱子旁。'),
    ('landing', 'chu', '二层平台的木质栏杆断了一截。', '楚子航站在二层平台的窗口旁。'),
    ('shed', 'qin', '器材棚的门锁被撬开，门虚掩着。', '秦越走进器材棚，打开领用簿。'),
    ('rest', 'shen', '医护休息区的空床被推到了窗边。', '沈澄在医护休息区坐下。'),
    ('water', 'lu', '休息区饮水杯的杯口缺了一块。', '路明非拿起休息区饮水杯。'),
    ('rifle_chu', 'chu', '楚子航的演习枪枪管上缠了一圈白胶带。', '楚子航把演习枪背到肩上。'),
    ('blue_radio', 'chu', '蓝方短讯机的电量灯开始闪红。', '楚子航按下蓝方短讯机的通话键。'),
    ('red_flag', 'zhou', '红方信号旗的旗面被撕开一道口子。', '周映扶住红方信号旗的旗杆。'),
    ('camera', 'fingel', '芬格尔的相机镜头盖不见了。', '芬格尔举起相机对准庭院。'),
    ('stretcher', 'doctor', '折叠担架被展开，帆布上有一道血印。', '顾岚把折叠担架挪到门边。'),
    ('white_sign', 'shen', '医护通道标牌被撞歪，箭头指向附楼。', '沈澄抬头看了看医护通道标牌。'),
    ('lu', 'lu', '路明非的校服领口湿了一圈，膝盖上的灰被拍掉了。', '路明非把水递给诺诺。'),
]


def main():
    world = json.loads(WORLD.read_text(encoding='utf8'))['initial']
    characters = world['characters']
    roster = [cid for cid, row in characters.items() if row.get('tasks')]
    act_rows, skip_rows = [], []
    for index, situations in enumerate((ACT, SKIP)):
        for offset, situation in enumerate(situations):
            cid = roster[(offset + index * 3) % len(roster)]
            row = characters[cid]
            tasks = '；'.join(f'{tid}={task.get("goal", "")}' for tid, task in (row.get('tasks') or {}).items())
            location = row['initialPosition']['containerId']
            place = world['locations'].get(location, {}).get('name', location)
            text = f"角色：{row['name']}；情境：{situation}；位置：{place}；个性：{row.get('initialPersonality', '')}；待办：{tasks}"
            (act_rows if index == 0 else skip_rows).append({
                'kind': 'act', 'label': 'act' if index == 0 else 'skip',
                'input': text, 'source': 'authored',
            })
    look_rows = []
    for entity_id, member, positive, negative in PAIRS:
        row = world['characters'].get(entity_id) or world['items'].get(entity_id) or world['locations'].get(entity_id)
        kind = '人物' if entity_id in world['characters'] else '物品' if entity_id in world['items'] else '地点'
        appearance = (row.get('initialAppearance') or '')[-80:]
        name = row.get('name', entity_id)
        member_name = characters[member]['name']
        for label, fact in ((1, positive), (0, negative)):
            look_rows.append({
                'kind': 'appearance', 'label': label,
                'input': f'实体：{name}；类型：{kind}；当前外貌：{appearance}；本组结果：{member} {member_name}: {fact}',
                'source': 'authored',
            })
    (PUB / 'pilot-act.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in act_rows + skip_rows), encoding='utf8')
    (PUB / 'pilot-appearance.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in look_rows), encoding='utf8')
    print('act', len(act_rows), 'skip', len(skip_rows), 'appearance', len(look_rows),
          'appearance labels', sum(r['label'] for r in look_rows))


if __name__ == '__main__':
    main()
