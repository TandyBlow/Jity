"""Manual adjudication of the audited training targets, and the audited pools.

audit_targets.py flags 136 pairs (71 distinct target strings) out of 341. Each
distinct target was read against its own fact and given one verdict here:

  ok             the target states its fact; the flag was a coverage artefact
                 (paraphrase, a required sanity cue, a licenced scene detail)
  extra-action   a trailing clause adds an action or state the fact does not
                 contain                                        -> delete the tail
  restatement    a trailing clause says the result a second time -> delete the tail
  quantity       a measure word from the fact value is missing    -> put it back
  qualifier      a qualifying noun from the fact value is missing -> put it back
  start          a movement target names the destination only    -> add the start

No target is lengthened to match a distribution: every rewrite either deletes an
unlicensed clause or restores a qualifier that the fact already carries. Length
before and after is reported, not corrected.

Outputs (artifacts/target-audit-r1/):
  decisions-r1.json    one record per flagged pair: fact, original, verdict,
                       revised target, reason
  *-audited.jsonl      the three pools with revised targets (originals untouched)
  summary.json         counts by verdict, length distribution before/after
"""
import collections
import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
WORKTREE = HERE.parents[1]
AUDIT = WORKTREE / 'artifacts/target-audit-r1'
POOLS = (('verbalizer', WORKTREE / 'experiments/world-components/n4_narrative_dev/verbalizer_pairs.jsonl'),
         ('expand78', WORKTREE / 'artifacts/next-inputs/world-components/n4-expand78-unified.jsonl'),
         ('object34', WORKTREE / 'artifacts/next-inputs/world-components/n4-object34-unified.jsonl'))

# (original target, verdict, revised target or None, reason)
DECISIONS = [
    # --- movement: destination only, plus a tail the fact does not license ---
    ('沈砚沿着石阶走进旧灯塔，鞋底在潮气里打滑。', 'start', '沈砚从潮生巷走进旧灯塔。', '缺起点潮生巷；尾句“鞋底打滑”事实外'),
    ('沈砚沿着石阶下到潮渡，河风把外袍下摆吹起来。', 'start', '沈砚从潮生巷下到潮渡。', '缺起点潮生巷；尾句“外袍下摆被吹起”事实外'),
    ('沈砚从潮生巷一路走到旧灯塔脚下，抬头看了看塔身。', 'extra-action', '沈砚从潮生巷一路走到旧灯塔脚下。', '尾句“抬头看了看塔身”是事实外动作'),
    ('沈砚推开旧灯塔的木门，潮生巷的雨声被关在身后。', 'start', '沈砚从潮生巷走进旧灯塔。', '起点只作为声音出现，未写成移动起点'),
    ('顾行舟把船停在潮渡，缆绳在木桩上绕了两圈。', 'start', '顾行舟把船从河心开到潮渡。', '缺起点河心；尾句缆绳动作事实外'),
    ('沈砚走到早市的摊棚外，鱼鳞在石板上反光。', 'start', '沈砚从潮生巷走到早市的摊棚外。', '缺起点潮生巷；尾句鱼鳞反光事实外'),
    ('沈砚走到潮渡的木桩旁，雾从河面漫上栈桥。', 'start', '沈砚从潮生巷走到潮渡的木桩旁。', '缺起点潮生巷；尾句雾漫栈桥是场景描写'),
    ('阿棠走进档案馆，鞋底在门槛上蹭了两下。', 'start', '阿棠从早市走进档案馆。', '缺起点早市；尾句蹭门槛事实外'),
    ('沈砚走到潮汐档案馆门口，把湿伞收在手里。', 'start', '沈砚从潮生巷走到潮汐档案馆门口。', '缺起点潮生巷；湿伞不在可见物件里'),
    ('沈砚穿过早市的人流，在鱼摊前站住。', 'start', '沈砚从潮生巷穿过早市的人流。', '缺起点潮生巷；尾句“站住”事实外'),
    ('沈砚回到潮渡，木桩上还挂着水珠。', 'start', '沈砚从旧灯塔回到潮渡。', '缺起点旧灯塔；尾句水珠是场景描写'),
    ('沈砚进了潮汐档案馆，在长桌边停下。', 'start', '沈砚从潮生巷走进潮汐档案馆。', '缺起点潮生巷；尾句“在长桌边停下”事实外'),
    ('叶知微到了旧灯塔，袖口带着铜油味。', 'start', '叶知微从潮渡到了旧灯塔。', '缺起点潮渡；尾句铜油味事实外'),
    ('沈砚从潮渡一路走到雾堤，风把他的袖口吹得鼓起来。', 'extra-action', '沈砚从潮渡一路走到雾堤。', '起终点齐全；尾句风鼓袖口事实外'),
    ('阿棠从潮生巷走进早市，围裙上沾着鱼鳞。', 'extra-action', '阿棠从潮生巷走进早市。', '起终点齐全；尾句围裙鱼鳞事实外'),
    ('韩渡到了雾堤，眉毛上挂着雾水。', 'start', '韩渡从潮渡到了雾堤。', '缺起点潮渡；尾句眉毛雾水事实外'),
    ('阿棠到了早市，把鱼筐放在案板边。', 'start', '阿棠从潮生巷到了早市。', '缺起点潮生巷；尾句放鱼筐事实外'),
    ('沈砚从潮生巷挤进早市，帆布棚下的白汽扑到脸上。', 'extra-action', '沈砚从潮生巷挤进早市。', '起终点齐全；白汽不在场景“清晨；薄雾；棚下散光”里'),
    # --- outcome ---
    ('沈砚换好备用灯芯，火苗重新站稳。', 'qualifier', '沈砚换好了塔顶的灯芯。', '事实是塔顶的灯芯，目标写成备用灯芯'),
    ('沈砚把陷在泥里的系泊绳一寸一寸拖回岸上。', 'qualifier', '沈砚把系泊绳从浅滩一寸一寸拖了回来。', '事实带起点浅滩，目标用“岸上”替换'),
    ('阿棠把一叠干纸放在桌角，纸角被风掀起。', 'extra-action', '阿棠把一叠干纸放在桌角。', '尾句纸角被掀起事实外'),
    ('阿棠把一筐银鳞鱼搬上案板，鱼尾拍得筐沿响。', 'extra-action', '阿棠把一筐银鳞鱼搬上案板。', '尾句鱼尾拍筐事实外'),
    ('叶知微把玻璃罩上的盐雾擦掉，灯罩透亮起来。', 'restatement', '叶知微把灯罩擦得透亮。', '尾句把“透亮”再说一遍'),
    ('沈砚把潮汐簿缺的那页补全，合上了簿子。', 'extra-action', '沈砚把潮汐簿缺的那页补全了。', '尾句合上簿子事实外'),
    ('韩渡把松脱的钟绳重新系紧，钟绳绷直了。', 'restatement', '韩渡把松脱的钟绳重新系紧。', '尾句把“系紧”的结果再说一遍'),
    ('韩渡把松脱的钟绳重新系紧，手背上沾着盐沫。', 'extra-action', '韩渡把松脱的钟绳重新系紧。', '尾句手背沾盐沫是另一条事实'),
    ('阿棠抱起鱼筐，放到案板上。', 'quantity', '阿棠把一筐银鳞鱼搬上案板。', '丢了数量“一筐”，物件也由银鳞鱼变成鱼筐'),
    ('沈砚扶正警示灯，玻璃罩里的火苗晃了两下。', 'qualifier', '沈砚把被风吹歪的警示灯扶正。', '事实是“被风吹歪的警示灯”，目标丢了“被风吹歪”；尾句火苗晃动事实外'),
    ('沈砚把潮汐簿缺的那页补全，指尖沾了墨。', 'extra-action', '沈砚把潮汐簿缺的那页补全了。', '尾句指尖沾墨是另一条事实'),
    ('沈砚在潮渡等到最后一班船，船灯从雾里透出来。', 'extra-action', '沈砚在潮渡等到了最后一班船。', '尾句船灯透出雾事实外'),
    ('沈砚换好了塔顶的灯芯，铜灯罩不再发暗。', 'restatement', '沈砚换好了塔顶的灯芯。', '尾句把换灯芯的结果再说一遍'),
    ('沈砚在潮渡等到了最后一班渡船，船灯从雾里透出来。', 'extra-action', '沈砚在潮渡等到了最后一班渡船。', '尾句船灯透出雾事实外'),
    ('沈砚把系泊绳从浅滩拖回来，外袍下摆沾满泥水。', 'extra-action', '沈砚把系泊绳从浅滩拖了回来。', '尾句外袍泥水是另一条事实'),
    ('沈砚一下一下拉动钟绳，雾警钟的声音撞进雾里。', 'ok', None, '用拉动钟绳和钟声写出“敲响”，事实完整'),
    ('沈砚换好了塔顶的灯芯，退开半步看火苗。', 'extra-action', '沈砚换好了塔顶的灯芯。', '尾句退开看火苗事实外'),
    ('沈砚在潮渡等到了最后一班船，才向前走了一步。', 'extra-action', '沈砚在潮渡等到了最后一班船。', '尾句再走一步事实外'),
    ('沈砚把系泊绳从浅滩拖了回来，绳子还在滴水。', 'restatement', '沈砚把系泊绳从浅滩拖了回来。', '尾句滴水是拖回的重复描写'),
    ('叶知微把灯罩擦得透亮，玻璃上不再有雾。', 'restatement', '叶知微把灯罩擦得透亮。', '尾句把“透亮”再说一遍'),
    ('阿棠把干纸放到桌角，又伸手按住。', 'quantity', '阿棠把一叠干纸放在桌角。', '丢数量“一叠”；尾句按住事实外'),
    ('阿棠把银鳞鱼搬上案板，水花溅到石板上。', 'quantity', '阿棠把一筐银鳞鱼搬上案板。', '丢数量“一筐”；尾句水花事实外'),
    ('阿棠把一叠干纸放在桌角，纸页还带着潮气。', 'extra-action', '阿棠把一叠干纸放在桌角。', '尾句纸页带潮气事实外'),
    # --- appearance ---
    ('沈砚的指尖沾了墨，在纸边蹭了蹭。', 'extra-action', '沈砚的指尖沾了墨。', '尾句在纸边蹭事实外'),
    ('沈砚的外袍下摆被雾水打湿，贴在腿上。', 'restatement', '沈砚的外袍下摆被雾水打湿。', '尾句贴在腿上是同一状态的重复'),
    ('叶知微的袖口沾了铜油，在灯影里发亮。', 'extra-action', '叶知微的袖口沾了铜油。', '尾句发亮事实外'),
    ('阿棠的鞋底带着早市的泥水，在门槛上蹭了两下。', 'extra-action', '阿棠的鞋底带着早市的泥水。', '尾句蹭门槛事实外'),
    ('阿棠的辫梢沾了白汽，发梢微微发潮。', 'restatement', '阿棠的辫梢沾了白汽。', '尾句发潮是同义重复'),
    ('叶知微擦完灯罩，袖口蹭上一道铜油。', 'extra-action', '叶知微的袖口沾了铜油。', '前半句擦灯罩事实外，且“一道”是新增数量'),
    ('阿棠从蒸汽里出来，辫梢挂着白汽。', 'extra-action', '阿棠的辫梢挂着白汽。', '“从蒸汽里出来”事实外'),
    ('叶知微抬起手，袖口那片铜油很显眼。', 'extra-action', '叶知微的袖口沾了铜油。', '抬手动作与“那片”都是事实外'),
    ('阿棠在石地上留下几个泥水印子。', 'qualifier', '阿棠的鞋底带着早市的泥水。', '丢了“鞋底”和“早市的泥水”，改写成结果'),
    ('韩渡抹了一把眉毛，雾水还是留在上面。', 'qualifier', '韩渡眉毛上的雾水更重了。', '丢了程度“更重”，改写抹眉毛'),
    ('沈砚走完石阶，外袍下摆已经湿透。', 'qualifier', '沈砚的外袍下摆被雾水打湿。', '“湿透”比事实“打湿”更重，起因雾水被丢掉'),
    ('沈砚的外袍下摆被海风掀起，衣角拍在腿上。', 'restatement', '沈砚的外袍下摆被海风掀起。', '尾句衣角拍腿是同一状态的重复'),
    ('沈砚的袖口被河风打湿，贴在手腕上。', 'restatement', '沈砚的袖口被河风打湿。', '尾句贴手腕是同一状态的重复'),
    ('沈砚直起腰，外袍下摆的泥水已经结出白盐。', 'quantity', '沈砚的外袍下摆沾满泥水，边角结了一圈白盐。', '丢数量“一圈”和“沾满泥水”；直起腰事实外'),
    ('沈砚放下笔，指尖已经染上墨色。', 'extra-action', '沈砚的指尖沾了墨。', '放下笔事实外，“染上墨色”是沾墨的同义改写'),
    ('沈砚的衣摆沾了泥水，边角沉甸甸地垂着。', 'restatement', '沈砚的衣摆沾了泥水。', '尾句垂着是同一状态的重复'),
    ('沈砚的鞋底沾了湿石板的水，在身后留下浅印。', 'extra-action', '沈砚的鞋底沾了湿石板的水。', '尾句留下浅印事实外'),
    # --- no_change: the target must not use the input's own field names ---
    ('他等了一会儿，场景里没有新的变化。', 'banned', '他等了一会儿，周围没有新的变化。', '目标里出现字段名“场景”，要求明确不写字段名'),
    # --- sanity / personality: the flags are coverage artefacts, targets kept ---
    ('沈砚的呼吸慢慢匀下来，胸口那点发紧的感觉散了。', 'ok', None, '“放松”用呼吸和胸口写出可感方向，事实完整'),
    ('沈砚的呼吸有些发紧，手指也不太听使唤。', 'ok', None, '“发紧”用呼吸与手指写出可感方向'),
    ('沈砚松开手，才发现自己一直提着的那口气落回去了。', 'ok', None, '“放松”用松手与气息落下写出'),
    ('沈砚靠在墙边站了一会儿，心跳才慢下来。', 'ok', None, '“放松”用心跳变慢写出'),
    ('沈砚按住胸口，那阵闷意没有散。', 'ok', None, '“发紧”用闷意不散写出'),
    ('沈砚站住，听见自己的呼吸比刚才重。', 'ok', None, '“发紧”用呼吸变重写出'),
    ('沈砚没有再把话咽回去，直接问了出来。', 'ok', None, '“不再把话咽回去”直接写出'),
    ('沈砚没有催，站在栈桥边等了下去。', 'ok', None, '“愿意等”用没有催、继续等写出'),
    ('沈砚本来想把话咽回去，这次却先开了口。', 'ok', None, '“先开口”直接写出'),
    ('沈砚没有像往常那样沉默，先问了一句。', 'ok', None, '“愿意先开口”用先问一句写出'),
    ('沈砚这一次没有沉默，把想问的说了。', 'ok', None, '“不再把话咽回去”用开口写出'),
    ('沈砚张了张嘴，把那句话说了出来。', 'ok', None, '写出了开口，但“愿意”只靠动作暗示；保留并记为弱表达'),
    ('沈砚开口时没有停顿，话已经出口。', 'ok', None, '写出了开口，但“愿意/不再咽回去”只靠不停顿暗示；保留并记为弱表达'),
]
KEPT_WEAK = {'沈砚张了张嘴，把那句话说了出来。', '沈砚开口时没有停顿，话已经出口。'}
# Arm B (conservative) keeps every trailing clause and only repairs a fact that
# the original target contradicts or drops: a missing movement start, a missing
# measure word, a missing qualifier, or a field name used as a place. Targets not
# listed here are unchanged in arm B. Arm B does not isolate length: restoring a
# qualifier or a start changes the sentence length too, so the three arms can
# separate "fact repair" from "tail deletion" but not length as such.
CONSERVATIVE = {
    '叶知微到了旧灯塔，袖口带着铜油味。': '叶知微从潮渡到了旧灯塔，袖口带着铜油味。',
    '沈砚回到潮渡，木桩上还挂着水珠。': '沈砚从旧灯塔回到潮渡，木桩上还挂着水珠。',
    '沈砚推开旧灯塔的木门，潮生巷的雨声被关在身后。': '沈砚从潮生巷推开旧灯塔的木门，雨声被关在身后。',
    '沈砚沿着石阶下到潮渡，河风把外袍下摆吹起来。': '沈砚从潮生巷沿着石阶下到潮渡，河风把外袍下摆吹起来。',
    '沈砚沿着石阶走进旧灯塔，鞋底在潮气里打滑。': '沈砚从潮生巷沿着石阶走进旧灯塔，鞋底在潮气里打滑。',
    '沈砚穿过早市的人流，在鱼摊前站住。': '沈砚从潮生巷穿过早市的人流，在鱼摊前站住。',
    '沈砚走到早市的摊棚外，鱼鳞在石板上反光。': '沈砚从潮生巷走到早市的摊棚外，鱼鳞在石板上反光。',
    '沈砚走到潮汐档案馆门口，把湿伞收在手里。': '沈砚从潮生巷走到潮汐档案馆门口，把湿伞收在手里。',
    '沈砚走到潮渡的木桩旁，雾从河面漫上栈桥。': '沈砚从潮生巷走到潮渡的木桩旁，雾从河面漫上栈桥。',
    '沈砚进了潮汐档案馆，在长桌边停下。': '沈砚从潮生巷进了潮汐档案馆，在长桌边停下。',
    '阿棠到了早市，把鱼筐放在案板边。': '阿棠从潮生巷到了早市，把鱼筐放在案板边。',
    '阿棠走进档案馆，鞋底在门槛上蹭了两下。': '阿棠从早市走进档案馆，鞋底在门槛上蹭了两下。',
    '韩渡到了雾堤，眉毛上挂着雾水。': '韩渡从潮渡到了雾堤，眉毛上挂着雾水。',
    '顾行舟把船停在潮渡，缆绳在木桩上绕了两圈。': '顾行舟把船从河心开到潮渡，缆绳在木桩上绕了两圈。',
    '沈砚直起腰，外袍下摆的泥水已经结出白盐。': '沈砚直起腰，外袍下摆沾满泥水，边角结了一圈白盐。',
    '阿棠把干纸放到桌角，又伸手按住。': '阿棠把一叠干纸放到桌角，又伸手按住。',
    '阿棠把银鳞鱼搬上案板，水花溅到石板上。': '阿棠把一筐银鳞鱼搬上案板，水花溅到石板上。',
    '阿棠抱起鱼筐，放到案板上。': '阿棠抱起一筐银鳞鱼，放到案板上。',
    '沈砚扶正警示灯，玻璃罩里的火苗晃了两下。': '沈砚把被风吹歪的警示灯扶正，玻璃罩里的火苗晃了两下。',
    '沈砚把陷在泥里的系泊绳一寸一寸拖回岸上。': '沈砚把系泊绳从浅滩一寸一寸拖回岸上。',
    '沈砚换好备用灯芯，火苗重新站稳。': '沈砚换好塔顶的灯芯，火苗重新站稳。',
    '沈砚走完石阶，外袍下摆已经湿透。': '沈砚走完石阶，外袍下摆被雾水打湿。',
    '阿棠在石地上留下几个泥水印子。': '阿棠的鞋底带着早市的泥水，在石地上留下几个泥水印子。',
    '韩渡抹了一把眉毛，雾水还是留在上面。': '韩渡抹了一把眉毛，雾水反而更重了。',
    '他等了一会儿，场景里没有新的变化。': '他等了一会儿，周围没有新的变化。',
}
PUNCT = re.compile(r'[\s，,。．.；;：:！!？?、…—－\-\'"“”‘’（）()《》「」]')


def normalize(text):
    return PUNCT.sub('', text or '')


def bigrams(text):
    flat = normalize(text)
    return {flat[i:i + 2] for i in range(len(flat) - 1)}


def coverage(value, target):
    wanted = bigrams(value)
    return 1.0 if not wanted else len(wanted & bigrams(target)) / len(wanted)


def value_of(pair):
    fact = [line for line in pair['input'].splitlines() if line.startswith('事实=')][0][3:]
    parts = fact.split('｜')
    return parts[2].strip() if len(parts) > 2 else ''


def main():
    report = json.loads((AUDIT / 'audit-r1.json').read_text(encoding='utf-8'))
    table = {original: (verdict, revised, reason) for original, verdict, revised, reason in DECISIONS}
    seen_values = collections.defaultdict(set)
    records, changed = [], 0
    audited = {}
    for pool, path in POOLS:
        pairs = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
        out = []
        for pair in pairs:
            pair_id = pair.get('pairId') or pair.get('unitId')
            value = value_of(pair)
            original = pair['target']
            row = {'pool': pool, 'id': pair_id, 'fact': value, 'original': original,
                   'verdict': 'machine-clean', 'revised': None, 'reason': ''}
            if original in table:
                seen_values[original].add(value)
                verdict, revised, reason = table[original]
                row.update({'verdict': verdict, 'revised': revised, 'reason': reason})
                if revised is not None:
                    assert revised != original, (pair_id, original)
                    if pair['kind'] == 'moved':
                        assert '→' in value
                    else:
                        after, before = coverage(value, revised), coverage(value, original)
                        assert after >= before, (pair_id, value, original, revised)
                    changed += 1
            records.append(row)
            copy = dict(pair)
            copy['target'] = row['revised'] or original
            out.append(copy)
        audited[pool] = out
    for original, values in seen_values.items():
        assert len(values) == 1, (original, sorted(values))
    flagged = [r for r in records if r['verdict'] != 'machine-clean']
    counts = collections.Counter(r['verdict'] for r in flagged)
    lengths = {'before': collections.Counter(), 'after': collections.Counter()}
    for row in records:
        before, after = len(row['original']), len(row['revised'] or row['original'])
        lengths['before'][before // 5 * 5] += 1
        lengths['after'][after // 5 * 5] += 1
    mean = {k: round(sum(len(r['original']) if k == 'before' else len(r['revised'] or r['original'])
                         for r in records) / len(records), 2) for k in ('before', 'after')}
    summary = {'pairs': len(records), 'flagged': len(flagged), 'rewritten': changed,
               'verdicts': dict(sorted(counts.items())), 'meanChars': mean,
               'lengthHistogram': {k: dict(sorted(v.items())) for k, v in lengths.items()},
               'keptWeak': sorted(KEPT_WEAK),
               'note': 'machine-clean rows were not read one by one; see report for the 41-row sample'}
    AUDIT.mkdir(parents=True, exist_ok=True)
    (AUDIT / 'decisions-r1.json').write_text(
        json.dumps({'summary': summary, 'records': records}, ensure_ascii=False, indent=1) + '\n',
        encoding='utf-8', newline='\n')
    for pool, rows in audited.items():
        path = AUDIT / (pool + '-audited.jsonl')
        text = ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows)
        path.write_text(text, encoding='utf-8', newline='\n')
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
