# Trains the span labeler evaluated by run-labeler-trial.mjs.
#
# Base model: hfl/minirbt-h256 + token-classification head (5 tags). Task:
# mark the character spans of item_used (ITEM) and target (TGT) in the
# player-action text; action_type is NOT this model's job (the classifier
# covers it), and feasibility stays code-side.
#
# Labeling rules (fixed before any training; the browser trial extracts
# spans and compares against them):
# 1. Span = a contiguous character range of the ORIGINAL text, [start, end).
# 2. item_use actions: the used object -> ITEM, what it acts on -> TGT
#    (我用X打开Y: X=ITEM, Y=TGT).
# 3. inspect actions: the inspected object -> TGT, no ITEM ("检查X的Y":
#    X=TGT, Y stays O).
# 4. move / npc_talk: the location / the person -> TGT.
# 5. Person titles stay inside the span ("古德里安教授" whole); title
#    stripping is code-side post-processing, same as the names task.
# 6. Spans are the HEAD NOUN only: 的-phrases and demonstrative/classifier
#    prefixes (那把/半截) are stripped and labeled O — "生锈的铁门钥匙" ->
#    铁门钥匙, "那扇书架后的暗门" -> 暗门, "后院的门" -> 门 (possessor is a
#    modifier). Compounds WITHOUT 的 are whole nouns ("旧锁" is one noun).
#    Training and span scoring both follow this rule.
# 7. At most one span per field per sentence (the task is single-entity);
#    multi-entity sentences never enter corpus or eval.
# 8. MENTIONED-but-not-used objects are O, not ITEM: "我想起了X" / "X还在
#    背包里" label nothing — the tag follows the verb phrase, not the noun.
# 9. Authoring exclusions (hand-written corpus): no body-part instruments
#    (肩膀/膝盖 are never ITEM), no 借/买 frames (ask-vs-take ambiguity),
#    no sentences whose gold span is defensible two ways.
#
# Acceptance protocol (pre-registered; unchanged gates):
# - PRIMARY: on the SEALED acceptance batch (~100 hand-written sentences,
#   slots disjoint from everything trained or evaluated), strict span match
#   (start AND end AND type exact) >= 90% for EACH of ITEM/TGT.
# - Component accepted only if both fields pass AND end-to-end latency
#   (raw text -> spans) stays <= 4s per call in the browser trial.
# - Additionally REPORTED (not gating): both-fields-correct rate.
# - Discipline: acceptance v1 (ec4aa02) and v2 (b5067d7, results in
#   acceptanceRetired below) were each evaluated once and are retired. The
#   sealed batch is evaluated EXACTLY ONCE via `run-labeler-trial.mjs
#   --with-acceptance` after dev results justify it — never during
#   development. dev batches (classic + grouped) are diagnostics only.
# - 铁门钥匙 attribution (settled): the old model output 生锈, the new model
#   outputs 铁门钥匙 — model AND scoring rule (rule 6 v2) changed together
#   in ec4aa02/b5067d7, so that flip is joint attribution; it must not be
#   recorded as "the head-noun rule fixed it".
#
# Data contract (single source of truth): this script is the only place
# that defines corpus/dev/scored/acceptance data. It writes everything to
# artifacts/benchmark/span-labeler-corpus.json — the browser trial loads
# THAT file (and records its sha256 in the report) instead of keeping a
# hand-synced JS copy. After writing, this script READS THE FILE BACK for
# its own evaluation, so Python and browser literally score the same bytes.
#
# Split discipline: the shuffled pool (templates + hand-written train
# groups) is split 10% validation / 90% train BEFORE the manifest is
# written; "train" and "validation" in the manifest are the actual sets.
# devGroups are held out whole PATTERN GROUPS (no sentence of a group is
# trained), so dev measures generalization across sentence patterns.
#
# Usage: python train-span-labeler.py <minirbt-snapshot-dir> [--export-corpus]
#        python train-span-labeler.py --eval-onnx
#        (--eval-onnx scores the FROZEN exported artifacts in
#        frontend/public/models/minirbt-h256-span without retraining; used
#        for decoding-comparison rounds where weights stay fixed)
#
# Decoding comparison (this round, weights+data frozen): greedy per-token
# argmax vs CONSTRAINED sentence decoding — each field picks at most one
# contiguous token range (B- head, I- continuation, empty allowed), spans
# may not overlap, chosen to maximize whole-sentence log-prob (exact
# enumeration). Both decoders are recorded per case in evaluate() and in
# the browser trial, so the decode lever is measured without touching
# data or weights. Diagnosis is MULTI-LABEL: a field can carry several
# defect classes at once (e.g. truncated-o AND truncated-b in one gold
# span) — a single primary class mispointed the cut location before.

import importlib.machinery
import importlib.util
import json
import math
import pathlib
import random
import sys
import types

# base 环境的 pyarrow/h5py 与 numpy 2 二进制不兼容（import 即崩），而
# transformers → generation → sklearn 会连带 import pyarrow；transformers
# 又按元数据认为 TF 可用而在 image_transforms 里真 import tensorflow
# （内部连带 h5py）。训练只走 torch 张量路径，用进程内桩顶住 import，不动
# 用户环境。详见 train-action-classifier.py 同段注释。
try:
    import pyarrow  # noqa: F401
except Exception:
    stub = types.ModuleType("pyarrow")
    stub.__version__ = "16.1.0"  # 合法版本号：pandas 会 parse 它
    stub.__path__ = []
    sys.modules["pyarrow"] = stub
tf_stub = types.ModuleType("tensorflow")
tf_stub.__spec__ = importlib.machinery.ModuleSpec("tensorflow", None)
tf_stub.__path__ = []
sys.modules.setdefault("tensorflow", tf_stub)

import torch
from transformers.models.bert.modeling_bert import BertForTokenClassification
from transformers.models.bert.tokenization_bert_fast import BertTokenizerFast

SEED = 4711
MAX_LEN = 48
TAGS = ["O", "B-ITEM", "I-ITEM", "B-TGT", "I-TGT"]
EPOCHS = 30
BATCH = 16
LR = 3e-4

# ── 模板语料槽位（第一批训练数据；与 devClassic/scored 有历史交集
#    雕像/壁画/暗门/剑，在 ec4aa02 记录在案，不回改）。────────────────
ITEMS = ["铜钥匙", "铁门钥匙", "剑", "扫帚", "地图", "绳索", "水壶", "铁锹", "灯笼", "木桶"]
NPCS = ["诺诺", "执行部学生", "路明非", "古德里安教授", "凯瑟琳"]
LOCS = ["二楼档案室", "卡塞尔学院图书馆", "走廊", "阅览室"]
OBJECTS = ["暗门", "书架", "壁画", "雕像", "窗台"]
OPEN_TARGETS = ["大门", "木箱", "柜子", "抽屉"]

# 10 句开发集 classic（原 held-out 批；已多轮参与排查，只用于定位错误，
# 不再验收）。保留原文以延续 dev ITEM 4→8 / TGT 4→5 的对照序列。
DEV_CLASSIC = [
    ("我用火把照亮地下藏书室。", "火把", "地下藏书室"),
    ("我用短刀割断绳索。", "短刀", "绳索"),
    ("我和图书馆管理员打听暗门。", None, "图书馆管理员"),
    ("我去地下藏书室。", None, "地下藏书室"),
    ("我检查雕像的底座。", None, "雕像"),
    ("我在原地休息。", None, None),
    ("我用指南针校准方向。", "指南针", None),
    ("我把铃铛挂在暗门上。", "铃铛", "暗门"),
    ("我向夏弥打听暗门的来历。", None, "夏弥"),
    ("我用蜡烛照亮壁画。", "蜡烛", "壁画"),
]

# 12 句计分原文。标注规则 v2 起按中心语评分（rule 6）：item 期望改
# "铁门钥匙"；parse LLM 任务的 expect 摘录不变，历史报告保留原评分。
SCORED = [
    ("我用铜钥匙打开大门。", "铜钥匙", "大门"),
    ("我和诺诺打听图书馆的传闻。", None, "诺诺"),
    ("我去二楼档案室查资料。", None, "二楼档案室"),
    ("我使用生锈的铁门钥匙打开大门。", "铁门钥匙", "大门"),
    ("我和执行部学生搭话。", None, "执行部学生"),
    ("我检查那扇书架后的暗门。", None, "暗门"),
    ("我拔剑攻击诺诺。", "剑", "诺诺"),
    ("我在原地休息一会儿。", None, None),
    ("我仔细查看旧笔记里的字迹。", None, "旧笔记"),
    ("我用旧笔记垫住门缝。", "旧笔记", "门缝"),
    ("我去找执行部学生问话。", None, "执行部学生"),
    ("我用路明非的校徽刷开闸机。", "校徽", "闸机"),
]

# 已退役验收批 v2（trial 1791490412586，提交 b5067d7/82d8d41）：评过一次
# 即退役，结果 strict ITEM 6/10、TGT 7/10，loose TGT 8/10。原文保留在
# manifest.acceptanceRetired 供审计；这些槽位不再进入任何新数据。
ACCEPTANCE_RETIRED_V2 = [
    ("我把火钳握在手里。", "火钳", None),
    ("我想起了断桨。", None, None),
    ("我用铜哨示意马夫。", "铜哨", "马夫"),
    ("我检查门环。", None, "门环"),
    ("我在原地蹲了一会儿。", None, None),
    ("我用湿柴塞进灶膛。", "湿柴", "灶膛"),
    ("我用那把断剑撬开后院的门。", "断剑", "门"),
    ("我向马夫打听水井的位置。", None, "马夫"),
    ("断剑还在鞘里。", None, None),
    ("我用蒙尘的火钳拨开灰堆。", "火钳", "灰堆"),
]

# ── 人工编写的训练句式组（本轮新增；每句手写，不做名词排列组合）。
#    定向覆盖上轮四类错例：人名/物品同框架角色对照、领属结构、修饰语
#    干扰、短中心语。跨度以原文子串给出，规则 6 只标中心语。──────────
TRAIN_GROUPS = {
    # 开启/破坏类动作的多种表达（同义动词，不排列名词）。
    "open-varied": [
        ("我用铁钎撬开了井盖。", "铁钎", "井盖"),
        ("我用撬棍顶起了石板。", "撬棍", "石板"),
        ("我用发卡捅开了旧锁。", "发卡", "旧锁"),
        ("我抡起木槌砸开了门闩。", "木槌", "门闩"),
        ("我用刀片划开了信封。", "刀片", "信封"),
        ("我掀开了缸盖。", None, "缸盖"),
    ],
    # 切断/分离类动作的多种表达；末句无工具版对照。
    "cut-varied": [
        ("我用剪刀铰断了风筝线。", "剪刀", "风筝线"),
        ("我用柴刀砍断了藤蔓。", "柴刀", "藤蔓"),
        ("我用手锯锯断了横木。", "手锯", "横木"),
        ("我把缠住的渔线扯断了。", "渔线", None),
        ("我剪断了捆包裹的细绳。", None, "细绳"),
    ],
    # 照明类动作的多种表达；末句含 的-领属修饰。
    "light-varied": [
        ("我用煤油灯照亮了储藏室。", "煤油灯", "储藏室"),
        ("我用火柴点亮了壁灯。", "火柴", "壁灯"),
        ("我举着手电照向洞口。", "手电", "洞口"),
        ("我把马灯挂上了车辕。", "马灯", "车辕"),
        ("我用磷光瓶照出了墙上的记号。", "磷光瓶", "记号"),
    ],
    # 放置类：容器/支点作 TGT。
    "place-varied": [
        ("我把油纸包塞进了墙洞。", "油纸包", "墙洞"),
        ("我把铜钱放回了供桌。", "铜钱", "供桌"),
        ("我把梯子搭在了墙头。", "梯子", "墙头"),
        ("我把蓑衣盖在水缸上。", "蓑衣", "水缸"),
        ("我把竹席铺在了阁楼上。", "竹席", "阁楼"),
    ],
    # 人物问询的多种表达；打听/请教宾语均 O（规则 8）。
    "talk-varied": [
        ("我向更夫打听城门的规矩。", None, "更夫"),
        ("我找账房先生问了个明白。", None, "账房先生"),
        ("我和守闸的老倪攀谈起来。", None, "老倪"),
        ("我向绣娘请教纹样的来历。", None, "绣娘"),
        ("我向药铺伙计打听郎中的住处。", None, "药铺伙计"),
    ],
    # 移动类地点的多种表达。
    "move-varied": [
        ("我溜进了西跨院。", None, "西跨院"),
        ("我从角门折回了前厅。", None, "前厅"),
        ("我沿着回廊走到了内宅。", None, "内宅"),
        ("我潜入了地窖。", None, "地窖"),
        ("我一口气跑上了钟楼。", None, "钟楼"),
    ],
    # 领属结构 TGT 侧：领属者 O，中心语 TGT（后院的门→门 的训练面）。
    "possessor-target": [
        ("我撬开了柴房的挂锁。", None, "挂锁"),
        ("我用马蹄铁砸开了马厩的门锁。", "马蹄铁", "门锁"),
        ("我擦亮了灶王爷的牌位。", "牌位", None),
        ("我推开了祠堂的角门。", None, "角门"),
        ("我转动了石塔的兽首。", None, "兽首"),
    ],
    # 领属结构 ITEM 侧：人的领属者 O，中心语 ITEM（与 talk 组人物 TGT 对照）。
    "possessor-item": [
        ("我用陈师傅的凿子起出了锈钉。", "凿子", "锈钉"),
        ("我用花匠的枝剪铰掉了枯枝。", "枝剪", "枯枝"),
        ("我用庙祝的钥匙打开了偏殿的门。", "钥匙", "门"),
        ("我用守墓人的风灯照了照碑文。", "风灯", "碑文"),
    ],
    # 同框架 人/物 角色对照：递给/交给 人→人 TGT；同物品再用作物。
    "person-object-contrast": [
        ("我把油布递给了艄公。", None, "艄公"),
        ("我把油布铺在了筏底。", "油布", "筏底"),
        ("我向船家打听渡口的远近。", None, "船家"),
        ("我检查了船底的裂缝。", None, "船底"),
        ("我把缆绳交给了纤夫。", None, "纤夫"),
        ("我用缆绳捆紧了货箱。", "缆绳", "货箱"),
    ],
    # 提及不标（规则 8）：名词出现但无使用动作。
    "mention-extended": [
        ("我的行囊里还剩半卷麻绳。", None, None),
        ("我忽然想起了当票上的日子。", None, None),
        ("清单末尾添着火油。", None, None),
        ("背包侧袋里插着那把伞兵刀。", None, None),
        ("我对着账本出了半天神。", None, None),
    ],
    # 处置类 item-only（无作用对象）；末句 塞回封套→封套 TGT 对照。
    "item-only-disposition": [
        ("我把断刀擦干了收好。", "断刀", None),
        ("我把怀表上了弦。", "怀表", None),
        ("我把望远镜举起来又放下。", "望远镜", None),
        ("我把符纸折好塞回了封套。", "符纸", "封套"),
        ("我把断弦换了下来。", "断弦", None),
    ],
    # 检查类动词变体；含 X的Y→X 规则。
    "inspect-varied": [
        ("我打量着神龛。", None, "神龛"),
        ("我翻看了地契。", None, "地契"),
        ("我凑近端详铜镜的铭文。", None, "铜镜"),
        ("我仔细检查了锚链的磨损。", None, "锚链"),
        ("我查验了火漆的印痕。", None, "火漆"),
    ],
    # 单字中心语（上轮截断错例的高危形态）。
    "single-char-heads": [
        ("我抽出了刀。", "刀", None),
        ("我点亮了灯。", None, "灯"),
        ("我推开了虚掩的门。", None, "门"),
        ("我用竹篙撑住了船。", "竹篙", "船"),
        ("我把刀插回了鞘。", "刀", "鞘"),
    ],
    # 修饰语干扰：的-短语与指示/量词前缀均 O。
    "modifier-expansion": [
        ("我用那串钥匙打开了侧门。", "钥匙", "侧门"),
        ("我用半截铅笔拓下了石刻。", "铅笔", "石刻"),
        ("我用卷了边的海图找到了水道。", "海图", "水道"),
        ("我检查了那扇雕花的屏风。", None, "屏风"),
        ("我用烧焦的木棍拨了拨火堆。", "木棍", "火堆"),
        ("我用湿透的抹布擦净了碑座。", "抹布", "碑座"),
    ],
    # 物品互作用与同物品跨角色。
    "cross-role-objects": [
        ("我用马蹄铁敲了敲拴马桩。", "马蹄铁", "拴马桩"),
        ("我用簪子挑开了封蜡。", "簪子", "封蜡"),
        ("我用铜盆接住了檐水。", "铜盆", "檐水"),
        ("我用鼎腿压住了席角。", "鼎腿", "席角"),
        ("我把鼎腿搬到了廊下。", "鼎腿", "廊下"),
    ],
}

# ── 整组划入 dev 的句式组（组内任何句子都不进训练；dev 只作诊断，
#    衡量跨句式泛化）。槽位与全部训练跨度不相交。────────────────────
DEV_GROUPS = {
    # 领属结构（当铺域）：领属者 O + 中心语，覆盖 use/inspect/处置。
    "dev-possession-shop": [
        ("我推开了当铺的栅门。", None, "栅门"),
        ("我撬开了钱柜的铜锁。", None, "铜锁"),
        ("我用朝奉的戥子称了称香料。", "戥子", "香料"),
        ("我擦亮了掌柜的烟杆。", "烟杆", None),
        ("我检查了账台的暗屉。", None, "账台"),
        ("我把算盘摆正了。", "算盘", None),
        ("我朝伙计问了问行情。", None, "伙计"),
        ("我把当票折好收进了钱匣。", "当票", "钱匣"),
    ],
    # 人/物 同框架对照（码头域）。
    "dev-person-object-dock": [
        ("我把斗笠递给了船娘。", None, "船娘"),
        ("我把斗笠扣在了米瓮上。", "斗笠", "米瓮"),
        ("我向舵工打听水路。", None, "舵工"),
        ("我检查了舵杆的裂纹。", None, "舵杆"),
        ("我把麻缆盘在了缆桩上。", "麻缆", "缆桩"),
        ("我用长篙撑开了渡船。", "长篙", "渡船"),
        ("我把水瓢递给了守滩人。", None, "守滩人"),
        ("我向守滩人打听潮汛。", None, "守滩人"),
    ],
    # 修饰语堆叠：双重 的-短语、指示+量词前缀。
    "dev-modifier-stack": [
        ("我用那把磨得发亮的剪子铰开了线头。", "剪子", "线头"),
        ("我把缺了口的粗碗扣在了案板上。", "粗碗", "案板"),
        ("我检查了那盏积灰的油盏。", None, "油盏"),
        ("我用浸过油的火绒引燃了柴堆。", "火绒", "柴堆"),
        ("我把卷了角的图纸铺平了。", "图纸", None),
        ("我用那半截蜡笔涂黑了封皮。", "蜡笔", "封皮"),
        ("我掀开了蒙着白布的笼屉。", None, "笼屉"),
        ("我用斑驳的铜章在封泥上按了个印。", "铜章", "封泥"),
    ],
    # 单字/超短中心语（全新槽位）。
    "dev-short-heads": [
        ("我扳开了闸。", None, "闸"),
        ("我捅了捅灶。", None, "灶"),
        ("我擦了擦匾。", "匾", None),
        ("我把小艇系在了桩上。", "小艇", "桩"),
        ("我用竹钩勾住了檐。", "竹钩", "檐"),
        ("我拔出了短刃。", "短刃", None),
        ("我抵住了栅栏。", None, "栅栏"),
    ],
}

# ── 封存验收批 v3（100 句手写；槽位与训练/dev/scored/devClassic/退役批
#    全不相交，程序断言把关）。协议：dev 出现可信改善后，用
#    run-labeler-trial.mjs --with-acceptance 恰好评一次；本轮不评。
#    批内故意保留同名词跨角色对照（如 提灯/枣红马/麻绳）与提及-使用
#    对照（篾刀/油纸伞/稻草），检验规则 2/6/8 的联合泛化。────────────
ACCEPTANCE_SEALED = {
    # 人名 vs 物品 同框架角色对照（上轮 马夫→ITEM 类错例）。
    "ac-person-object": [
        ("我把咸鱼干递给了货郎。", None, "货郎"),
        ("我把咸鱼干挂上了房梁。", "咸鱼干", "房梁"),
        ("我向皮匠打听硝皮的手艺。", None, "皮匠"),
        ("我和皮匠聊起了鞣皮的方子。", None, "皮匠"),
        ("我把角子塞给了门房。", None, "门房"),
        ("我把角子丢进了功德箱。", "角子", "功德箱"),
        ("我和酒保打听北仓的动静。", None, "酒保"),
        ("我敲了敲酒保的案几。", None, "案几"),
        ("我把缰绳抛给了马倌。", None, "马倌"),
        ("我请说书人讲了一段旧事。", None, "说书人"),
    ],
    # 领属结构 TGT 侧（上轮 后院的门→门 错例）。
    "ac-possessor-target": [
        ("我推开了磨坊的板门。", None, "板门"),
        ("我撬开了油坊的侧栅。", None, "侧栅"),
        ("我用镐头刨开了染坊的门槛。", "镐头", "门槛"),
        ("我擦亮了山神庙的香案。", "香案", None),
        ("我用拨火棍捅了捅窑膛。", "拨火棍", "窑膛"),
        ("我扫净了碾坊的碾盘。", "碾盘", None),
        ("我用竹梯爬上了谷仓的顶棚。", "竹梯", "顶棚"),
        ("我检查了驿站的拴马环。", None, "拴马环"),
        ("我敲响了渡口的铜锣。", None, "铜锣"),
        ("我压灭了窑口的余烬。", None, "余烬"),
    ],
    # 领属结构 ITEM 侧。
    "ac-possessor-item": [
        ("我用货郎的扁担挑起了箩筐。", "扁担", "箩筐"),
        ("我用皮匠的锥子撬开了线结。", "锥子", "线结"),
        ("我用樵夫的斧头劈开了桦木墩。", "斧头", "桦木墩"),
        ("我用驿卒的火镰引着了枯草。", "火镰", "枯草"),
        ("我用磨刀匠的磨石蹭快了镰刃。", "磨石", "镰刃"),
        ("我用香客的蒲团垫住了龛脚。", "蒲团", "龛脚"),
        ("我用篾匠的篾刀削尖了竹签。", "篾刀", "竹签"),
        ("我用门房的提灯照见了照壁。", "提灯", "照壁"),
        ("我用说书人的醒木拍了拍桌角。", "醒木", "桌角"),
        ("我用酒保的银钎凿开了冰面。", "银钎", "冰面"),
    ],
    # 修饰语干扰（上轮 蒙尘的火钳→蒙 类错例）。
    "ac-modifier-interference": [
        ("我用锃亮的撬钩别开了铜闩。", "撬钩", "铜闩"),
        ("我把缺了口的陶碗摞了起来。", "陶碗", None),
        ("我用沾满油污的火叉拨旺了炉膛。", "火叉", "炉膛"),
        ("我检查了那面描金的插屏。", None, "插屏"),
        ("我用烧掉了半边的蒲扇扇旺了炭盆。", "蒲扇", "炭盆"),
        ("我用豁了口的木瓢搅动了酒酿。", "木瓢", "酒酿"),
        ("我把打了补丁的斗篷叠好了。", "斗篷", None),
        ("我用缠着布条的木杠顶住了书案。", "木杠", "书案"),
        ("我用褪了色的红线捆好了书匣。", "红线", "书匣"),
        ("我检查了那盏罩着纱的宫灯。", None, "宫灯"),
    ],
    # 短中心语（上轮 铜/灰/断剑 截断类错例）。
    "ac-short-heads": [
        ("我用湿麻绳捆紧了苇席。", "麻绳", "苇席"),
        ("我推倒了那堵矮墙。", None, "矮墙"),
        ("我把谷糠拌进了槽。", "谷糠", "槽"),
        ("我用铜钩勾起了井绳。", "铜钩", "井绳"),
        ("我搬开了窖口的青石。", None, "青石"),
        ("我卸下了门板。", None, "门板"),
        ("我把稻草添进了圈。", "稻草", "圈"),
        ("我扣上了窗板。", None, "窗板"),
        ("我用木杵舂起了谷。", "木杵", "谷"),
        ("我插上了闩。", None, "闩"),
    ],
    # 处置类 item-only。
    "ac-item-only": [
        ("我把马鞭甩得啪啪响。", "马鞭", None),
        ("我把绑腿扎紧了。", "绑腿", None),
        ("我把木哨吹响了。", "木哨", None),
        ("我把褡裢挎好了。", "褡裢", None),
        ("我把舆图摊开又卷起。", "舆图", None),
        ("我把算筹摆弄了半天。", "算筹", None),
        ("我磕了磕旱烟锅。", "旱烟锅", None),
        ("我把油纸伞撑开又收拢。", "油纸伞", None),
        ("我把墨条研开了。", "墨条", None),
        ("我把护身符攥出了汗。", "护身符", None),
    ],
    # 提及不标（含与同批使用句的跨角色对照：褡裢/篾刀/油纸伞/稻草/铜锣）。
    "ac-mention": [
        ("我想起了槽头的那把铡刀。", None, None),
        ("我的褡裢还挂在钉子上。", None, None),
        ("篾刀就别在工具筐里。", None, None),
        ("伞架上还插着那把油纸伞。", None, None),
        ("谷仓里堆着陈年的稻草。", None, None),
        ("我惦记着没买成的毡靴。", None, None),
        ("铜锣声还在巷子里回响。", None, None),
        ("我盘算着找谁借盘缠。", None, None),
        ("药锄靠在篱笆边没人动。", None, None),
        ("我盯着账目发了半天怔。", None, None),
    ],
    # 同一动作的多种表达（开启/切断/捆扎/撬移）。
    "ac-action-paraphrase": [
        ("我扛着原木撞开了柴门。", "原木", "柴门"),
        ("我用短斧砸开了栅栏门。", "短斧", "栅栏门"),
        ("我抡圆了锤子砸开了砖垛。", "锤子", "砖垛"),
        ("我用镰刀削断了芦苇。", "镰刀", "芦苇"),
        ("我用石头砸弯了插销。", "石头", "插销"),
        ("我用麻绳绞紧了木筏。", "麻绳", "木筏"),
        ("我用皮条箍紧了陶瓮。", "皮条", "陶瓮"),
        ("我用撬杠挪开了堵路的顽石。", "撬杠", "顽石"),
        ("我用扁担挑开了门帘。", "扁担", "门帘"),
        ("我用竹竿探到了河床。", "竹竿", "河床"),
    ],
    # 检查类动词变体（查验/端详/翻检/清点/掂/试）。
    "ac-inspect-varied": [
        ("我查验了染缸的釉色。", None, "染缸"),
        ("我端详了壶身的款识。", None, "壶身"),
        ("我翻检了樟木箱的夹层。", None, "樟木箱"),
        ("我打量了套着新缰的马。", None, "马"),
        ("我清点了滞销的粗盐。", None, "粗盐"),
        ("我嗅了嗅坛口。", None, "坛口"),
        ("我掂了掂那锭官银。", None, "官银"),
        ("我试了试弩机。", None, "弩机"),
        ("我翻看了账册的末页。", None, "账册"),
        ("我查验了橱门的合页。", None, "橱门"),
    ],
    # 批内跨角色对照（同名词在不同句里分属 ITEM/TGT/提及）。
    "ac-cross-role": [
        ("我用瓦盆接住了檐溜。", "瓦盆", "檐溜"),
        ("我把瓦盆擦干扣在了案头。", "瓦盆", "案头"),
        ("我把提灯挂上了门楼。", "提灯", "门楼"),
        ("我从门楼底下取回了提灯。", "提灯", None),
        ("我向货郎讨了碗凉茶。", None, "货郎"),
        ("我把凉茶泼在了车辙里。", "凉茶", "车辙"),
        ("我刷洗了马槽。", None, "马槽"),
        ("我牵出了枣红马。", "枣红马", None),
        ("我用鬃刷刷顺了枣红马。", "鬃刷", "枣红马"),
        ("我用鬃刷扫了扫鞍子。", "鬃刷", "鞍子"),
    ],
}

# 逐字诊断的错误类别（Python 与浏览器共用同一分类口径，见 diagnose_field）。
# 多标签：一个字段可同时命中多类（如 O 截断与实体内重复 B 共存，各自独立
# 成立、都如实记录——单一"主类"会误指截断位置）；无缺陷时返回 ["ok"]。
# 列表顺序 = 下面的规范顺序。
ERROR_CLASSES = [
    "ok",                # 无缺陷（金标与预测均为空，或严格命中）
    "span-false",        # 金标无跨度、模型给出跨度
    "span-missing",      # 金标有跨度、模型未给出该字段跨度
    "all-o",             # 金标字符全部被预测成 O（span-missing 的成因）
    "truncated-o",       # 实体内部出现 O，截断了跨度
    "truncated-b",       # 实体内部又出现 B-（解码首组胜出，同样截断）
    "wrong-field",       # 金标字符或预测跨度落在另一字段
    "over-extended",     # 预测跨度完整覆盖金标但越界
    "boundary-mismatch", # 与金标相交但互不包含
    "modifier-as-head",  # 预测跨度完全落在中心语前的修饰/领属区（的 分隔）
    "displaced",         # 与金标不相交、不落在修饰区、也不压另一字段金标
]
_CLASS_RANK = {name: i for i, name in enumerate(ERROR_CLASSES)}


def rows_of(groups):
    """{group: [(text, item, target)...]} -> flat [(group, text, item, target)]."""
    return [(g, *row) for g, rows in groups.items() for row in rows]


def locate(text, span):
    """Substring -> unique char range; asserts the occurrence is unique."""
    n = text.count(span)
    assert n == 1, f"span {span!r} occurs {n}x in {text!r}; gold would be ambiguous"
    start = text.index(span)
    return (start, start + len(span))


def build_template_corpus():
    """Templates with tracked spans -> (text, item_range, target_range)."""
    corpus = []

    def emit(segments):
        text = ""
        item = None
        target = None
        for kind, content in segments:
            if kind == "lit":
                text += content
                continue
            start = len(text)
            text += content
            slot = "item" if kind == "ITEM" else "target"
            if {"item": item, "target": target}[slot] is None:
                if slot == "item":
                    item = (start, start + len(content))
                else:
                    target = (start, start + len(content))
        corpus.append((text, item, target))

    for item in ITEMS:
        for target in OPEN_TARGETS:
            emit([("lit", "我用"), ("ITEM", item), ("lit", "打开"), ("TGT", target), ("lit", "。")])
            emit([("lit", "我用"), ("ITEM", item), ("lit", "砸开"), ("TGT", target), ("lit", "。")])
            emit([("lit", "我用"), ("ITEM", item), ("lit", "锁上"), ("TGT", target), ("lit", "。")])
        for target in OBJECTS:
            emit([("lit", "我用"), ("ITEM", item), ("lit", "撬开"), ("TGT", target), ("lit", "。")])
            emit([("lit", "我用"), ("ITEM", item), ("lit", "照亮"), ("TGT", target), ("lit", "。")])
            emit([("lit", "我用"), ("ITEM", item), ("lit", "把"), ("TGT", target), ("lit", "压住。")])
        # 规则审计修正：被作用物一律 TGT（此前 撑住书架/敲了敲书架/割断绳子
        # 漏标 TGT，检查{item}的齿纹误标 ITEM——inspect 无 ITEM，见规则 3）。
        emit([("lit", "我用"), ("ITEM", item), ("lit", "撑住"), ("TGT", "书架"), ("lit", "。")])
        emit([("lit", "我用"), ("ITEM", item), ("lit", "割断"), ("TGT", "绳子"), ("lit", "。")])
        emit([("lit", "我用"), ("ITEM", item), ("lit", "敲了敲"), ("TGT", "书架"), ("lit", "。")])
        emit([("lit", "我把"), ("ITEM", item), ("lit", "靠在"), ("TGT", "暗门"), ("lit", "边。")])
        emit([("lit", "我把"), ("ITEM", item), ("lit", "收进"), ("TGT", "背包"), ("lit", "。")])
        emit([("lit", "我检查"), ("TGT", item), ("lit", "的齿纹。")])
    for npc in NPCS:
        emit([("lit", "我和"), ("TGT", npc), ("lit", "搭话。")])
        emit([("lit", "我和"), ("TGT", npc), ("lit", "打听图书馆的传闻。")])
        emit([("lit", "我和"), ("TGT", npc), ("lit", "打听暗门的来历。")])
        emit([("lit", "我向"), ("TGT", npc), ("lit", "询问暗门的下落。")])
    for loc in LOCS:
        emit([("lit", "我去"), ("TGT", loc), ("lit", "。")])
        emit([("lit", "我去"), ("TGT", loc), ("lit", "查资料。")])
        emit([("lit", "我沿着楼梯走到"), ("TGT", loc), ("lit", "。")])
        emit([("lit", "我前往"), ("TGT", loc), ("lit", "。")])
        emit([("lit", "我返回"), ("TGT", loc), ("lit", "。")])
    for obj in OBJECTS:
        emit([("lit", "我检查"), ("TGT", obj), ("lit", "。")])
        emit([("lit", "我仔细查看"), ("TGT", obj), ("lit", "上的痕迹。")])
        emit([("lit", "我观察"), ("TGT", obj), ("lit", "。")])
        emit([("lit", "我搜索"), ("TGT", obj), ("lit", "。")])
        emit([("lit", "我把"), ("ITEM", "扫帚"), ("lit", "放在"), ("TGT", obj), ("lit", "旁边。")])
    corpus.extend([
        ("我在原地休息一会儿。", None, None),
        ("我在原地缓了缓。", None, None),
        ("我靠在门边等一等。", None, None),
        ("我整理了一下背包。", None, None),
        ("我深吸一口气。", None, None),
        ("我坐下来歇了口气。", None, None),
    ])
    for npc in NPCS:
        # 规则审计修正：拔剑的"剑"是被使用的物品 → ITEM（此前漏标）。
        emit([("lit", "我拔"), ("ITEM", "剑"), ("lit", "攻击"), ("TGT", npc), ("lit", "。")])

    # ── 覆盖补充（用户指示）：item-only、提及不标、同物品跨角色、
    #    修饰语句式、实体长度变化。─────────────────────────────────────
    # item-only：处置物品但没有明确作用对象。
    for item in ITEMS:
        emit([("lit", "我把"), ("ITEM", item), ("lit", "握紧了。")])
        emit([("lit", "我把"), ("ITEM", item), ("lit", "攥在手里。")])
        emit([("lit", "我把"), ("ITEM", item), ("lit", "擦了又擦。")])
        emit([("lit", "我把"), ("ITEM", item), ("lit", "举过头顶。")])
        emit([("lit", "我把"), ("ITEM", item), ("lit", "收好。")])
    # 提及不标（规则 8）：物品名词出现但无使用动作，双字段皆空。
    for item in ITEMS:
        emit([("lit", "我想起了"), ("lit", item), ("lit", "。")])
        emit([("lit", item), ("lit", "还在背包里。")])
        emit([("lit", "背包里只有"), ("lit", item), ("lit", "。")])
    # 同物品跨角色：同一名词在 inspect 句作 TGT、在 use 句作 ITEM；
    # 物品与物品互相作用（i1 为 ITEM、i2 为 TGT）。
    for item in ITEMS:
        emit([("lit", "我检查"), ("TGT", item), ("lit", "。")])
    for item_a in ITEMS:
        for item_b in ITEMS:
            if item_a != item_b:
                emit([("lit", "我用"), ("ITEM", item_a), ("lit", "撬开"), ("TGT", item_b), ("lit", "。")])
    # 修饰语句式（规则 6）：修饰语标 O，只标中心语。
    for item in ITEMS:
        emit([("lit", "我用生锈的"), ("ITEM", item), ("lit", "打开"), ("TGT", "大门"), ("lit", "。")])
        emit([("lit", "我用那把"), ("ITEM", item), ("lit", "撬开"), ("TGT", "木箱"), ("lit", "。")])
    for obj in OBJECTS:
        emit([("lit", "我检查上锁的"), ("TGT", obj), ("lit", "。")])
    for loc in LOCS:
        emit([("lit", "我走进昏暗的"), ("TGT", loc), ("lit", "。")])

    # 排除全部计分句、开发句、验收句原文；断言干净。
    excluded = (
        {text for text, _, _ in SCORED}
        | {text for text, _, _ in DEV_CLASSIC}
        | {text for text, _, _ in ACCEPTANCE_RETIRED_V2}
        | {text for _, text, _, _ in rows_of(DEV_GROUPS)}
        | {text for _, text, _, _ in rows_of(ACCEPTANCE_SEALED)}
    )
    corpus = [(text, i, t) for text, i, t in corpus if text not in excluded]
    assert len({text for text, _, _ in corpus}) == len(corpus)
    return corpus


def check_discipline(template_corpus):
    """程序化把关：验收批/分组 dev 与训练数据的槽位、原文均不相交。

    历史交集（devClassic/scored 的 雕像/壁画/暗门/剑）在 ec4aa02 记录在
    案，属遗留问题，不在此约束范围内。
    """
    template_spans = set()
    for text, item, target in template_corpus:
        template_spans.add(text[item[0]: item[1]] if item else None)
        template_spans.add(text[target[0]: target[1]] if target else None)
    template_spans.discard(None)

    handwritten_spans = {
        span for _, text, item, target in rows_of(TRAIN_GROUPS)
        for span in (item, target) if span
    }
    dev_classic_spans = {s for _, i, t in DEV_CLASSIC for s in (i, t) if s}
    scored_spans = {s for _, i, t in SCORED for s in (i, t) if s}
    retired_spans = {s for _, i, t in ACCEPTANCE_RETIRED_V2 for s in (i, t) if s}
    dev_group_spans = {
        span for _, text, item, target in rows_of(DEV_GROUPS)
        for span in (item, target) if span
    }
    sealed_spans = {
        span for _, text, item, target in rows_of(ACCEPTANCE_SEALED)
        for span in (item, target) if span
    }

    def overlap(name, a, b):
        inter = a & b
        assert not inter, f"slot discipline violated ({name}): {sorted(inter)}"

    overlap("handwritten-train vs templates", handwritten_spans, template_spans)
    overlap("handwritten-train vs devClassic", handwritten_spans, dev_classic_spans)
    overlap("handwritten-train vs scored", handwritten_spans, scored_spans)
    overlap("devGroups vs train (templates+handwritten)", dev_group_spans, template_spans | handwritten_spans)
    overlap("devGroups vs scored", dev_group_spans, scored_spans)
    overlap("devGroups vs devClassic", dev_group_spans, dev_classic_spans)
    overlap(
        "sealed acceptance vs everything trainable/evaluated",
        sealed_spans,
        template_spans | handwritten_spans | dev_group_spans | dev_classic_spans | scored_spans | retired_spans,
    )

    trained_texts = (
        {text for text, _, _ in template_corpus}
        | {text for _, text, _, _ in rows_of(TRAIN_GROUPS)}
    )
    eval_texts = (
        {text for text, _, _ in DEV_CLASSIC}
        | {text for text, _, _ in SCORED}
        | {text for _, text, _, _ in rows_of(DEV_GROUPS)}
        | {text for _, text, _, _ in rows_of(ACCEPTANCE_SEALED)}
        | {text for text, _, _ in ACCEPTANCE_RETIRED_V2}
    )
    assert not (trained_texts & eval_texts), "verbatim sentence leaked across splits"
    assert len({t for _, t, _, _ in rows_of(ACCEPTANCE_SEALED)}) == sum(
        len(rows) for rows in ACCEPTANCE_SEALED.values()
    )


def spans_to_tags(text, item, target, tokenizer):
    """Char-level tags -> wordpiece-token tags via offset mapping."""
    char_tags = ["O"] * len(text)
    for span, base in ((item, "ITEM"), (target, "TGT")):
        if span is None:
            continue
        start, end = span
        char_tags[start] = f"B-{base}"
        for pos in range(start + 1, end):
            char_tags[pos] = f"I-{base}"
    encoded = tokenizer(text, truncation=True, max_length=MAX_LEN, return_offsets_mapping=True)
    labels = []
    for (token_start, token_end) in encoded["offset_mapping"]:
        if token_end == 0:
            labels.append(-100)  # [CLS]/[SEP]/[PAD]
            continue
        # 词片段完全落在某标签内才继承；跨界片段（ASCII 词边界）记 O。
        mid = (token_start + token_end) // 2
        labels.append(TAGS.index(char_tags[mid]) if mid < len(char_tags) else TAGS.index("O"))
    return encoded["input_ids"], labels


def tags_to_spans(text, offsets, tag_ids):
    """Model output -> (item_span, target_span) character ranges.

    组尾取组内最后一个词片段的结束位置（审查发现：句末特殊标记的起点是
    0，用"下一个 token 的起点"当组尾会产出 [x,0] 这类错区间）。
    """
    spans = {"ITEM": None, "TGT": None}
    current = None  # [type, start, end]
    for tag_id, (token_start, token_end) in zip(tag_ids, offsets):
        if token_end == 0 or tag_id >= len(TAGS):
            tag = "O"  # [CLS]/[SEP]
        else:
            tag = TAGS[tag_id]
        if tag.startswith("I-") and current is not None and current[0] == tag[2:]:
            current[2] = token_end  # 延续当前组，组尾前移到本片段末尾
            continue
        # O 或 B-/游离 I-：先按组内末片段结束位置落盘当前组
        if current is not None and spans[current[0]] is None:
            spans[current[0]] = (current[1], current[2])
        if tag == "O":
            current = None
        else:
            current = [tag[2:], token_start, token_end]
    if current is not None and spans[current[0]] is None:
        spans[current[0]] = (current[1], current[2])
    return spans["ITEM"], spans["TGT"]


def diagnose_field(text, gold, pred, other_gold, token_rows, field, other):
    """单字段错误归类：多标签列表（规范序见 ERROR_CLASSES），无缺陷返回 ["ok"]。

    token_rows: [{"start","end","gold","pred"}]，gold/pred 为 "O"/"B-ITEM"/...
    与 run-labeler-trial.mjs 的 diagnoseField 同口径。
    """
    if gold is None:
        if pred is None:
            return ["ok"]
        classes = ["span-false"]
        if other_gold and pred[0] < other_gold[1] and other_gold[0] < pred[1]:
            classes.append("wrong-field")
        return _order(classes)
    gold_tokens = [row for row in token_rows if row["start"] < gold[1] and gold[0] < row["end"]]
    preds = [row["pred"] for row in gold_tokens]
    mine = (f"B-{field}", f"I-{field}")
    theirs = (f"B-{other}", f"I-{other}")
    classes = []
    if all(p == "O" for p in preds):
        classes.append("all-o")
    elif any(p == "O" for p in preds) and any(p in mine for p in preds):
        classes.append("truncated-o")
    if any(row["gold"] == f"I-{field}" and row["pred"] == f"B-{field}" for row in gold_tokens):
        classes.append("truncated-b")
    if any(p in theirs for p in preds):
        classes.append("wrong-field")
    if pred is None:
        classes.append("span-missing")
        return _order(classes)
    if pred == gold:
        return ["ok"]
    if pred[0] < gold[1] and gold[0] < pred[1]:  # 相交
        classes.append("over-extended" if gold[0] <= pred[0] and pred[1] <= gold[1] else "boundary-mismatch")
        return _order(classes)
    # 不相交
    if other_gold and pred[0] < other_gold[1] and other_gold[0] < pred[1]:
        classes.append("wrong-field")
    if pred[1] <= gold[0] and ("的" in text[pred[1]: gold[0]] or text[pred[0]: pred[1]].endswith("的")):
        classes.append("modifier-as-head")
    else:
        classes.append("displaced")
    return _order(classes)


def _order(classes):
    return sorted(set(classes), key=_CLASS_RANK.get)


def constrained_decode(offsets, probs):
    """整句约束解码：每字段至多一段连续词片段（首词 B-、段内 I-，允许空），
    两段不得重叠，在全部片段的五类概率上最大化整句对数概率（精确枚举）。

    枚举顺序固定（空、i 升、j 升；平局取先枚举者），Python 与 JS 同序，
    保证同 logits 产出一致结果。返回 (item_span, target_span, assigned_ids)。
    """
    idx = [i for i, (_, end) in enumerate(offsets) if end != 0]
    n = len(idx)
    if n == 0:
        return None, None, [0] * len(offsets)
    log_p = [[math.log(max(p, 1e-12)) for p in row] for row in probs]

    def options(field):
        b, cont, o = (TAGS.index(f"B-{field}"), TAGS.index(f"I-{field}"), TAGS.index("O"))
        opts = [(0.0, None, None)]
        for a in range(n):
            gain = log_p[idx[a]][b] - log_p[idx[a]][o]
            for j in range(a, n):
                if j > a:
                    gain += log_p[idx[j]][cont] - log_p[idx[j]][o]
                opts.append((gain, a, j))
        return opts

    item_opts = options("ITEM")
    tgt_opts = options("TGT")
    best = None
    for gi, ai, aj in item_opts:
        for gt, bi, bj in tgt_opts:
            if ai is not None and bi is not None and ai <= bj and bi <= aj:
                continue  # 词片段重叠
            if best is None or gi + gt > best[0]:
                best = (gi + gt, ai, aj, bi, bj)
    _, ai, aj, bi, bj = best
    assignment = ["O"] * n
    for (x, y), field in (((ai, aj), "ITEM"), ((bi, bj), "TGT")):
        if x is None:
            continue
        assignment[x] = f"B-{field}"
        for t in range(x + 1, y + 1):
            assignment[t] = f"I-{field}"
    ids = [0] * len(offsets)
    for k, t in enumerate(idx):
        ids[t] = TAGS.index(assignment[k])
    item = None if ai is None else (offsets[idx[ai]][0], offsets[idx[aj]][1])
    target = None if bi is None else (offsets[idx[bi]][0], offsets[idx[bj]][1])
    return item, target, ids


def diagnose(text, item, target, offsets, assigned_ids, probs):
    """整句逐 token 诊断：逐字金标/预测/概率 + 分字段多标签错误归类。

    assigned_ids 是某一解码方式（贪心或约束）落盘的逐 token 标签。
    """
    gold_spans = {}
    for name, expected in (("ITEM", item), ("TGT", target)):
        gold_spans[name] = (
            (text.index(expected), text.index(expected) + len(expected)) if expected else None
        )
    token_rows = []
    for (token_start, token_end), tag_id, prob_row in zip(offsets, assigned_ids, probs):
        if token_end == 0:
            continue  # [CLS]/[SEP]
        mid = (token_start + token_end) // 2
        gold_tag = "O"
        for name in ("ITEM", "TGT"):
            span = gold_spans[name]
            if span and span[0] <= mid < span[1]:
                gold_tag = f"{'B' if mid == span[0] else 'I'}-{name}"
                break
        token_rows.append({
            "start": token_start,
            "end": token_end,
            "ch": text[token_start:token_end],
            "gold": gold_tag,
            "pred": TAGS[tag_id],
            "pPred": round(float(prob_row[tag_id]), 4),
            "pGold": round(float(prob_row[TAGS.index(gold_tag)]), 4),
        })
    pred_item, pred_target = tags_to_spans(text, offsets, assigned_ids)
    return {
        "tokens": token_rows,
        "item": diagnose_field(text, gold_spans["ITEM"], pred_item, gold_spans["TGT"], token_rows, "ITEM", "TGT"),
        "target": diagnose_field(text, gold_spans["TGT"], pred_target, gold_spans["ITEM"], token_rows, "TGT", "ITEM"),
        "predItem": text[pred_item[0]: pred_item[1]] if pred_item else None,
        "predTarget": text[pred_target[0]: pred_target[1]] if pred_target else None,
    }


def evaluate(forward, cases, detail="tokens"):
    """detail: "tokens"（dev 批，含逐字记录）| "diagnosis"（仅归类）| None。

    记录先行：两种解码的全部预测先写进 row，再评分——期望为空、预测非空时
    预测文本也必须落盘（此前 Python 只在双非空分支写预测，false-positive
    行 predItem=None 却 strict=False，无法核对两端逐例一致）。
    """
    modes = ("greedy", "constrained")
    strict = {m: {"ITEM": [0, 0], "TGT": [0, 0]} for m in modes}
    loose = {m: {"ITEM": [0, 0], "TGT": [0, 0]} for m in modes}
    both = {m: [0, 0] for m in modes}
    rows = []
    for case in cases:
        text, item, target = case["text"], case["item"], case["target"]
        offsets, greedy_ids, probs = forward(text)
        decodes = {
            "greedy": tags_to_spans(text, offsets, greedy_ids) + (greedy_ids,),
            "constrained": constrained_decode(offsets, probs),
        }
        expected_spans = {}
        for name, expected in (("ITEM", item), ("TGT", target)):
            expected_spans[name] = (
                (text.index(expected), text.index(expected) + len(expected)) if expected else None
            )
        row = {"text": text}
        for mode in modes:
            pred_item, pred_target, assigned = decodes[mode]
            hits = {}
            for name, expected, predicted in (
                ("ITEM", expected_spans["ITEM"], pred_item),
                ("TGT", expected_spans["TGT"], pred_target),
            ):
                strict[mode][name][1] += 1
                loose[mode][name][1] += 1
                if predicted is None and expected is None:
                    strict[mode][name][0] += 1
                    loose[mode][name][0] += 1
                    hit = True
                elif predicted is not None and expected is not None:
                    hit = predicted == expected
                    strict[mode][name][0] += int(hit)
                    if predicted[0] < expected[1] and expected[0] < predicted[1]:
                        loose[mode][name][0] += 1
                else:
                    hit = False
                hits[name] = hit
            both[mode][1] += 1
            both[mode][0] += int(hits["ITEM"] and hits["TGT"])
            sub = {
                "predItem": text[pred_item[0]: pred_item[1]] if pred_item else None,
                "predTarget": text[pred_target[0]: pred_target[1]] if pred_target else None,
                "itemStrict": hits["ITEM"],
                "targetStrict": hits["TGT"],
            }
            if detail is not None:
                diag = diagnose(text, item, target, offsets, assigned, probs)
                sub["diagnosis"] = {"item": diag["item"], "target": diag["target"]}
                if detail == "tokens" and mode == "greedy":
                    row["tokens"] = diag["tokens"]
            row[mode] = sub
        rows.append(row)
    return strict, loose, both, rows


def print_diagnostics(name, rows):
    """把逐字诊断打印成可读记录：错位 token + 两种解码的多标签归类。"""
    print(f"  [{name}] per-token diagnostics (gold != pred only, greedy):")
    for row in rows:
        mismatches = [
            f"{t['ch']}:{t['gold']}>{t['pred']}(p={t['pPred']:.2f})"
            for t in row.get("tokens", [])
            if t["gold"] != t["pred"]
        ]
        g, c = row["greedy"], row["constrained"]

        def fmt(sub):
            return (
                f"{sub['predItem']}/{sub['predTarget']} "
                f"[{'+'.join(sub['diagnosis']['item'])} | {'+'.join(sub['diagnosis']['target'])}]"
            )

        print(f"    {row['text']}\n      greedy      = {fmt(g)}\n      constrained = {fmt(c)}")
        if mismatches:
            print(f"      {'  '.join(mismatches)}")


def make_forward_torch(model, tokenizer):
    def forward(text):
        encoded = tokenizer(text, truncation=True, max_length=MAX_LEN, return_offsets_mapping=True)
        offsets = encoded["offset_mapping"]
        with torch.no_grad():
            logits = model(
                input_ids=torch.tensor([encoded["input_ids"]]),
                attention_mask=torch.tensor([encoded["attention_mask"]]),
                token_type_ids=torch.tensor([encoded["token_type_ids"]]),
            ).logits[0]
        probs = torch.softmax(logits, dim=-1)[: len(offsets)].tolist()
        tag_ids = logits.argmax(-1).tolist()[: len(offsets)]
        return offsets, tag_ids, probs

    return forward


def make_forward_onnx(session, tokenizer):
    import numpy as np

    def forward(text):
        encoded = tokenizer(text, truncation=True, max_length=MAX_LEN, return_offsets_mapping=True)
        offsets = encoded["offset_mapping"]
        seq = len(encoded["input_ids"])
        feed = {
            "input_ids": np.array([encoded["input_ids"]], dtype=np.int64),
            "attention_mask": np.ones((1, seq), dtype=np.int64),
            "token_type_ids": np.zeros((1, seq), dtype=np.int64),
        }
        logits = session.run(None, feed)[0][0]  # [seq, tags]
        shifted = logits - logits.max(axis=-1, keepdims=True)
        exp = np.exp(shifted)
        probs = (exp / exp.sum(axis=-1, keepdims=True))[: len(offsets)].tolist()
        tag_ids = logits.argmax(axis=-1).tolist()[: len(offsets)]
        return offsets, tag_ids, probs

    return forward


def main():
    args = sys.argv[1:]
    export_only = "--export-corpus" in args
    eval_onnx = "--eval-onnx" in args
    positional = [a for a in args if not a.startswith("--")]
    if not export_only and not eval_onnx and not positional:
        sys.exit("usage: train-span-labeler.py <snapshot-dir> [--export-corpus] | --eval-onnx")
    frontend_root = pathlib.Path(__file__).resolve().parent.parent
    out_dir = frontend_root / "public" / "models" / "minirbt-h256-span"
    artifacts_dir = frontend_root.parent / "artifacts" / "benchmark"
    (out_dir / "onnx").mkdir(parents=True, exist_ok=True)

    rng = random.Random(SEED)
    template_corpus = build_template_corpus()
    handwritten = rows_of(TRAIN_GROUPS)
    corpus = [(text, locate(text, i) if i else None, locate(text, t) if t else None)
              for _, text, i, t in handwritten]
    corpus += template_corpus
    counts = {}
    for text, item, target in corpus:
        key = f"item={item is not None},target={target is not None}"
        counts[key] = counts.get(key, 0) + 1
    print(f"pool: {len(corpus)} sentences (templates {len(template_corpus)} + hand-written {len(corpus) - len(template_corpus)}) {counts}")

    # 划分先于写盘：manifest 里的 train/validation 就是实际训练/留出集。
    rng.shuffle(corpus)
    val_n = max(1, len(corpus) // 10)
    val_sentences, train_sentences = corpus[:val_n], corpus[val_n:]
    print(f"split: train={len(train_sentences)} validation={len(val_sentences)}")

    check_discipline(template_corpus)

    def as_rows(rows):
        return [
            {
                "text": text,
                "item": text[item[0]: item[1]] if item else None,
                "target": text[target[0]: target[1]] if target else None,
            }
            for text, item, target in rows
        ]

    sealed_rows = sum(len(rows) for rows in ACCEPTANCE_SEALED.values())
    manifest = {
        "seed": SEED,
        "labelingRules": [
            "span = contiguous char range of original text [start,end)",
            "item_use: used object=ITEM, acted-on=TGT",
            "inspect: inspected object=TGT (no ITEM); 检查X的Y -> X=TGT, Y=O",
            "move/npc_talk: location/person=TGT",
            "titles stay in person spans; stripping is code-side",
            "rule 6 (v2): spans are the HEAD NOUN; 的-phrases and 那/半截-style "
            "prefixes are O — 生锈的铁门钥匙->铁门钥匙, 后院的门->门 (possessor is "
            "a modifier); compounds without 的 are whole nouns (旧锁); "
            "training and span scoring both follow it",
            "at most one span per field",
            "rule 8: mentioned-but-not-used objects are O (tag follows the verb phrase, not the noun)",
            "rule 9 (authoring): no body-part instruments, no 借/买 frames, "
            "no two-way-defensible gold spans",
        ],
        "acceptanceProtocol": {
            "preRegistered": "sealed acceptance batch (100 hand-written sentences, fresh slots): "
                             "strict span match >= 90% per field",
            "component": "both fields pass AND end-to-end <= 4s per call",
            "alsoReported": "both-fields-correct rate (non-gating)",
            "protocol": "dev batches (classic 10 + grouped) are diagnostics only; the sealed batch "
                        "is evaluated exactly once via run-labeler-trial.mjs --with-acceptance after "
                        "dev results justify it; v1 (ec4aa02) and v2 (b5067d7) were each evaluated "
                        "once and retired",
        },
        "attributionNote": "铁门钥匙 case: the pre-coverage model output 生锈, the post-coverage model "
                           "outputs 铁门钥匙 — model and scoring rule (rule 6 v2) changed together in "
                           "ec4aa02/b5067d7, so the flip is joint attribution, not 'the rule fixed it'. "
                           "Historical reports keep their original scores.",
        "counts": {
            "templates": len(template_corpus),
            "handwrittenTrain": len(handwritten),
            "train": len(train_sentences),
            "validation": len(val_sentences),
            "distribution": counts,
            "devClassic": len(DEV_CLASSIC),
            "devGroups": {name: len(rows) for name, rows in DEV_GROUPS.items()},
            "scored": len(SCORED),
            "acceptanceSealed": {name: len(rows) for name, rows in ACCEPTANCE_SEALED.items()},
            "acceptanceRetiredV2": len(ACCEPTANCE_RETIRED_V2),
        },
        "devClassic": [{"text": text, "item": item, "target": target} for text, item, target in DEV_CLASSIC],
        "devGroups": [
            {"group": name, "sentences": [{"text": t, "item": i, "target": g} for t, i, g in rows]}
            for name, rows in DEV_GROUPS.items()
        ],
        "scored": [{"text": text, "item": item, "target": target} for text, item, target in SCORED],
        "trainHandwrittenGroups": [
            {"group": name, "sentences": [{"text": t, "item": i, "target": g} for t, i, g in rows]}
            for name, rows in TRAIN_GROUPS.items()
        ],
        "train": as_rows(train_sentences),
        "validation": as_rows(val_sentences),
        "acceptance": [
            {"group": name, "sentences": [{"text": t, "item": i, "target": g} for t, i, g in rows]}
            for name, rows in ACCEPTANCE_SEALED.items()
        ],
        "acceptanceRetired": {
            "v2": {
                "evaluatedAt": "trial 1791490412586 (commits b5067d7/82d8d41); strict ITEM 6/10, "
                               "TGT 7/10, loose TGT 8/10, both-fields 6/10 -> rejected; retired",
                "sentences": [{"text": text, "item": item, "target": target}
                              for text, item, target in ACCEPTANCE_RETIRED_V2],
            },
            "v1": "evaluated once at ec4aa02-era trial; retired (see 82d8d41 for the v1/v2 mixup)",
        },
        "errorTaxonomy": {
            "multiLabel": True,
            "note": "diagnosis per field is a LIST of defect classes in the order below; a gold span "
                    "can carry several at once (e.g. truncated-o AND truncated-b in 地下藏书室) — "
                    "single-primary-class reporting mispointed the cut location. Positions live in "
                    "the per-token records. No defects -> [\"ok\"].",
            "ok": "no defects (both empty, or exact span match)",
            "span-false": "gold empty, model emitted a span",
            "span-missing": "gold present, no span decoded for this field",
            "all-o": "every gold character predicted O (cause of span-missing)",
            "truncated-o": "O predicted inside the entity; the decoded span was cut there",
            "truncated-b": "another B- fires inside the entity (first group wins, also cuts)",
            "wrong-field": "gold characters or the predicted span land on the OTHER field",
            "over-extended": "prediction covers gold entirely but over-extends",
            "boundary-mismatch": "prediction overlaps gold but neither contains the other",
            "modifier-as-head": "prediction sits entirely in the pre-head modifier/possessor zone (的-separated)",
            "displaced": "prediction disjoint from gold, not in the modifier zone, not on the other field's gold",
        },
        "batchSemantics": {
            "devGroups": "whole GROUPS held out of training; entities/scenarios are disjoint, but "
                         "sentence patterns recur across splits by design (e.g. 擦亮了灶王爷的牌位 "
                         "train vs 擦亮了掌柜的烟杆 dev) — evidence supports new-entity/new-scenario "
                         "evaluation only, NOT unseen-pattern claims",
            "acceptance": "sealed; evaluated exactly once via run-labeler-trial.mjs --with-acceptance",
        },
        "note": "single data contract: run-labeler-trial.mjs loads THIS file (sha256 recorded in its "
                "report); this script reads the file back for its own evaluation. train/validation are "
                "the actual split; devClassic/devGroups/scored/acceptance are excluded from training.",
    }
    manifest_path = artifacts_dir / "span-labeler-corpus.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"corpus manifest saved: {manifest_path}")
    if export_only:
        return

    # 读回同一份数据文件做评估——Python 与浏览器逐字节同源。
    disk = json.loads(manifest_path.read_text(encoding="utf-8"))
    dev_group_cases = [
        {**row, "group": grp["group"]} for grp in disk["devGroups"] for row in grp["sentences"]
    ]
    # disk["acceptance"] 是封存批：评一次的协议归浏览器 trial --with-acceptance，
    # 训练侧刻意不加载、不评估。
    eval_batches = (
        ("devClassic", disk["devClassic"], "tokens"),
        ("devGroups", dev_group_cases, "tokens"),
        ("scored", disk["scored"], "diagnosis"),
    )

    def run_eval(title, forward):
        print(f"== {title} ==")
        for name, cases, detail in eval_batches:
            strict, loose, both, rows = evaluate(forward, cases, detail=detail)
            for mode in ("greedy", "constrained"):
                for field in ("ITEM", "TGT"):
                    s, l = strict[mode][field], loose[mode][field]
                    print(f"{name} {mode} {field}: strict={s[0]}/{s[1]} loose={l[0]}/{l[1]}")
                print(f"{name} {mode} both-fields strict: {both[mode][0]}/{both[mode][1]}")
            if detail == "tokens":
                print_diagnostics(name, rows)
            else:
                for row in rows:
                    g = row["greedy"]
                    print(f"  [{name}] {row['text']} item={g['predItem']} target={g['predTarget']}")

    if eval_onnx:
        # 冻结权重评估：直接打分已导出的 ONNX 工件（与浏览器同字节），
        # 不重训——用于解码方式对照轮。
        import onnxruntime as ort

        tokenizer = BertTokenizerFast.from_pretrained(out_dir)
        for tag, fname in (("q8", "onnx/model_quantized.onnx"), ("fp32", "onnx/model.onnx")):
            session = ort.InferenceSession(str(out_dir / fname))
            run_eval(f"onnx {tag} (frozen artifacts)", make_forward_onnx(session, tokenizer))
        return

    snapshot = positional[0]
    torch.manual_seed(SEED)

    tokenizer = BertTokenizerFast.from_pretrained(snapshot)
    model = BertForTokenClassification.from_pretrained(
        snapshot,
        num_labels=len(TAGS),
        id2label={i: tag for i, tag in enumerate(TAGS)},
        label2id={tag: i for i, tag in enumerate(TAGS)},
    )
    model.config._attn_implementation = "eager"  # 稳定 ONNX 导出

    features = []
    for text, item, target in train_sentences:
        input_ids, labels = spans_to_tags(text, item, target, tokenizer)
        features.append((text, input_ids, labels))

    def pad_batch(batch):
        length = min(MAX_LEN, max(len(ids) for _, ids, _ in batch))
        input_ids, attention, token_types, label_ids = [], [], [], []
        for _, ids, labels in batch:
            pad = length - len(ids)
            input_ids.append(ids + [0] * pad)
            attention.append([1] * len(ids) + [0] * pad)
            token_types.append([0] * length)
            label_ids.append(labels + [-100] * pad)
        return (
            torch.tensor(input_ids),
            torch.tensor(attention),
            torch.tensor(token_types),
            torch.tensor(label_ids),
        )

    val_features = []
    for text, item, target in val_sentences:
        input_ids, labels = spans_to_tags(text, item, target, tokenizer)
        val_features.append((text, input_ids, labels))
    ce = torch.nn.CrossEntropyLoss(ignore_index=-100)

    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)
    model.train()
    for epoch in range(1, EPOCHS + 1):
        rng.shuffle(features)
        total = 0.0
        for start in range(0, len(features), BATCH):
            batch = features[start: start + BATCH]
            input_ids, attention, token_types, label_ids = pad_batch(batch)
            logits = model(input_ids=input_ids, attention_mask=attention, token_type_ids=token_types).logits
            loss = ce(logits.reshape(-1, len(TAGS)), label_ids.reshape(-1))
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total += loss.item() * len(batch)
        val_total = 0.0
        # 验证前必须切 eval()（关 Dropout）：上一轮的 val_loss 在 train() 态
        # 下测得，混入随机丢弃，那批数字作废——本轮权重冻结不重训，下次
        # 训练起生效。测完切回 train()。
        model.eval()
        for start in range(0, len(val_features), BATCH):
            batch = val_features[start: start + BATCH]
            input_ids, attention, token_types, label_ids = pad_batch(batch)
            with torch.no_grad():
                logits = model(input_ids=input_ids, attention_mask=attention, token_type_ids=token_types).logits
                val_total += ce(logits.reshape(-1, len(TAGS)), label_ids.reshape(-1)).item() * len(batch)
        model.train()
        print(f"epoch {epoch}: loss={total / len(features):.4f} val_loss={val_total / len(val_features):.4f}")

    run_eval("torch (freshly trained)", make_forward_torch(model, tokenizer))

    dummy = tokenizer("我用铜钥匙打开大门。", truncation=True, max_length=MAX_LEN, return_offsets_mapping=True)
    seq = len(dummy["input_ids"])
    torch.onnx.export(
        model,
        (
            torch.tensor([dummy["input_ids"]]),
            torch.tensor([dummy["attention_mask"]]),
            torch.tensor([dummy["token_type_ids"]]),
        ),
        str(out_dir / "onnx" / "model.onnx"),
        input_names=["input_ids", "attention_mask", "token_type_ids"],
        output_names=["logits"],
        dynamic_axes={
            "input_ids": {0: "batch", 1: "seq"},
            "attention_mask": {0: "batch", 1: "seq"},
            "token_type_ids": {0: "batch", 1: "seq"},
            "logits": {0: "batch", 1: "seq"},
        },
        opset_version=14,
    )
    from onnxruntime.quantization import QuantType, quantize_dynamic

    quantize_dynamic(
        str(out_dir / "onnx" / "model.onnx"),
        str(out_dir / "onnx" / "model_quantized.onnx"),
        weight_type=QuantType.QUInt8,
    )
    tokenizer.save_pretrained(out_dir)
    model.config.save_pretrained(out_dir)
    sizes = {
        p.name: p.stat().st_size
        for p in sorted(out_dir.rglob("*"))
        if p.is_file() and p.suffix in {".onnx", ".json", ".txt"}
    }
    print("exported:", json.dumps(sizes, indent=2))


if __name__ == "__main__":
    main()
