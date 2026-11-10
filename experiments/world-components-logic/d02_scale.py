"""Build the assistant-draft scale-v2 batch (40 groups / 320 targeted samples).

This extends pilot-v1 to a first scale batch.  It is still assistant-authored,
not human-reviewed, and not a training or acceptance result.  The 20 existing
groups keep their five variants and gain three generated scope cases; 20 new
groups contribute five authored variants plus the same three scope cases.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import short_d02_checkers as checkers
from d02_pilot import (WORLDS, GROUPS, B, E, case_rows, build_audits)

ROOT = HERE / 'data' / 'd02-checkers' / 'scale-v2'
SPLITS = ('train', 'development', 'calibration', 'sealed')


def ent(kind, name, aliases=()):
    return {'type': kind, 'name': name, 'aliases': list(aliases)}


EXTRA_ENTITIES = {
    'harbor-v1': {
        'rope': ent('item', '麻绳', ['绳子']),
        'oil': ent('item', '灯油'),
        'net': ent('item', '渔网'),
        'twine': ent('item', '细绳'),
        'boat': ent('item', '小艇'),
        'water': ent('location', '水面'),
    },
    'archive-v1': {
        'shelf': ent('location', '书架'),
        'wax': ent('item', '封蜡', ['蜡']),
        'card': ent('item', '索引卡'),
        'pen': ent('item', '钢笔'),
        'cart': ent('item', '推车'),
    },
    'workshop-v1': {
        'dye': ent('item', '染料'),
        'scissors': ent('item', '剪刀'),
        'brush': ent('item', '刷子', ['毛刷']),
        'glue': ent('item', '胶水'),
        'ruler': ent('item', '直尺'),
    },
    'signal-v1': {
        'antenna': ent('item', '天线'),
        'log': ent('item', '值班记录'),
        'pen': ent('item', '钢笔', ['笔']),
        'lamp': ent('item', '信号灯'),
        'wrench': ent('item', '扳手'),
        'bolt': ent('item', '螺栓'),
    },
}

NEW_GROUPS = [
    dict(id='harbor-dock', world='harbor-v1', actor='lin', other='zhou', split='train',
         prompt='林澈要把木箱搬到码头。',
         core=('林澈把木箱搬到码头。', [B('林澈', ['subject'], 'lin'),
                                       B('木箱', ['object'], 'crate'),
                                       B('码头', ['destination'], 'dock')]),
         swap=('周岚把木箱搬到码头。', [B('周岚', ['subject'], 'zhou'),
                                       B('木箱', ['object'], 'crate'),
                                       B('码头', ['destination'], 'dock')]),
         result=('林澈把木箱搬到码头，木箱已经放稳了。',
                 [B('林澈', ['subject'], 'lin'), B('木箱', ['object'], 'crate'),
                  B('码头', ['destination'], 'dock')],
                 [E('unsettled_result', '木箱已经放稳了', 'main')]),
         special=('他把木箱搬到码头。', [B('他', ['subject'], 'zhou', basis='pronoun'),
                                         B('木箱', ['object'], 'crate'),
                                         B('码头', ['destination'], 'dock')],
                  'attempt', [], ['reference_requires_review']),
         role=('林澈和周岚一起搬木箱。', [B('林澈', ['subject'], 'lin'),
                                         B('周岚', ['subject'], 'zhou'),
                                         B('木箱', ['object'], 'crate')],
               'attempt', [], [])),
    dict(id='harbor-rope', world='harbor-v1', actor='lin', other='zhou', split='train',
         prompt='林澈要用麻绳把木箱捆紧。',
         core=('林澈用麻绳捆住木箱。', [B('林澈', ['subject'], 'lin'),
                                       B('麻绳', ['tool'], 'rope'),
                                       B('木箱', ['object'], 'crate')]),
         swap=('周岚用麻绳捆住木箱。', [B('周岚', ['subject'], 'zhou'),
                                       B('麻绳', ['tool'], 'rope'),
                                       B('木箱', ['object'], 'crate')]),
         result=('林澈用麻绳捆住木箱，木箱已经捆紧了。',
                 [B('林澈', ['subject'], 'lin'), B('麻绳', ['tool'], 'rope'),
                  B('木箱', ['object'], 'crate')],
                 [E('unsettled_result', '木箱已经捆紧了', 'main')]),
         special=('林澈拿起绳子。', [B('林澈', ['subject'], 'lin'),
                                     B('绳子', ['object'], 'rope', basis='alias')],
                  'attempt', [], ['alias_requires_review']),
         role=('林澈从周岚那里取麻绳。', [B('林澈', ['subject'], 'lin'),
                                         B('周岚', [], 'zhou', diagnostic=['source']),
                                         B('麻绳', ['object'], 'rope')],
               'attempt', [], ['diagnostic_role_requires_review'])),
    dict(id='harbor-lamp-oil', world='harbor-v1', actor='lin', other='zhou', split='train',
         prompt='林澈要给提灯加灯油。',
         core=('林澈把灯油倒进提灯。', [B('林澈', ['subject'], 'lin'),
                                       B('灯油', ['object'], 'oil'),
                                       B('提灯', ['destination'], 'lamp')]),
         swap=('周岚把灯油倒进提灯。', [B('周岚', ['subject'], 'zhou'),
                                       B('灯油', ['object'], 'oil'),
                                       B('提灯', ['destination'], 'lamp')]),
         result=('林澈把灯油倒进提灯，提灯已经加满了。',
                 [B('林澈', ['subject'], 'lin'), B('灯油', ['object'], 'oil'),
                  B('提灯', ['destination'], 'lamp')],
                 [E('unsettled_result', '提灯已经加满了', 'main')]),
         special=('林澈把煤油倒进提灯。', [B('林澈', ['subject'], 'lin'),
                                          B('煤油', ['object'], status='unknown_entity'),
                                          B('提灯', ['destination'], 'lamp')],
                  'attempt', [], ['unresolved_role_object']),
         role=('林澈用灯油擦拭提灯。', [B('林澈', ['subject'], 'lin'),
                                       B('灯油', ['tool'], 'oil'),
                                       B('提灯', ['object'], 'lamp')],
               'attempt', [], [])),
    dict(id='harbor-net', world='harbor-v1', actor='lin', other='zhou', split='development',
         prompt='林澈要用细绳补好渔网。',
         core=('林澈用细绳补渔网。', [B('林澈', ['subject'], 'lin'),
                                     B('细绳', ['tool'], 'twine'),
                                     B('渔网', ['object'], 'net')]),
         swap=('周岚用细绳补渔网。', [B('周岚', ['subject'], 'zhou'),
                                     B('细绳', ['tool'], 'twine'),
                                     B('渔网', ['object'], 'net')]),
         result=('林澈用细绳补渔网，渔网已经补好了。',
                 [B('林澈', ['subject'], 'lin'), B('细绳', ['tool'], 'twine'),
                  B('渔网', ['object'], 'net')],
                 [E('unsettled_result', '渔网已经补好了', 'main')]),
         special=('如果细绳够长，林澈就补渔网。', [B('细绳', ['tool'], 'twine'),
                                                   B('林澈', ['subject'], 'lin'),
                                                   B('渔网', ['object'], 'net')],
                  'attempt', [E('condition_scope', '细绳够长', 'condition', False)], []),
         role=('林澈把渔网放到码头。', [B('林澈', ['subject'], 'lin'),
                                       B('渔网', ['object'], 'net'),
                                       B('码头', ['destination'], 'dock')],
               'attempt', [], [])),
    dict(id='harbor-boat', world='harbor-v1', actor='lin', other='zhou', split='calibration',
         prompt='林澈要把小艇推到水面。',
         core=('林澈把小艇推到水面。', [B('林澈', ['subject'], 'lin'),
                                       B('小艇', ['object'], 'boat'),
                                       B('水面', ['destination'], 'water')]),
         swap=('周岚把小艇推到水面。', [B('周岚', ['subject'], 'zhou'),
                                       B('小艇', ['object'], 'boat'),
                                       B('水面', ['destination'], 'water')]),
         result=('林澈把小艇推到水面，小艇已经下水了。',
                 [B('林澈', ['subject'], 'lin'), B('小艇', ['object'], 'boat'),
                  B('水面', ['destination'], 'water')],
                 [E('unsettled_result', '小艇已经下水了', 'main')]),
         special=('林澈在水面等待。', [B('林澈', ['subject'], 'lin'),
                                       B('水面', [], 'water', diagnostic=['static_location'])],
                  'attempt', [], ['diagnostic_role_requires_review']),
         role=('林澈把麻绳交给周岚。', [B('林澈', ['subject'], 'lin'),
                                       B('麻绳', ['object'], 'rope'),
                                       B('周岚', ['recipient'], 'zhou')],
               'attempt', [], [])),
    dict(id='archive-shelf', world='archive-v1', actor='yu', other='zheng', split='train',
         prompt='余荞把登记簿放到书架。',
         core=('余荞把登记簿放到书架。', [B('余荞', ['subject'], 'yu'),
                                         B('登记簿', ['object'], 'ledger'),
                                         B('书架', ['destination'], 'shelf')]),
         swap=('郑栖把登记簿放到书架。', [B('郑栖', ['subject'], 'zheng'),
                                         B('登记簿', ['object'], 'ledger'),
                                         B('书架', ['destination'], 'shelf')]),
         result=('余荞把登记簿放到书架，登记簿已经放好了。',
                 [B('余荞', ['subject'], 'yu'), B('登记簿', ['object'], 'ledger'),
                  B('书架', ['destination'], 'shelf')],
                 [E('unsettled_result', '登记簿已经放好了', 'main')]),
         special=('她把登记簿放到书架。', [B('她', ['subject'], 'yu', basis='pronoun'),
                                           B('登记簿', ['object'], 'ledger'),
                                           B('书架', ['destination'], 'shelf')],
                  'attempt', [], ['reference_requires_review']),
         role=('余荞从郑栖那里取登记簿。', [B('余荞', ['subject'], 'yu'),
                                           B('郑栖', [], 'zheng', diagnostic=['source']),
                                           B('登记簿', ['object'], 'ledger')],
               'attempt', [], ['diagnostic_role_requires_review'])),
    dict(id='archive-wax', world='archive-v1', actor='yu', other='zheng', split='train',
         prompt='余荞要用封蜡封信封。',
         core=('余荞用封蜡封信封。', [B('余荞', ['subject'], 'yu'),
                                     B('封蜡', ['tool'], 'wax'),
                                     B('信封', ['object'], 'envelope')]),
         swap=('郑栖用封蜡封信封。', [B('郑栖', ['subject'], 'zheng'),
                                     B('封蜡', ['tool'], 'wax'),
                                     B('信封', ['object'], 'envelope')]),
         result=('余荞用封蜡封信封，信封已经封好了。',
                 [B('余荞', ['subject'], 'yu'), B('封蜡', ['tool'], 'wax'),
                  B('信封', ['object'], 'envelope')],
                 [E('unsettled_result', '信封已经封好了', 'main')]),
         special=('余荞拿起蜡。', [B('余荞', ['subject'], 'yu'),
                                   B('蜡', ['object'], 'wax', basis='alias')],
                  'attempt', [], ['alias_requires_review']),
         role=('余荞把信封交给郑栖。', [B('余荞', ['subject'], 'yu'),
                                       B('信封', ['object'], 'envelope'),
                                       B('郑栖', ['recipient'], 'zheng')],
               'attempt', [], [])),
    dict(id='archive-card', world='archive-v1', actor='yu', other='zheng', split='train',
         prompt='余荞要用钢笔写索引卡。',
         core=('余荞用钢笔写索引卡。', [B('余荞', ['subject'], 'yu'),
                                       B('钢笔', ['tool'], 'pen'),
                                       B('索引卡', ['object'], 'card')]),
         swap=('郑栖用钢笔写索引卡。', [B('郑栖', ['subject'], 'zheng'),
                                       B('钢笔', ['tool'], 'pen'),
                                       B('索引卡', ['object'], 'card')]),
         result=('余荞用钢笔写索引卡，索引卡已经写好了。',
                 [B('余荞', ['subject'], 'yu'), B('钢笔', ['tool'], 'pen'),
                  B('索引卡', ['object'], 'card')],
                 [E('unsettled_result', '索引卡已经写好了', 'main')]),
         special=('如果钢笔有墨，余荞就写索引卡。', [B('钢笔', ['tool'], 'pen'),
                                                     B('余荞', ['subject'], 'yu'),
                                                     B('索引卡', ['object'], 'card')],
                  'attempt', [E('condition_scope', '钢笔有墨', 'condition', False)], []),
         role=('余荞用郑栖写索引卡。', [B('余荞', ['subject'], 'yu'),
                                       B('郑栖', ['tool'], 'zheng'),
                                       B('索引卡', ['object'], 'card')],
               'attempt', [], ['role_type_mismatch'])),
    dict(id='archive-cart', world='archive-v1', actor='yu', other='zheng', split='sealed',
         prompt='余荞把推车推到阅览室。',
         core=('余荞把推车推到阅览室。', [B('余荞', ['subject'], 'yu'),
                                         B('推车', ['object'], 'cart'),
                                         B('阅览室', ['destination'], 'room')]),
         swap=('郑栖把推车推到阅览室。', [B('郑栖', ['subject'], 'zheng'),
                                         B('推车', ['object'], 'cart'),
                                         B('阅览室', ['destination'], 'room')]),
         result=('余荞把推车推到阅览室，推车已经停稳了。',
                 [B('余荞', ['subject'], 'yu'), B('推车', ['object'], 'cart'),
                  B('阅览室', ['destination'], 'room')],
                 [E('unsettled_result', '推车已经停稳了', 'main')]),
         special=('余荞把麻袋放到推车。', [B('余荞', ['subject'], 'yu'),
                                           B('麻袋', ['object'], status='unknown_entity'),
                                           B('推车', ['destination'], 'cart')],
                  'attempt', [], ['unresolved_role_object']),
         role=('余荞和郑栖一起推推车。', [B('余荞', ['subject'], 'yu'),
                                         B('郑栖', ['subject'], 'zheng'),
                                         B('推车', ['object'], 'cart')],
               'attempt', [], [])),
    dict(id='archive-return', world='archive-v1', actor='yu', other='zheng', split='sealed',
         prompt='余荞把借阅牌放回档案柜。',
         core=('余荞把借阅牌放回档案柜。', [B('余荞', ['subject'], 'yu'),
                                           B('借阅牌', ['object'], 'badge'),
                                           B('档案柜', ['destination'], 'cabinet')]),
         swap=('郑栖把借阅牌放回档案柜。', [B('郑栖', ['subject'], 'zheng'),
                                           B('借阅牌', ['object'], 'badge'),
                                           B('档案柜', ['destination'], 'cabinet')]),
         result=('余荞把借阅牌放回档案柜，借阅牌已经放回去了。',
                 [B('余荞', ['subject'], 'yu'), B('借阅牌', ['object'], 'badge'),
                  B('档案柜', ['destination'], 'cabinet')],
                 [E('unsettled_result', '借阅牌已经放回去了', 'main')]),
         special=('余荞在档案柜旁等待。', [B('余荞', ['subject'], 'yu'),
                                           B('档案柜', [], 'cabinet',
                                             diagnostic=['static_location'])],
                  'attempt', [], ['diagnostic_role_requires_review']),
         role=('余荞用钢笔在借阅牌上写字。', [B('余荞', ['subject'], 'yu'),
                                             B('钢笔', ['tool'], 'pen'),
                                             B('借阅牌', ['object'], 'badge')],
               'attempt', [], [])),
    dict(id='workshop-dye', world='workshop-v1', actor='tang', other='lian', split='train',
         prompt='唐霁用搅拌棒把染料调开。',
         core=('唐霁用搅拌棒调开染料。', [B('唐霁', ['subject'], 'tang'),
                                         B('搅拌棒', ['tool'], 'rod'),
                                         B('染料', ['object'], 'dye')]),
         swap=('连笙用搅拌棒调开染料。', [B('连笙', ['subject'], 'lian'),
                                         B('搅拌棒', ['tool'], 'rod'),
                                         B('染料', ['object'], 'dye')]),
         result=('唐霁用搅拌棒调开染料，染料已经调开了。',
                 [B('唐霁', ['subject'], 'tang'), B('搅拌棒', ['tool'], 'rod'),
                  B('染料', ['object'], 'dye')],
                 [E('unsettled_result', '染料已经调开了', 'main')]),
         special=('如果染料结块，唐霁就搅动染料。', [B('染料', ['object'], 'dye', occurrence=1),
                                                     B('唐霁', ['subject'], 'tang')],
                  'attempt', [E('condition_scope', '染料结块', 'condition', False)], []),
         role=('唐霁把染料倒进染料碗。', [B('唐霁', ['subject'], 'tang'),
                                         B('染料', ['object'], 'dye'),
                                         B('染料碗', ['destination'], 'bowl')],
               'attempt', [], [])),
    dict(id='workshop-cut', world='workshop-v1', actor='tang', other='lian', split='train',
         prompt='唐霁用剪刀剪开样布。',
         core=('唐霁用剪刀剪开样布。', [B('唐霁', ['subject'], 'tang'),
                                       B('剪刀', ['tool'], 'scissors'),
                                       B('样布', ['object'], 'cloth')]),
         swap=('连笙用剪刀剪开样布。', [B('连笙', ['subject'], 'lian'),
                                       B('剪刀', ['tool'], 'scissors'),
                                       B('样布', ['object'], 'cloth')]),
         result=('唐霁用剪刀剪开样布，样布已经剪开了。',
                 [B('唐霁', ['subject'], 'tang'), B('剪刀', ['tool'], 'scissors'),
                  B('样布', ['object'], 'cloth')],
                 [E('unsettled_result', '样布已经剪开了', 'main')]),
         special=('唐霁用锯子剪样布。', [B('唐霁', ['subject'], 'tang'),
                                         B('锯子', ['tool'], status='unknown_entity'),
                                         B('样布', ['object'], 'cloth')],
                  'attempt', [], ['unresolved_role_tool']),
         role=('唐霁用连笙剪样布。', [B('唐霁', ['subject'], 'tang'),
                                     B('连笙', ['tool'], 'lian'),
                                     B('样布', ['object'], 'cloth')],
               'attempt', [], ['role_type_mismatch'])),
    dict(id='workshop-glue', world='workshop-v1', actor='tang', other='lian', split='train',
         prompt='唐霁用刷子把胶水涂匀。',
         core=('唐霁用刷子涂胶水。', [B('唐霁', ['subject'], 'tang'),
                                     B('刷子', ['tool'], 'brush'),
                                     B('胶水', ['object'], 'glue')]),
         swap=('连笙用刷子涂胶水。', [B('连笙', ['subject'], 'lian'),
                                     B('刷子', ['tool'], 'brush'),
                                     B('胶水', ['object'], 'glue')]),
         result=('唐霁用刷子涂胶水，胶水已经涂匀了。',
                 [B('唐霁', ['subject'], 'tang'), B('刷子', ['tool'], 'brush'),
                  B('胶水', ['object'], 'glue')],
                 [E('unsettled_result', '胶水已经涂匀了', 'main')]),
         special=('唐霁拿起毛刷。', [B('唐霁', ['subject'], 'tang'),
                                     B('毛刷', ['object'], 'brush', basis='alias')],
                  'attempt', [], ['alias_requires_review']),
         role=('唐霁把胶水放到配色台。', [B('唐霁', ['subject'], 'tang'),
                                         B('胶水', ['object'], 'glue'),
                                         B('配色台', ['destination'], 'bench')],
               'attempt', [], [])),
    dict(id='workshop-measure', world='workshop-v1', actor='tang', other='lian', split='sealed',
         prompt='唐霁用直尺量样布。',
         core=('唐霁用直尺量样布。', [B('唐霁', ['subject'], 'tang'),
                                     B('直尺', ['tool'], 'ruler'),
                                     B('样布', ['object'], 'cloth')]),
         swap=('连笙用直尺量样布。', [B('连笙', ['subject'], 'lian'),
                                     B('直尺', ['tool'], 'ruler'),
                                     B('样布', ['object'], 'cloth')]),
         result=('唐霁用直尺量样布，样布已经量好了。',
                 [B('唐霁', ['subject'], 'tang'), B('直尺', ['tool'], 'ruler'),
                  B('样布', ['object'], 'cloth')],
                 [E('unsettled_result', '样布已经量好了', 'main')]),
         special=('他用直尺量样布。', [B('他', ['subject'], 'tang', basis='pronoun'),
                                       B('直尺', ['tool'], 'ruler'),
                                       B('样布', ['object'], 'cloth')],
                  'attempt', [], ['reference_requires_review']),
         role=('唐霁从连笙那里取直尺。', [B('唐霁', ['subject'], 'tang'),
                                         B('连笙', [], 'lian', diagnostic=['source']),
                                         B('直尺', ['object'], 'ruler')],
               'attempt', [], ['diagnostic_role_requires_review'])),
    dict(id='workshop-hang', world='workshop-v1', actor='tang', other='lian', split='sealed',
         prompt='唐霁把样布挂到晾架。',
         core=('唐霁把样布挂到晾架。', [B('唐霁', ['subject'], 'tang'),
                                         B('样布', ['object'], 'cloth'),
                                         B('晾架', ['destination'], 'rack')]),
         swap=('连笙把样布挂到晾架。', [B('连笙', ['subject'], 'lian'),
                                         B('样布', ['object'], 'cloth'),
                                         B('晾架', ['destination'], 'rack')]),
         result=('唐霁把样布挂到晾架，样布已经挂好了。',
                 [B('唐霁', ['subject'], 'tang'), B('样布', ['object'], 'cloth'),
                  B('晾架', ['destination'], 'rack')],
                 [E('unsettled_result', '样布已经挂好了', 'main')]),
         special=('唐霁在晾架旁等待。', [B('唐霁', ['subject'], 'tang'),
                                         B('晾架', [], 'rack', diagnostic=['static_location'])],
                  'attempt', [], ['diagnostic_role_requires_review']),
         role=('唐霁把样布交给连笙。', [B('唐霁', ['subject'], 'tang'),
                                         B('样布', ['object'], 'cloth'),
                                         B('连笙', ['recipient'], 'lian')],
               'attempt', [], [])),
    dict(id='signal-battery', world='signal-v1', actor='wei', other='xie', split='train',
         prompt='周苇把电池装进信号机。',
         core=('周苇把电池装进信号机。', [B('周苇', ['subject'], 'wei'),
                                         B('电池', ['object'], 'battery'),
                                         B('信号机', ['destination'], 'radio')]),
         swap=('谢迟把电池装进信号机。', [B('谢迟', ['subject'], 'xie'),
                                         B('电池', ['object'], 'battery'),
                                         B('信号机', ['destination'], 'radio')]),
         result=('周苇把电池装进信号机，信号机已经通电了。',
                 [B('周苇', ['subject'], 'wei'), B('电池', ['object'], 'battery'),
                  B('信号机', ['destination'], 'radio')],
                 [E('unsettled_result', '信号机已经通电了', 'main')]),
         special=('如果电池有电，周苇就装电池。', [B('电池', ['object'], 'battery', occurrence=1),
                                                     B('周苇', ['subject'], 'wei')],
                  'attempt', [E('condition_scope', '电池有电', 'condition', False)], []),
         role=('周苇用电池测试信号机。', [B('周苇', ['subject'], 'wei'),
                                         B('电池', ['tool'], 'battery'),
                                         B('信号机', ['object'], 'radio')],
               'attempt', [], [])),
    dict(id='signal-antenna', world='signal-v1', actor='wei', other='xie', split='train',
         prompt='周苇用扳手调天线。',
         core=('周苇用扳手调天线。', [B('周苇', ['subject'], 'wei'),
                                     B('扳手', ['tool'], 'wrench'),
                                     B('天线', ['object'], 'antenna')]),
         swap=('谢迟用扳手调天线。', [B('谢迟', ['subject'], 'xie'),
                                     B('扳手', ['tool'], 'wrench'),
                                     B('天线', ['object'], 'antenna')]),
         result=('周苇用扳手调天线，天线已经调好了。',
                 [B('周苇', ['subject'], 'wei'), B('扳手', ['tool'], 'wrench'),
                  B('天线', ['object'], 'antenna')],
                 [E('unsettled_result', '天线已经调好了', 'main')]),
         special=('周苇用铁锤调天线。', [B('周苇', ['subject'], 'wei'),
                                         B('铁锤', ['tool'], status='unknown_entity'),
                                         B('天线', ['object'], 'antenna')],
                  'attempt', [], ['unresolved_role_tool']),
         role=('周苇用谢迟调天线。', [B('周苇', ['subject'], 'wei'),
                                     B('谢迟', ['tool'], 'xie'),
                                     B('天线', ['object'], 'antenna')],
               'attempt', [], ['role_type_mismatch'])),
    dict(id='signal-log', world='signal-v1', actor='wei', other='xie', split='train',
         prompt='周苇用钢笔写值班记录。',
         core=('周苇用钢笔写值班记录。', [B('周苇', ['subject'], 'wei'),
                                         B('钢笔', ['tool'], 'pen'),
                                         B('值班记录', ['object'], 'log')]),
         swap=('谢迟用钢笔写值班记录。', [B('谢迟', ['subject'], 'xie'),
                                         B('钢笔', ['tool'], 'pen'),
                                         B('值班记录', ['object'], 'log')]),
         result=('周苇用钢笔写值班记录，值班记录已经写好了。',
                 [B('周苇', ['subject'], 'wei'), B('钢笔', ['tool'], 'pen'),
                  B('值班记录', ['object'], 'log')],
                 [E('unsettled_result', '值班记录已经写好了', 'main')]),
         special=('周苇拿起笔。', [B('周苇', ['subject'], 'wei'),
                                   B('笔', ['object'], 'pen', basis='alias')],
                  'attempt', [], ['alias_requires_review']),
         role=('周苇把值班记录放到值守室。', [B('周苇', ['subject'], 'wei'),
                                             B('值班记录', ['object'], 'log'),
                                             B('值守室', ['destination'], 'room')],
               'attempt', [], [])),
    dict(id='signal-lamp', world='signal-v1', actor='wei', other='xie', split='development',
         prompt='周苇用信号灯向谢迟发信号。',
         core=('周苇用信号灯向谢迟发信号。', [B('周苇', ['subject'], 'wei'),
                                             B('信号灯', ['tool'], 'lamp'),
                                             B('谢迟', ['recipient'], 'xie')]),
         swap=('谢迟用信号灯向周苇发信号。', [B('谢迟', ['subject'], 'xie'),
                                             B('信号灯', ['tool'], 'lamp'),
                                             B('周苇', ['recipient'], 'wei')]),
         result=('周苇用信号灯向谢迟发信号，信号已经发出了。',
                 [B('周苇', ['subject'], 'wei'), B('信号灯', ['tool'], 'lamp'),
                  B('谢迟', ['recipient'], 'xie')],
                 [E('unsettled_result', '信号已经发出了', 'main')]),
         special=('周苇喊道：“我已经发出信号了！”', [B('周苇', ['subject'], 'wei')],
                  'attempt', [E('success_word_in_quote', '我已经发出信号了', 'quote', False)], []),
         role=('周苇从谢迟那里取信号灯。', [B('周苇', ['subject'], 'wei'),
                                           B('谢迟', [], 'xie', diagnostic=['source']),
                                           B('信号灯', ['object'], 'lamp')],
               'attempt', [], ['diagnostic_role_requires_review'])),
    dict(id='signal-wrench', world='signal-v1', actor='wei', other='xie', split='calibration',
         prompt='周苇用扳手拧紧螺栓。',
         core=('周苇用扳手拧紧螺栓。', [B('周苇', ['subject'], 'wei'),
                                     B('扳手', ['tool'], 'wrench'),
                                     B('螺栓', ['object'], 'bolt')]),
         swap=('谢迟用扳手拧紧螺栓。', [B('谢迟', ['subject'], 'xie'),
                                     B('扳手', ['tool'], 'wrench'),
                                     B('螺栓', ['object'], 'bolt')]),
         result=('周苇用扳手拧紧螺栓，螺栓已经拧紧了。',
                 [B('周苇', ['subject'], 'wei'), B('扳手', ['tool'], 'wrench'),
                  B('螺栓', ['object'], 'bolt')],
                 [E('unsettled_result', '螺栓已经拧紧了', 'main')]),
         special=('周苇用钳子拧螺栓。', [B('周苇', ['subject'], 'wei'),
                                       B('钳子', ['tool'], status='unknown_entity'),
                                       B('螺栓', ['object'], 'bolt')],
                  'attempt', [], ['unresolved_role_tool']),
         role=('周苇把扳手放到值守室。', [B('周苇', ['subject'], 'wei'),
                                         B('扳手', ['object'], 'wrench'),
                                         B('值守室', ['destination'], 'room')],
               'attempt', [], [])),
]


def apply_entities():
    for world_id, additions in EXTRA_ENTITIES.items():
        WORLDS[world_id]['entities'].update(copy.deepcopy(additions))


def extra_cases(group):
    """Three generated scope cases that do not change the core role bindings."""
    world = WORLDS[group['world']]
    actor = group['actor']
    actor_name = world['entities'][actor]['name']
    core_text, core_bindings = group['core']
    return [
        dict(suffix='multi', kind='multi_step', text='四周很安静，' + core_text,
             bindings=copy.deepcopy(core_bindings), label='attempt', exprIssues=[],
             expected=('accept', 'accept', 'accept'),
             mustCodes=[], tags=['scale_extra', 'multi_step']),
        dict(suffix='condition', kind='condition', text='如果四周安全，' + core_text,
             bindings=copy.deepcopy(core_bindings), label='attempt',
             exprIssues=[E('condition_scope', '四周安全', 'condition', False)],
             expected=('accept', 'accept', 'accept'),
             mustCodes=[], tags=['scale_extra', 'condition']),
        dict(suffix='quote', kind='quote',
             text=actor_name + '喊道：“我已经完成了。”',
             bindings=[B(actor_name, ['subject'], actor)],
             label='attempt',
             exprIssues=[E('success_word_in_quote', '我已经完成了', 'quote', False)],
             expected=('accept', 'accept', 'accept'),
             mustCodes=[], tags=['scale_extra', 'quote']),
        dict(suffix='result2', kind='unsettled_result',
             text=core_text.rstrip('。') + '，事情已经办妥了。',
             bindings=copy.deepcopy(core_bindings), label='mixed',
             exprIssues=[E('unsettled_result', '事情已经办妥了', 'main')],
             expected=('accept', 'upgrade', 'upgrade'),
             mustCodes=['unsettled_result'],
             tags=['scale_extra', 'result_assertion', 'unsettled_result']),
        dict(suffix='actor-pronoun', kind='pronoun_actor',
             text=core_text.replace(actor_name, '他', 1),
             bindings=actor_pronoun_bindings(core_bindings, actor_name, actor),
             label='attempt', exprIssues=[],
             expected=('upgrade', 'accept', 'upgrade'),
             mustCodes=['reference_requires_review'],
             tags=['scale_extra', 'pronoun_ellipsis']),
    ]


def actor_pronoun_bindings(bindings, actor_name, actor):
    rows = copy.deepcopy(bindings)
    for row in rows:
        if row['entityId'] == actor and row['surface'] == actor_name:
            row['surface'] = '他'
            row['basis'] = 'pronoun'
            row['occurrence'] = 0
    return rows


def build(output=ROOT):
    apply_entities()
    output.mkdir(parents=True, exist_ok=True)
    (output / 'worlds.json').write_text(
        json.dumps(WORLDS, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    all_groups = GROUPS + NEW_GROUPS
    scenarios, samples, failures = [], [], []
    for case in case_rows(all_groups):
        group = case['group']
        sample_id = group['id'] + ':' + case['suffix']
        try:
            built = build_audits(sample_id, case, case['world'], group['actor'])
        except ValueError as exc:
            raise SystemExit('locate failure at ' + sample_id + ': ' + str(exc))
        m1 = checkers.validate_role_audit(built['text'], built['steps'], built['roleAudit'],
                                          case['world'], group['actor'])
        m2 = checkers.validate_expression_audit(built['text'], built['steps'],
                                                built['expressionAudit'])
        combined = checkers.combine(m1, m2)
        expected = case['expected']
        if (m1.decision, m2.decision, combined.decision) != expected:
            failures.append({'sampleId': sample_id, 'expected': expected,
                             'got': [m1.decision, m2.decision, combined.decision],
                             'codes': sorted({x['code'] for x in combined.issues})})
        codes = {x['code'] for x in combined.issues}
        missing = set(case['mustCodes']) - codes
        if missing:
            failures.append({'sampleId': sample_id, 'missingCodes': sorted(missing),
                             'got': sorted(codes)})
        samples.append({
            'schema': 'jity-d02-checker-scale-sample-v1',
            'sampleId': sample_id,
            'scenarioGroup': group['id'],
            'split': group['split'],
            'source': 'assistant_authored_scale_v2',
            'worldId': group['world'],
            'actorId': group['actor'],
            'text': built['text'],
            'steps': built['steps'],
            'roleAudit': built['roleAudit'],
            'expressionAudit': built['expressionAudit'],
            'expected': {'m1': expected[0], 'm2': expected[1], 'combined': expected[2]},
            'tags': case['tags'] + [case['kind']],
            'annotationStatus': 'assistant_draft_pending_human',
            'reviewNote': 'scale-v2 助手草稿；不是人审、不是训练集、不是封存成绩。',
        })
        if case['suffix'] == 'clean':
            scenarios.append({'scenarioGroup': group['id'], 'split': group['split'],
                              'worldId': group['world'], 'actorId': group['actor'],
                              'prompt': group['prompt']})
    for group in all_groups:
        for case in extra_cases(group):
            sample_id = group['id'] + ':' + case['suffix']
            built = build_audits(sample_id, case, WORLDS[group['world']], group['actor'])
            m1 = checkers.validate_role_audit(built['text'], built['steps'],
                                              built['roleAudit'], WORLDS[group['world']],
                                              group['actor'])
            m2 = checkers.validate_expression_audit(built['text'], built['steps'],
                                                    built['expressionAudit'])
            combined = checkers.combine(m1, m2)
            expected = case['expected']
            if (m1.decision, m2.decision, combined.decision) != expected:
                failures.append({'sampleId': sample_id, 'expected': expected,
                                 'got': [m1.decision, m2.decision, combined.decision]})
            samples.append({
                'schema': 'jity-d02-checker-scale-sample-v1',
                'sampleId': sample_id, 'scenarioGroup': group['id'],
                'split': group['split'], 'source': 'assistant_authored_scale_v2',
                'worldId': group['world'], 'actorId': group['actor'],
                'text': built['text'], 'steps': built['steps'],
                'roleAudit': built['roleAudit'],
                'expressionAudit': built['expressionAudit'],
                'expected': {'m1': expected[0], 'm2': expected[1], 'combined': expected[2]},
                'tags': case['tags'] + [case['kind']],
                'annotationStatus': 'assistant_draft_pending_human',
                'reviewNote': 'scale-v2 助手草稿；生成的作用域变体，不是人审。',
            })
    if failures:
        raise SystemExit('scale-v2 expectation failures:\n' +
                         json.dumps(failures, ensure_ascii=False, indent=2))
    (output / 'scenarios.json').write_text(json.dumps(scenarios, ensure_ascii=False, indent=2) + '\n')
    (output / 'samples.jsonl').write_text(
        ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in samples))
    counts = {split: sum(1 for row in samples if row['split'] == split) for split in SPLITS}
    groups_by_split = {split: sorted({row['scenarioGroup'] for row in samples if row['split'] == split})
                       for split in SPLITS}
    manifest = {
        'schema': 'jity-d02-checker-scale-manifest-v1',
        'batch': 'scale-v2',
        'annotationStatus': 'assistant_draft_pending_human',
        'humanReview': {'status': 'pending', 'reviewedSamples': 0},
        'trainingAuthorized': False,
        'sealedUse': 'unopened_pending_final_freeze',
        'groupCount': len(all_groups),
        'sampleCount': len(samples),
        'sourceCounts': {'assistant_authored_scale_v2': len(samples)},
        'splitCounts': counts,
        'splits': groups_by_split,
        'basePilot': {'path': 'pilot-v1/manifest.json',
                      'sha256': hashlib.sha256((ROOT.parent / 'pilot-v1' / 'manifest.json').read_bytes()).hexdigest()},
        'ruleSource': {'path': 'pilot-v1/ANNOTATION.md',
                       'sha256': hashlib.sha256((ROOT.parent / 'pilot-v1' / 'ANNOTATION.md').read_bytes()).hexdigest()},
        'sha256': {name: hashlib.sha256((output / name).read_bytes()).hexdigest()
                   for name in ('worlds.json', 'scenarios.json', 'samples.jsonl')},
    }
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(build(args.output), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
