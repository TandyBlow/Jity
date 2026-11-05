"""Build the target-expression paired material (v1), no training.

124 pairs / 248 examples: 4 categories x (20 train + 5 dev + 6 confirm).
Each pair has one positive and one negative; authorization or statement differs.
Source/template families are split as whole units.
"""
from __future__ import annotations
import hashlib, json, pathlib, re, sys
from collections import Counter, defaultdict

ROOT = pathlib.Path('D:/others/Jity')
ART = ROOT / 'artifacts' / 'statement-verification'
OUT = ART / 'pairs-target-v1.jsonl'
REG = ART / 'regression-v1.jsonl'
OLD = ART / 'pairs-v1.jsonl'
CAP = ART / 'general-capability-v1.jsonl'
AUDIT = ART / 'audit-target-v1.json'
FREEZE = ART / 'split-freeze-target-v1.json'

TRAIN = ['authorization', 'statement', 'authorization', 'statement']
DEV2 = ['authorization', 'statement']
DEV3 = ['authorization', 'statement', 'authorization']
CONF_A = ['authorization', 'statement', 'authorization']
CONF_B = ['statement', 'authorization', 'statement']


def F(sid, text, kind):
    return {'sourceId': sid, 'factText': text, 'kind': kind}


def S(sid, text):
    return {'sourceId': sid, 'text': text}


def V(sid, text):
    return {'sourceId': sid, 'text': text}


def frame_prefix(bg, s, a, obj):
    return f'{bg}，{s}{a}。'


def frame_suffix(bg, s, a, obj):
    return f'{s}{a}，{bg}。'


def frame_mid(bg, s, a, obj):
    return f'{s}在{bg}{a}。'


def frame_through(bg, s, a, obj):
    return f'隔着{bg}，{s}{a}。'


def frame_notcleared(bg, s, a, obj):
    return f'{bg}还没散，{s}{a}。'


def frame_light(bg, s, a, obj):
    return f'{bg}落在{obj}上，{s}{a}。'


def frame_stop(bg, s, a, obj):
    return f'{s}在{bg}停了停，{a}。'


def frame_drift(bg, s, a, obj):
    return f'{bg}从{obj}那边漫过来，{s}{a}。'


def frame_strong(bg, s, a, obj):
    return f'{s}{a}时，{bg}正浓。'


def vis_prefix(obj, state, s, a, obj2=''):
    return f'{obj}{state}，{s}{a}。'


def vis_suffix(obj, state, s, a, obj2=''):
    return f'{s}{a}，{obj}{state}。'


def vis_when(obj, state, s, a, obj2=''):
    return f'{s}{a}时，{obj}{state}。'


def vis_semicolon(obj, state, s, a, obj2=''):
    return f'{obj}{state}；{s}{a}。'


def vis_see(obj, state, s, a, obj2=''):
    return f'{s}看见{obj}{state}，{a}。'


def vis_onlythen(obj, state, s, a, obj2=''):
    return f'{obj}{state}，{s}才{a}。'


def vis_zhe(obj, state, s, a, obj2=''):
    return f'{obj}{state}着，{s}{a}。'


def vis_wait(obj, state, s, a, obj2=''):
    return f'等{obj}{state}，{s}{a}。'


def vis_at(obj, state, s, a, obj2=''):
    return f'{s}在{obj}{state}时，{a}。'


# ---------------- body: 31 pairs ----------------
# row = (subject, positive body phrase, negative body phrase, action fact,
#        movement-only fact, visible object)
BODY = [
    ('body', 'train-01', 'body-limb', 'train', [
        ('阿棠', '指节被麻绳勒得发白', '掌心被木柄磨得发热', '把麻绳收紧', '从灶房来到渡口', '麻绳'),
        ('闻溪', '手腕被缆绳勒出红痕', '手背被灯油烫起小泡', '把缆绳拖回', '从渡口来到盐仓', '缆绳'),
        ('陆禾', '小臂被竹篾划出血线', '指节被石阶磕得发青', '把竹篾捆好', '从盐仓来到石桥', '竹篾'),
        ('贺川', '膝盖被木箱撞得发麻', '额角被门框磕得发红', '把木箱推开', '从石桥来到柴房', '木箱'),
    ], TRAIN),
    ('body', 'train-02', 'body-stain', 'train', [
        ('阿棠', '袖口湿透', '衣摆沾了泥', '把纸伞扶正', '从渡口来到茶棚', '纸伞'),
        ('闻溪', '衣襟沾了盐霜', '袖口染了灯油', '把盐包码好', '从盐仓来到渡口', '盐包'),
        ('陆禾', '鞋面沾了泥水', '裤脚湿透', '把鱼筐搬起', '从石桥来到河埠', '鱼筐'),
        ('贺川', '手背溅了热油', '袖口沾了煤灰', '把炉火拨旺', '从柴房来到灶间', '炉火'),
    ], TRAIN),
    ('body', 'train-03', 'body-mark', 'train', [
        ('阿棠', '肩头落着灰', '发间沾着草屑', '把纸灯挂好', '从茶棚来到回廊', '纸灯'),
        ('闻溪', '额角渗出细汗', '鬓边沾着雨珠', '把窗纸糊好', '从渡口来到厢房', '窗纸'),
        ('陆禾', '手背蹭破皮', '膝头沾了土', '把木箱扶正', '从河埠来到货栈', '木箱'),
        ('贺川', '下颌沾着油光', '指缝塞着泥', '把鱼筐推开', '从灶间来到后院', '鱼筐'),
    ], TRAIN),
    ('body', 'train-04', 'body-trace', 'train', [
        ('阿棠', '手背上沾着灯油', '指甲缝里嵌着泥', '把灯罩擦亮', '从回廊来到灯房', '灯罩'),
        ('闻溪', '袖口上挂着线头', '衣角上沾着草籽', '把布匹叠好', '从厢房来到布庄', '布匹'),
        ('陆禾', '鞋底上粘着泥块', '裤腿上沾着盐粒', '把货箱搬起', '从货栈来到码头', '货箱'),
        ('贺川', '肩膀上落着木屑', '头发里夹着草叶', '把木料码好', '从后院来到工棚', '木料'),
    ], TRAIN),
    ('body', 'train-05', 'body-bandage', 'train', [
        ('阿棠', '手腕上缠着布条', '指头上裹着纱布', '把药箱合上', '从灯房来到药铺', '药箱'),
        ('闻溪', '额角贴着膏药', '手背上包着布巾', '把药碗端稳', '从布庄来到医馆', '药碗'),
        ('陆禾', '膝盖上绑着护布', '脚踝上缠着麻布', '把拐杖靠好', '从码头来到客栈', '拐杖'),
        ('贺川', '肩头敷着湿布', '掌心缠着细绳', '把冰袋放好', '从工棚来到前堂', '冰袋'),
    ], TRAIN),
    ('body', 'dev-01', 'body-bruise', 'dev', [
        ('许砚', '额角起了青包', '脸颊蹭破了皮', '把门帘掀开', '从客栈来到院中', '门帘'),
        ('叶澄', '手腕上青了一块', '指节肿了起来', '把茶壶放下', '从院中来到茶室', '茶壶'),
    ], DEV2),
    ('body', 'dev-02', 'body-cloth', 'dev', [
        ('陆禾', '衣摆湿了', '领口沾了雨', '把蓑衣挂好', '从茶室来到檐下', '蓑衣'),
        ('贺川', '裤脚沾了泥', '袖口湿了', '把木桶提稳', '从檐下来到井边', '木桶'),
        ('阿棠', '鞋面沾了灰', '衣襟沾了油', '把鞋刷放下', '从井边来到廊下', '鞋刷'),
    ], DEV3),
    ('body', 'confirm-01', 'body-mud', 'confirm', [
        ('闻溪', '鞋面沾了泥', '裙摆沾了水', '把伞收好', '从廊下来到门口', '伞'),
        ('陆禾', '手背沾了灰', '指甲沾了墨', '把账本合上', '从门口来到柜台', '账本'),
        ('贺川', '袖口沾了酱', '指节沾了油', '把碗放稳', '从柜台来到灶边', '碗'),
    ], CONF_A),
    ('body', 'confirm-02', 'body-scratch', 'confirm', [
        ('阿棠', '手背被竹篾划出血痕', '指节被纸边割开小口', '把竹篾捆好', '从灶边来到院中', '竹篾'),
        ('闻溪', '手腕被麻绳磨破皮', '掌心被木刺扎出血点', '把麻绳盘好', '从院中来到廊下', '麻绳'),
        ('陆禾', '小腿被石角刮出红印', '脚背被木箱蹭破皮', '把石角垫好', '从廊下来到门口', '石角'),
    ], CONF_B),
]


# ---------------- background: 31 pairs ----------------
# row = (subject, action fact, positive bg, negative bg, base scene,
#        positive scene noun, negative scene noun, visible object)
BG = [
    ('background', 'train-01', 'bg-prefix', 'train', frame_prefix, [
        ('阿棠', '把缆绳拖回', '河雾里', '细雨里', '夜', '河雾', '细雨', '缆绳'),
        ('闻溪', '把纸伞扶正', '雨声里', '风声里', '清晨', '雨声', '风声', '纸伞'),
        ('陆禾', '把鱼筐搬起', '夜雾里', '雨里', '夜', '夜雾', '雨', '鱼筐'),
        ('贺川', '把灯罩系紧', '潮气里', '尘气里', '傍晚', '潮气', '尘气', '灯罩'),
    ], TRAIN),
    ('background', 'train-02', 'bg-suffix', 'train', frame_suffix, [
        ('阿棠', '把门闩落下', '风里', '雨里', '夜', '风', '雨', '门闩'),
        ('闻溪', '把窗纸糊好', '灯影里', '日影里', '傍晚', '灯影', '日影', '窗纸'),
        ('陆禾', '把炉火拨旺', '雪光里', '月光里', '夜', '雪光', '月光', '炉火'),
        ('贺川', '把茶盏端稳', '雾气里', '烟气里', '清晨', '雾气', '烟气', '茶盏'),
    ], TRAIN),
    ('background', 'train-03', 'bg-mid', 'train', frame_mid, [
        ('阿棠', '把纸伞扶正', '雨声里', '风声里', '清晨', '雨声', '风声', '纸伞'),
        ('闻溪', '把鱼筐推开', '热浪里', '寒风里', '午后', '热浪', '寒风', '鱼筐'),
        ('陆禾', '把木箱搬起', '水汽里', '尘土里', '清晨', '水汽', '尘土', '木箱'),
        ('贺川', '把缆绳收紧', '夜雾里', '晴空里', '夜', '夜雾', '晴空', '缆绳'),
    ], TRAIN),
    ('background', 'train-04', 'bg-through', 'train', frame_through, [
        ('阿棠', '把灯罩擦亮', '晨雾', '夜雾', '清晨', '晨雾', '夜雾', '灯罩'),
        ('闻溪', '把药碗端稳', '水汽', '油烟', '午后', '水汽', '油烟', '药碗'),
        ('陆禾', '把窗纸补好', '细雨', '大雪', '夜', '细雨', '大雪', '窗纸'),
        ('贺川', '把鱼筐拖回', '咸雾', '沙尘', '清晨', '咸雾', '沙尘', '鱼筐'),
    ], TRAIN),
    ('background', 'train-05', 'bg-notcleared', 'train', frame_notcleared, [
        ('阿棠', '把门闩落下', '薄雾', '夜雾', '清晨', '薄雾', '夜雾', '门闩'),
        ('闻溪', '把茶盏端稳', '朝雾', '雨雾', '清晨', '朝雾', '雨雾', '茶盏'),
        ('陆禾', '把麻绳盘好', '夜气', '烟尘', '夜', '夜气', '烟尘', '麻绳'),
        ('贺川', '把纸伞收好', '湿气', '霜气', '午后', '湿气', '霜气', '纸伞'),
    ], TRAIN),
    ('background', 'dev-01', 'bg-light', 'dev', frame_light, [
        ('阿棠', '把灯罩擦亮', '雪光', '日光', '夜', '雪光', '日光', '灯罩'),
        ('闻溪', '把茶盏端稳', '月光', '灯光', '夜', '月光', '灯光', '茶盏'),
    ], DEV2),
    ('background', 'dev-02', 'bg-stop', 'dev', frame_stop, [
        ('陆禾', '把鱼筐扶正', '暑气里', '寒风里', '午后', '暑气', '寒风', '鱼筐'),
        ('贺川', '把纸伞收好', '檐雨里', '檐风里', '清晨', '檐雨', '檐风', '纸伞'),
        ('许砚', '把门闩落下', '湿雾里', '晴空里', '夜', '湿雾', '晴空', '门闩'),
    ], DEV3),
    ('background', 'confirm-01', 'bg-drift', 'confirm', frame_drift, [
        ('阿棠', '把窗纸补好', '潮雾', '尘土', '清晨', '潮雾', '尘土', '窗纸'),
        ('闻溪', '把灯罩擦亮', '河雾', '烟气', '夜', '河雾', '烟气', '灯罩'),
        ('陆禾', '把茶盏端稳', '海雾', '沙尘', '午后', '海雾', '沙尘', '茶盏'),
    ], CONF_A),
    ('background', 'confirm-02', 'bg-strong', 'confirm', frame_strong, [
        ('贺川', '把门闩落下', '夜色', '尘雾', '夜', '夜色', '尘雾', '门闩'),
        ('许砚', '把鱼筐搬起', '雾气', '尘气', '清晨', '雾气', '尘气', '鱼筐'),
        ('叶澄', '把纸伞收好', '雨气', '雪气', '午后', '雨气', '雪气'
, '纸伞'),
    ], CONF_B),
]


# ---------------- visible-state: 31 pairs ----------------
# row = (subject, action fact, object, positive state, negative state, base scene)
VIS = [
    ('visible-state', 'train-01', 'vis-prefix', 'train', vis_prefix, [
        ('阿棠', '把灯罩擦亮', '纸灯', '已点亮', '熄了', '夜'),
        ('闻溪', '把窗纸补好', '风灯', '亮着', '灭了', '清晨'),
        ('陆禾', '把木箱搬起', '门闩', '关着', '开着', '夜'),
        ('贺川', '把鱼筐推开', '石阶', '湿着', '干了', '清晨'),
    ], TRAIN),
    ('visible-state', 'train-02', 'vis-suffix', 'train', vis_suffix, [
        ('阿棠', '把水壶提稳', '炉火', '亮着', '灭了', '夜'),
        ('闻溪', '把茶盏端稳', '窗纸', '关着', '开着', '午后'),
        ('陆禾', '把水桶放下', '水缸', '满着', '空了', '清晨'),
        ('贺川', '把木箱扶正', '木箱', '锁着', '开着', '夜'),
    ], TRAIN),
    ('visible-state', 'train-03', 'vis-when', 'train', vis_when, [
        ('阿棠', '把门闩落下', '铜铃', '响着', '静了', '夜'),
        ('闻溪', '把纸伞收好', '灯笼', '亮着', '灭了', '傍晚'),
        ('陆禾', '把鱼筐搬起', '门环', '挂着', '落了', '清晨'),
        ('贺川', '把缆绳收紧', '旗子', '湿着', '干了', '午后'),
    ], TRAIN),
    ('visible-state', 'train-04', 'vis-semicolon', 'train', vis_semicolon, [
        ('阿棠', '把灯罩擦亮', '纸灯', '已点亮', '熄了', '夜'),
        ('闻溪', '把窗纸补好', '窗纸', '破着', '补好', '清晨'),
        ('陆禾', '把木箱搬起', '石阶', '湿着', '干了', '夜'),
        ('贺川', '把水桶放下', '水缸', '空着', '满着', '午后'),
    ], TRAIN),
    ('visible-state', 'train-05', 'vis-see', 'train', vis_see, [
        ('阿棠', '把水壶提稳', '炉火', '亮着', '灭了', '夜'),
        ('闻溪', '把门闩落下', '纸灯', '已点亮', '熄了', '清晨'),
        ('陆禾', '把鱼筐搬起', '门闩', '落着', '开着', '夜'),
        ('贺川', '把茶盏端稳', '水缸', '满着', '空了', '午后'),
    ], TRAIN),
    ('visible-state', 'dev-01', 'vis-onlythen', 'dev', vis_onlythen, [
        ('许砚', '把灯罩擦亮', '门环', '落着', '开着', '夜'),
        ('叶澄', '把纸伞收好', '铜铃', '震着', '静了', '清晨'),
    ], DEV2),
    ('visible-state', 'dev-02', 'vis-zhe', 'dev', vis_zhe, [
        ('阿棠', '把门闩落下', '纸灯', '亮', '灭', '夜'),
        ('闻溪', '把水壶提稳', '炉火', '熄', '旺', '清晨'),
        ('陆禾', '把木箱搬起', '石阶', '湿', '裂', '午后'),
    ], DEV3),
    ('visible-state', 'confirm-01', 'vis-wait', 'confirm', vis_wait, [
        ('贺川', '把灯罩擦亮', '门闩', '落', '开', '夜'),
        ('许砚', '把鱼筐搬起', '灯笼', '亮', '灭', '清晨'),
        ('叶澄', '把水桶放下', '水缸', '满', '空', '午后'),
    ], CONF_A),
    ('visible-state', 'confirm-02', 'vis-at', 'confirm', vis_at, [
        ('阿棠', '把茶盏端稳', '铜铃', '响', '静', '夜'),
        ('闻溪', '把门闩落下', '炉火', '燃', '灭', '清晨'),
        ('陆禾', '把窗纸补好', '窗纸', '破', '糊好', '午后'),
    ], CONF_B),
]


# ---------------- extra-action: 31 pairs ----------------
# row = (subject, positive action, negative action, object, place, negative kind)
EX = [
    ('extra-action', 'train-01', 'ex-e1', 'train', [
        ('阿棠', '把鱼筐推开', '把鱼筐扶正', '鱼筐', '灶边', 'action'),
        ('闻溪', '把灯罩系紧', '把灯罩擦亮', '灯罩', '灯下', 'object'),
        ('陆禾', '把麻绳拖回', '把麻绳挂好', '麻绳', '檐下', 'action'),
        ('贺川', '把木箱搬起', '把木箱放下', '木箱', '门口', 'object'),
    ], TRAIN),
    ('extra-action', 'train-02', 'ex-e2', 'train', [
        ('阿棠', '将纸伞收起', '将纸伞挂好', '纸伞', '门后', 'action'),
        ('闻溪', '将窗纸补好', '将窗纸推开', '窗纸', '窗边', 'object'),
        ('陆禾', '将茶盏端稳', '将茶盏放下', '茶盏', '桌上', 'action'),
        ('贺川', '将炉火拨旺', '将炉火压住', '炉火', '灶里', 'object'),
    ], TRAIN),
    ('extra-action', 'train-03', 'ex-e3', 'train', [
        ('阿棠', '拖回了缆绳', '挂好了缆绳', '缆绳', '岸边', 'action'),
        ('闻溪', '搬起了鱼筐', '扶正了鱼筐', '鱼筐', '船头', 'object'),
        ('陆禾', '擦亮了铜灯', '熄灭了铜灯', '铜灯', '桌上', 'action'),
        ('贺川', '补好了窗纸', '推开了窗纸', '窗纸', '窗边', 'object'),
    ], TRAIN),
    ('extra-action', 'train-04', 'ex-e4', 'train', [
        ('阿棠', '把木箱搬到檐下', '把木箱推到门边', '木箱', '檐下', 'action'),
        ('闻溪', '把鱼筐提到灶边', '把鱼筐放回船头', '鱼筐', '灶边', 'object'),
        ('陆禾', '把灯罩挂到墙边', '把灯罩放回桌上', '灯罩', '墙边', 'action'),
        ('贺川', '把麻绳盘到桩上', '把麻绳丢在岸边', '麻绳', '桩上', 'object'),
    ], TRAIN),
    ('extra-action', 'train-05', 'ex-e5', 'train', [
        ('阿棠', '用布擦亮铜灯', '用布盖住铜灯', '铜灯', '桌上', 'action'),
        ('闻溪', '用刀削好木签', '用刀折断木签', '木签', '案上', 'object'),
        ('陆禾', '用绳捆紧木箱', '用绳松开木箱', '木箱', '檐下', 'action'),
        ('贺川', '用纸补好窗洞', '用纸封住窗洞', '窗洞', '窗边', 'object'),
    ], TRAIN),
    ('extra-action', 'dev-01', 'ex-e6', 'dev', [
        ('许砚', '给门闩上油', '给门闩换轴', '门闩', '门上', 'action'),
        ('叶澄', '给铜灯添油', '给铜灯换芯', '铜灯', '桌上', 'object'),
    ], DEV2),
    ('extra-action', 'dev-02', 'ex-e7', 'dev', [
        ('阿棠', '把纸伞挂好', '把纸伞撑开', '纸伞', '门后', 'action'),
        ('闻溪', '把窗纸糊好', '把窗纸撕开', '窗纸', '窗边', 'object'),
        ('陆禾', '把鱼筐放好', '把鱼筐踢开', '鱼筐', '灶边', 'action'),
    ], DEV3),
    ('extra-action', 'confirm-01', 'ex-e8', 'confirm', [
        ('贺川', '从灶房搬出鱼筐', '从柴房搬出鱼筐', '鱼筐', '灶房', 'action'),
        ('许砚', '从窗边取下灯罩', '从墙边取下灯罩', '灯罩', '窗边', 'object'),
        ('叶澄', '从岸边拖回缆绳', '从船头拖回缆绳', '缆绳', '岸边', 'action'),
    ], CONF_A),
    ('extra-action', 'confirm-02', 'ex-e9', 'confirm', [
        ('阿棠', '把窗纸推开', '把窗纸糊上', '窗纸', '窗边', 'action'),
        ('闻溪', '把门闩拉开', '把门闩插上', '门闩', '门上', 'object'),
        ('陆禾', '把木箱打开', '把木箱锁上', '木箱', '檐下', 'action'),
    ], CONF_B),
]


def emit(family, idx, mode, pos, neg, template):
    cat, fid, tname, split = family[:4]
    pair_id = f'tgt:{cat}:{split}:{fid}:p{idx:02d}'
    source_id = f'tgt:{cat}:{split}:{fid}:s{idx:02d}'
    group = f'tgt:{cat}:{split}:{fid}'
    template_id = f'tgt:{cat}:{tname}'
    out = []
    for label, d in (('supported', pos), ('unsupported', neg)):
        out.append({
            'pairId': pair_id,
            'exampleId': pair_id + (':sup' if label == 'supported' else ':unsup'),
            'sourceId': source_id,
            'sourceGroupId': group,
            'templateId': template_id,
            'split': split,
            'origin': 'target-family',
            'category': cat,
            'pairMode': mode,
            'label': label,
            'fullText': d['fullText'],
            'candidateId': 'C1',
            'candidateText': d['candidateText'],
            'facts': d['facts'],
            'scene': d['scene'],
            'visible': d['visible'],
            'goldSourceIds': d['gold'],
            'sourceRole': d['role'],
            'notes': f'family={fid}; template={tname}; mode={mode}; negative={d["note"]}',
        })
    return out


def build_body():
    out = []
    for fam in BODY:
        cat, fid, tname, split, rows, modes = fam
        for i, (subj, pos_body, stmt_body, action, movement, obj) in enumerate(rows, 1):
            mode = modes[i - 1]
            pos_text = f'{subj}的{pos_body}。'
            stmt_text = f'{subj}的{stmt_body}。'
            facts_pos = [F('F1', pos_body, 'body'), F('F2', action, 'action')]
            facts_neg = [F('F1', movement, 'movement'), F('F2', action, 'action')]
            scene = [S('S1', '夜')]
            vis = [V('V1', obj)]
            pos = {'fullText': pos_text, 'candidateText': pos_body, 'facts': facts_pos,
                   'scene': scene, 'visible': vis, 'gold': ['F1'], 'role': 'support', 'note': 'direct-body'}
            if mode == 'authorization':
                neg = {'fullText': pos_text, 'candidateText': pos_body, 'facts': facts_neg,
                       'scene': scene, 'visible': vis, 'gold': ['F1'], 'role': 'checked', 'note': 'movement-only'}
            else:
                neg = {'fullText': stmt_text, 'candidateText': stmt_body, 'facts': facts_pos,
                       'scene': scene, 'visible': vis, 'gold': ['F1'], 'role': 'checked', 'note': 'alternative-body'}
            out += emit(fam, i, mode, pos, neg, tname)
    return out


def build_bg():
    out = []
    for fam in BG:
        cat, fid, tname, split, frame, rows, modes = fam
        for i, (subj, action, bg, bad_bg, base, scene_ok, scene_bad, obj) in enumerate(rows, 1):
            mode = modes[i - 1]
            pos_text = frame(bg, subj, action, obj)
            stmt_text = frame(bad_bg, subj, action, obj)
            facts = [F('F1', action, 'action')]
            scene_pos = [S('S1', base), S('S2', scene_ok)]
            scene_neg = [S('S1', base), S('S2', scene_bad)]
            vis = [V('V1', obj)]
            pos = {'fullText': pos_text, 'candidateText': bg, 'facts': facts,
                   'scene': scene_pos, 'visible': vis, 'gold': ['S2'], 'role': 'scene-support', 'note': 'scene-present'}
            if mode == 'authorization':
                neg = {'fullText': pos_text, 'candidateText': bg, 'facts': facts,
                       'scene': scene_neg, 'visible': vis, 'gold': ['S2'], 'role': 'scene-checked', 'note': 'other-weather'}
            else:
                neg = {'fullText': stmt_text, 'candidateText': bad_bg, 'facts': facts,
                       'scene': scene_pos, 'visible': vis, 'gold': ['S2'], 'role': 'scene-checked', 'note': 'alternative-background'}
            out += emit(fam, i, mode, pos, neg, tname)
    return out


def build_vis():
    out = []
    for fam in VIS:
        cat, fid, tname, split, frame, rows, modes = fam
        for i, (subj, action, obj, state_ok, state_bad, base) in enumerate(rows, 1):
            mode = modes[i - 1]
            cand_ok = f'{obj}{state_ok}'
            cand_bad = f'{obj}{state_bad}'
            pos_text = frame(obj, state_ok, subj, action)
            stmt_text = frame(obj, state_bad, subj, action)
            facts = [F('F1', action, 'action')]
            scene_pos = [S('S1', base), S('S2', cand_ok)]
            scene_neg = [S('S1', base), S('S2', obj)]
            vis = [V('V1', obj)]
            pos = {'fullText': pos_text, 'candidateText': cand_ok, 'facts': facts,
                   'scene': scene_pos, 'visible': vis, 'gold': ['S2'], 'role': 'scene-support', 'note': 'state-present'}
            if mode == 'authorization':
                neg = {'fullText': pos_text, 'candidateText': cand_ok, 'facts': facts,
                       'scene': scene_neg, 'visible': vis, 'gold': ['V1'], 'role': 'visible-checked', 'note': 'object-visible-state-absent'}
            else:
                neg = {'fullText': stmt_text, 'candidateText': cand_bad, 'facts': facts,
                       'scene': scene_pos, 'visible': vis, 'gold': ['S2'], 'role': 'scene-checked', 'note': 'alternative-state'}
            out += emit(fam, i, mode, pos, neg, tname)
    return out


def build_ex():
    out = []
    for fam in EX:
        cat, fid, tname, split, rows, modes = fam
        for i, (subj, action_ok, action_bad, obj, place, neg_kind) in enumerate(rows, 1):
            mode = modes[i - 1]
            pos_text = f'{subj}{action_ok}。'
            stmt_text = f'{subj}{action_bad}。'
            facts_pos = [F('F1', action_ok, 'action'), F('F2', f'{obj}在{place}', 'object')]
            if neg_kind == 'action':
                facts_neg = [F('F1', action_bad, 'action'), F('F2', f'{obj}在{place}', 'object')]
            else:
                facts_neg = [F('F1', f'{obj}在{place}', 'object'), F('F2', action_bad, 'action')]
            scene = [S('S1', '夜')]
            pos = {'fullText': pos_text, 'candidateText': pos_text, 'facts': facts_pos,
                   'scene': scene, 'visible': [], 'gold': ['F1'], 'role': 'support', 'note': 'direct-action'}
            if mode == 'authorization':
                neg = {'fullText': pos_text, 'candidateText': pos_text, 'facts': facts_neg,
                       'scene': scene, 'visible': [], 'gold': ['F1'], 'role': 'checked', 'note': f'other-{neg_kind}'}
            else:
                neg = {'fullText': stmt_text, 'candidateText': stmt_text, 'facts': facts_pos,
                       'scene': scene, 'visible': [], 'gold': ['F1'], 'role': 'checked', 'note': 'alternative-action'}
            out += emit(fam, i, mode, pos, neg, tname)
    return out


def build_general_capability():
    rows = [json.loads(l) for l in OLD.read_text(encoding='utf-8').splitlines() if l.strip()]
    out = []
    for r in rows:
        if r['category'] != 'general' or r['split'] not in ('dev', 'confirm'):
            continue
        rec = dict(r)
        rec['capabilitySourceSplit'] = r['split']
        rec['split'] = 'capability'
        rec['origin'] = 'general-capability'
        out.append(rec)
    return out


def source_ids(r):
    return ({x['sourceId'] for x in r.get('facts', [])}
            | {x['sourceId'] for x in r.get('scene', [])}
            | {x['sourceId'] for x in r.get('visible', [])})


def audit(rows, cap):
    issues = []
    by_pair = defaultdict(list)
    for r in rows:
        by_pair[r['pairId']].append(r)
    for pid, rs in by_pair.items():
        if len(rs) != 2:
            issues.append(f'pair-size:{pid}:{len(rs)}')
            continue
        if {r['label'] for r in rs} != {'supported', 'unsupported'}:
            issues.append(f'pair-labels:{pid}')
        if len({r['pairMode'] for r in rs}) != 1:
            issues.append(f'pair-mode-diff:{pid}')
        a, b = rs
        for r in rs:
            if r['candidateText'] not in r['fullText']:
                issues.append(f'candidate-not-in-text:{r["exampleId"]}')
            ids = source_ids(r)
            for gid in r.get('goldSourceIds', []):
                if gid not in ids:
                    issues.append(f'gold-missing:{r["exampleId"]}:{gid}')
        if a['pairMode'] == 'authorization':
            if a['fullText'] != b['fullText'] or a['candidateText'] != b['candidateText']:
                issues.append(f'auth-text-diff:{pid}')
            for k in ('facts', 'scene', 'visible'):
                if len(a[k]) != len(b[k]):
                    issues.append(f'auth-count-diff:{pid}:{k}')
            diffs = [k for k in ('facts', 'scene', 'visible') if a[k] != b[k]]
            if not diffs:
                issues.append(f'auth-no-diff:{pid}')
            if a['category'] != 'extra-action' and diffs != ['facts' if a['facts'] != b['facts'] else ('scene' if a['scene'] != b['scene'] else 'visible')]:
                issues.append(f'auth-nonminimal:{pid}:{diffs}')
            if a['category'] == 'extra-action' and diffs not in (['facts'], ['facts', 'scene'], ['facts', 'visible']):
                # extra only varies facts in this design
                issues.append(f'auth-extra-diff:{pid}:{diffs}')
        else:
            for k in ('facts', 'scene', 'visible'):
                if a[k] != b[k]:
                    issues.append(f'stmt-auth-diff:{pid}:{k}')
            if a['candidateText'] == b['candidateText']:
                issues.append(f'stmt-same-candidate:{pid}')
            rests = [r['fullText'].replace(r['candidateText'], '', 1) for r in rs]
            if rests[0] != rests[1]:
                issues.append(f'stmt-rest-diff:{pid}')
    counts = {
        'totalExamples': len(rows), 'totalPairs': len(by_pair),
        'byCategory': dict(Counter(r['category'] for r in rows)),
        'bySplit': dict(Counter(r['split'] for r in rows)),
        'byCategorySplit': dict(Counter(f'{r["category"]}:{r["split"]}' for r in rows)),
        'byMode': dict(Counter(r['pairMode'] for r in rows)),
        'byLabel': dict(Counter(r['label'] for r in rows)),
        'pairModeByCategorySplit': {},
        'familySize': {},
    }
    for k in sorted(counts['byCategorySplit']):
        cat, split = k.split(':')
        pairs = {r['pairId'] for r in rows if r['category'] == cat and r['split'] == split and r['label'] == 'supported'}
        counts['pairModeByCategorySplit'][k] = dict(Counter(next(r['pairMode'] for r in rows if r['pairId'] == p) for p in pairs))
    fams = defaultdict(list)
    for r in rows:
        fams[r['sourceGroupId']].append(r)
    for fid, rs in fams.items():
        counts['familySize'][fid] = len({r['pairId'] for r in rs})
        if len({r['split'] for r in rs}) != 1:
            issues.append(f'family-cross-split:{fid}')
    tmpl = defaultdict(set)
    for r in rows:
        tmpl[r['templateId']].add(r['split'])
    for tid, ss in tmpl.items():
        if len(ss) != 1:
            issues.append(f'template-cross-split:{tid}:{ss}')
    for field in ('fullText', 'candidateText'):
        m = defaultdict(set)
        for r in rows:
            m[r[field]].add(r['split'])
        for k, ss in m.items():
            if len(ss) > 1:
                issues.append(f'{field}-cross-split:{k[:40]}:{ss}')
    sids = Counter(r['sourceId'] for r in rows)
    for sid, n in sids.items():
        if n != 2:
            issues.append(f'source-id-count:{sid}:{n}')
    reg = [json.loads(l) for l in REG.read_text(encoding='utf-8').splitlines() if l.strip()]
    reg_texts = {r['fullText'] for r in reg} | {r['candidateText'] for r in reg}
    for r in rows:
        if r['fullText'] in reg_texts or r['candidateText'] in reg_texts:
            issues.append(f'regression-text-overlap:{r["exampleId"]}')
    direct = {
        'body': any(r['label'] == 'supported' and r['candidateText'] == '袖口湿透'
                    and any(f['factText'] == '袖口湿透' for f in r['facts']) for r in rows),
        'background': any(r['label'] == 'supported' and r['candidateText'] == '河雾里'
                         and any(s['text'] == '河雾' for s in r['scene']) for r in rows),
        'visible-state': any(r['label'] == 'supported' and r['candidateText'] == '纸灯已点亮'
                            and any(s['text'] == '纸灯已点亮' for s in r['scene']) for r in rows),
        'extra-action': any(r['label'] == 'supported' and r['candidateText'] == '阿棠把鱼筐推开。'
                           and any(f['factText'] == '把鱼筐推开' for f in r['facts']) for r in rows),
    }
    for k, v in direct.items():
        if not v:
            issues.append(f'missing-direct-easy:{k}')
    return {
        'issueCount': len(issues), 'issues': issues[:100], 'counts': counts,
        'directEasy': direct, 'generalCapability': {'n': len(cap), 'labels': dict(Counter(r['label'] for r in cap))},
    }


def main():
    rows = build_body() + build_bg() + build_vis() + build_ex()
    cap = build_general_capability()
    rows.sort(key=lambda r: (r['split'], r['category'], r['sourceGroupId'], r['pairId'], r['label']))
    cap.sort(key=lambda r: (r['capabilitySourceSplit'], r['sourceGroupId'], r['pairId'], r['label']))
    with OUT.open('w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    with CAP.open('w', encoding='utf-8') as f:
        for r in cap:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    audit_res = audit(rows, cap)
    audit_res['hashes'] = {
        'pairs-target-v1.jsonl': hashlib.sha256(OUT.read_bytes()).hexdigest(),
        'general-capability-v1.jsonl': hashlib.sha256(CAP.read_bytes()).hexdigest(),
        'regression-v1.jsonl': hashlib.sha256(REG.read_bytes()).hexdigest(),
    }
    AUDIT.write_text(json.dumps(audit_res, ensure_ascii=False, indent=2), encoding='utf-8')
    freeze = {
        'version': 'statement-verification-target-pairs-v1',
        'created': '2026-11-05',
        'task': 'target-expression paired material; no training',
        'counts': audit_res['counts'],
        'generalCapability': audit_res['generalCapability'],
        'hashes': audit_res['hashes'],
        'auditIssueCount': audit_res['issueCount'],
        'auditSha256': hashlib.sha256(AUDIT.read_bytes()).hexdigest(),
        'pairs': '4 categories x (20 train + 5 dev + 6 confirm); source/template family split',
    }
    FREEZE.write_text(json.dumps(freeze, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({
        'pairs': audit_res['counts']['totalPairs'], 'examples': audit_res['counts']['totalExamples'],
        'byCategory': audit_res['counts']['byCategory'], 'bySplit': audit_res['counts']['bySplit'],
        'byLabel': audit_res['counts']['byLabel'], 'byMode': audit_res['counts']['byMode'],
        'pairModeByCategorySplit': audit_res['counts']['pairModeByCategorySplit'],
        'familySize': audit_res['counts']['familySize'],
        'generalCapability': audit_res['generalCapability'],
        'issueCount': audit_res['issueCount'], 'issues': audit_res['issues'][:30],
        'directEasy': audit_res['directEasy'], 'hashes': audit_res['hashes'],
    }, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
