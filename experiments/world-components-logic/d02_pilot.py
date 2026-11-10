"""Build and validate the D02 checker pilot; annotations are assistant drafts.

The pilot is deliberately small and scenario-grouped.  It is not a training
set, not a sealed test, and not evidence of model quality.  Every group keeps
its clean, actor-swap, result-assertion and two difficult variants together so
a later split cannot leak a rename or role swap into another split.
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

ROOT = HERE / 'data' / 'd02-checkers' / 'pilot-v1'
SPLITS = ('train', 'development', 'calibration', 'sealed')


def ent(kind, name, aliases=()):
    return {'type': kind, 'name': name, 'aliases': list(aliases)}


WORLDS = {
    'harbor-v1': {'entities': {
        'lin': ent('character', '林澈', ['小澈']),
        'zhou': ent('character', '周岚'),
        'xin': ent('character', '辛序'),
        'key': ent('item', '铜钥匙', ['钥匙']),
        'door': ent('item', '铁门'),
        'warehouse': ent('location', '仓库'),
        'lamp': ent('item', '提灯'),
        'crate': ent('item', '木箱'),
        'dock': ent('location', '码头'),
        'tape': ent('item', '胶带'),
    }},
    'archive-v1': {'entities': {
        'yu': ent('character', '余荞'),
        'zheng': ent('character', '郑栖'),
        'badge': ent('item', '借阅牌'),
        'cabinet': ent('item', '档案柜'),
        'room': ent('location', '阅览室'),
        'ledger': ent('item', '登记簿'),
        'stamp': ent('item', '印章'),
        'stamp_old': ent('item', '旧印章', ['旧印']),
        'desk': ent('item', '阅览桌'),
        'envelope': ent('item', '信封'),
    }},
    'workshop-v1': {'entities': {
        'tang': ent('character', '唐霁'),
        'lian': ent('character', '连笙'),
        'bowl': ent('item', '染料碗'),
        'rod': ent('item', '搅拌棒'),
        'bench': ent('location', '配色台'),
        'rack': ent('location', '晾架'),
        'cloth': ent('item', '样布'),
        'paper': ent('item', '吸水纸'),
    }},
    'signal-v1': {'entities': {
        'wei': ent('character', '周苇'),
        'xie': ent('character', '谢迟'),
        'radio': ent('item', '信号机'),
        'cable': ent('item', '备用线'),
        'tower': ent('location', '信号塔'),
        'room': ent('location', '值守室'),
        'gate': ent('item', '道口闸门', ['闸门']),
        'pin': ent('item', '锁紧销'),
        'battery': ent('item', '电池'),
    }},
}


def B(surface, roles, entity=None, basis='name', status='bound', diagnostic=(), occurrence=0,
      candidates=None):
    return {'surface': surface, 'roles': roles, 'entityId': entity, 'basis': basis,
            'status': status, 'diagnostic': list(diagnostic),
            'occurrence': occurrence, 'candidates': list(candidates or [])}


def E(code, surface, scope, blocking=True):
    return {'code': code, 'surface': surface, 'scope': scope, 'blocking': blocking}


GROUPS = [
    dict(id='harbor-gate', world='harbor-v1', actor='lin', other='zhou',
         split='train', prompt='林澈想打开仓库旁的铁门，取出里面受潮的提灯。',
         core=('林澈用铜钥匙开铁门。', [B('林澈', ['subject'], 'lin'),
                                        B('铜钥匙', ['tool'], 'key'),
                                        B('铁门', ['object'], 'door')]),
         swap=('周岚用铜钥匙开铁门。', [B('周岚', ['subject'], 'zhou'),
                                        B('铜钥匙', ['tool'], 'key'),
                                        B('铁门', ['object'], 'door')]),
         result=('林澈用铜钥匙开锁，铁门已经打开了。', [B('林澈', ['subject'], 'lin'),
                                                       B('铜钥匙', ['tool'], 'key'),
                                                       B('铁门', ['object'], 'door')],
                 [E('unsettled_result', '铁门已经打开了', 'main')]),
         special=('林澈拿起钥匙。', [B('林澈', ['subject'], 'lin'),
                                     B('钥匙', ['object'], 'key', basis='alias')],
                  'attempt', [], ['alias_requires_review']),
         role=('林澈把铜钥匙交给周岚。', [B('林澈', ['subject'], 'lin'),
                                           B('铜钥匙', ['object'], 'key'),
                                           B('周岚', ['recipient'], 'zhou')],
               'attempt', [], [])),
    dict(id='harbor-crate', world='harbor-v1', actor='lin', other='zhou',
         split='train', prompt='林澈和周岚要把受潮的木箱搬到码头。',
         core=('林澈和周岚一起抬起木箱。', [B('林澈', ['subject'], 'lin'),
                                             B('周岚', ['subject'], 'zhou'),
                                             B('木箱', ['object'], 'crate')]),
         swap=('周岚独自抬起木箱。', [B('周岚', ['subject'], 'zhou'),
                                       B('木箱', ['object'], 'crate')]),
         result=('林澈抬起木箱，已经到了码头。', [B('林澈', ['subject'], 'lin'),
                                                       B('木箱', ['object'], 'crate'),
                                                       B('码头', ['destination'], 'dock')],
                 [E('unsettled_result', '已经到了码头', 'main')]),
         special=('林澈与周岚共同抬起木箱。', [B('林澈', ['subject'], 'lin'),
                                               B('周岚', ['subject'], 'zhou'),
                                               B('木箱', ['object'], 'crate')],
                  'attempt', [], []),
         role=('林澈请周岚帮忙抬木箱。', [B('林澈', ['subject'], 'lin'),
                                         B('周岚', ['recipient'], 'zhou'),
                                         B('木箱', ['object'], 'crate')],
               'attempt', [], [])),
    dict(id='harbor-lamp', world='harbor-v1', actor='lin', other='zhou',
         split='train', prompt='林澈要先把提灯的裂缝用胶带缠好。',
         core=('林澈用胶带缠好提灯。', [B('林澈', ['subject'], 'lin'),
                                       B('胶带', ['tool'], 'tape'),
                                       B('提灯', ['object'], 'lamp')]),
         swap=('周岚用胶带缠好提灯。', [B('周岚', ['subject'], 'zhou'),
                                       B('胶带', ['tool'], 'tape'),
                                       B('提灯', ['object'], 'lamp')]),
         result=('林澈用胶带缠好提灯，提灯已经亮了。', [B('林澈', ['subject'], 'lin'),
                                                       B('胶带', ['tool'], 'tape'),
                                                       B('提灯', ['object'], 'lamp')],
                 [E('unsettled_result', '提灯已经亮了', 'main')]),
         special=('林澈用黑胶带缠提灯。', [B('林澈', ['subject'], 'lin'),
                                          B('黑胶带', ['tool'], status='unknown_entity'),
                                          B('提灯', ['object'], 'lamp')],
                  'attempt', [], ['unresolved_role_tool']),
         role=('林澈把提灯放到码头。', [B('林澈', ['subject'], 'lin'),
                                       B('提灯', ['object'], 'lamp'),
                                       B('码头', ['destination'], 'dock')],
               'attempt', [], [])),
    dict(id='harbor-wait', world='harbor-v1', actor='lin', other='zhou',
         split='train', prompt='林澈需要在仓库里等搬运的人回来。',
         core=('林澈检查铁门。', [B('林澈', ['subject'], 'lin'),
                                   B('铁门', ['object'], 'door')]),
         swap=('周岚检查铁门。', [B('周岚', ['subject'], 'zhou'),
                                   B('铁门', ['object'], 'door')]),
         result=('林澈检查铁门，铁门已经锁好了。', [B('林澈', ['subject'], 'lin'),
                                                   B('铁门', ['object'], 'door')],
                 [E('unsettled_result', '铁门已经锁好了', 'main')]),
         special=('林澈在仓库等待。', [B('林澈', ['subject'], 'lin'),
                                       B('仓库', [], 'warehouse',
                                         diagnostic=['static_location'])],
                  'attempt', [], ['diagnostic_role_requires_review']),
         role=('拿起提灯。', [B('提灯', ['object'], 'lamp')],
               'attempt', [], ['unresolved_role_subject'],
               {'implicit': True, 'roleOverride': {
                   's1': {'subject': {'status': 'insufficient', 'mentionIds': []}}}})),
    dict(id='harbor-key', world='harbor-v1', actor='lin', other='zhou',
         split='train', prompt='林澈要把铜钥匙交给周岚，再取回提灯。',
         core=('林澈把铜钥匙交给周岚。', [B('林澈', ['subject'], 'lin'),
                                           B('铜钥匙', ['object'], 'key'),
                                           B('周岚', ['recipient'], 'zhou')]),
         swap=('周岚把铜钥匙交给林澈。', [B('周岚', ['subject'], 'zhou'),
                                           B('铜钥匙', ['object'], 'key'),
                                           B('林澈', ['recipient'], 'lin')]),
         result=('林澈把铜钥匙交给周岚，事情已经办妥了。', [B('林澈', ['subject'], 'lin'),
                                                           B('铜钥匙', ['object'], 'key'),
                                                           B('周岚', ['recipient'], 'zhou')],
                 [E('unsettled_result', '事情已经办妥了', 'main')]),
         special=('他把铜钥匙交给林澈。', [B('他', ['subject'], 'zhou', basis='pronoun'),
                                           B('铜钥匙', ['object'], 'key'),
                                           B('林澈', ['recipient'], 'lin')],
                  'attempt', [], ['reference_requires_review']),
         role=('林澈从周岚那里取铜钥匙。', [B('林澈', ['subject'], 'lin'),
                                             B('周岚', [], 'zhou', diagnostic=['source']),
                                             B('铜钥匙', ['object'], 'key')],
               'attempt', [], ['diagnostic_role_requires_review'])),
    dict(id='archive-badge', world='archive-v1', actor='yu', other='zheng',
         split='train', prompt='余荞要把借阅牌递给郑栖登记。',
         core=('余荞把借阅牌递给郑栖。', [B('余荞', ['subject'], 'yu'),
                                           B('借阅牌', ['object'], 'badge'),
                                           B('郑栖', ['recipient'], 'zheng')]),
         swap=('郑栖把借阅牌递给余荞。', [B('郑栖', ['subject'], 'zheng'),
                                           B('借阅牌', ['object'], 'badge'),
                                           B('余荞', ['recipient'], 'yu')]),
         result=('余荞把借阅牌递给郑栖，事情已经办妥了。', [B('余荞', ['subject'], 'yu'),
                                                           B('借阅牌', ['object'], 'badge'),
                                                           B('郑栖', ['recipient'], 'zheng')],
                 [E('unsettled_result', '事情已经办妥了', 'main')]),
         special=('她把借阅牌递给郑栖。', [B('她', ['subject'], 'yu', basis='pronoun'),
                                           B('借阅牌', ['object'], 'badge'),
                                           B('郑栖', ['recipient'], 'zheng')],
                  'attempt', [], ['reference_requires_review']),
         role=('余荞从郑栖那里取借阅牌。', [B('余荞', ['subject'], 'yu'),
                                             B('郑栖', [], 'zheng', diagnostic=['source']),
                                             B('借阅牌', ['object'], 'badge')],
               'attempt', [], ['diagnostic_role_requires_review'])),
    dict(id='archive-ledger', world='archive-v1', actor='yu', other='zheng',
         split='development', prompt='余荞要用印章在登记簿上留下借阅记录。',
         core=('余荞用印章在登记簿上盖章。', [B('余荞', ['subject'], 'yu'),
                                             B('印章', ['tool'], 'stamp'),
                                             B('登记簿', ['object'], 'ledger')]),
         swap=('郑栖用印章在登记簿上盖章。', [B('郑栖', ['subject'], 'zheng'),
                                             B('印章', ['tool'], 'stamp'),
                                             B('登记簿', ['object'], 'ledger')]),
         result=('余荞用印章在登记簿上盖章，登记簿已经盖好了。', [B('余荞', ['subject'], 'yu'),
                                                                 B('印章', ['tool'], 'stamp'),
                                                                 B('登记簿', ['object'], 'ledger')],
                 [E('unsettled_result', '登记簿已经盖好了', 'main')]),
         special=('如果印章清楚，余荞就在登记簿上盖章。', [B('印章', ['tool'], 'stamp'),
                                                           B('余荞', ['subject'], 'yu'),
                                                           B('登记簿', ['object'], 'ledger')],
                  'attempt', [E('condition_scope', '印章清楚', 'condition', False)], []),
         role=('余荞把登记簿放进档案柜。', [B('余荞', ['subject'], 'yu'),
                                           B('登记簿', ['object'], 'ledger'),
                                           B('档案柜', ['destination'], 'cabinet')],
               'attempt', [], [])),
    dict(id='archive-cabinet', world='archive-v1', actor='yu', other='zheng',
         split='development', prompt='余荞要把登记簿收进档案柜。',
         core=('余荞把登记簿放进档案柜。', [B('余荞', ['subject'], 'yu'),
                                           B('登记簿', ['object'], 'ledger'),
                                           B('档案柜', ['destination'], 'cabinet')]),
         swap=('郑栖把登记簿放进档案柜。', [B('郑栖', ['subject'], 'zheng'),
                                           B('登记簿', ['object'], 'ledger'),
                                           B('档案柜', ['destination'], 'cabinet')]),
         result=('余荞把登记簿放进档案柜，档案柜已经关上了。', [B('余荞', ['subject'], 'yu'),
                                                               B('登记簿', ['object'], 'ledger'),
                                                               B('档案柜', ['destination'], 'cabinet')],
                 [E('unsettled_result', '档案柜已经关上了', 'main')]),
         special=('余荞拿起它。', [B('余荞', ['subject'], 'yu'),
                                     B('它', ['object'], status='ambiguous', basis='pronoun',
                                       candidates=['stamp', 'stamp_old'])],
                  'attempt', [], ['unresolved_role_object']),
         role=('余荞在阅览室等待。', [B('余荞', ['subject'], 'yu'),
                                     B('阅览室', [], 'room', diagnostic=['static_location'])],
               'attempt', [], ['diagnostic_role_requires_review'])),
    dict(id='archive-quote', world='archive-v1', actor='yu', other='zheng',
         split='train', prompt='余荞把借阅牌装进信封，并隔门向郑栖喊话。',
         core=('余荞把借阅牌放进信封。', [B('余荞', ['subject'], 'yu'),
                                         B('借阅牌', ['object'], 'badge'),
                                         B('信封', ['destination'], 'envelope')]),
         swap=('郑栖把借阅牌放进信封。', [B('郑栖', ['subject'], 'zheng'),
                                         B('借阅牌', ['object'], 'badge'),
                                         B('信封', ['destination'], 'envelope')]),
         result=('余荞把借阅牌放进信封，信封已经封好了。', [B('余荞', ['subject'], 'yu'),
                                                           B('借阅牌', ['object'], 'badge'),
                                                           B('信封', ['destination'], 'envelope')],
                 [E('unsettled_result', '信封已经封好了', 'main')]),
         special=('余荞喊道：“我已经拿到借阅牌了！”', [B('余荞', ['subject'], 'yu'),
                                                       B('借阅牌', ['object'], 'badge')],
                  'attempt', [E('success_word_in_quote', '我已经拿到借阅牌了', 'quote', False)], []),
         role=('余荞把借阅牌交给郑栖。', [B('余荞', ['subject'], 'yu'),
                                         B('借阅牌', ['object'], 'badge'),
                                         B('郑栖', ['recipient'], 'zheng')],
               'attempt', [], [])),
    dict(id='archive-ambig', world='archive-v1', actor='yu', other='zheng',
         split='calibration', prompt='余荞要把印章放回阅览桌。',
         core=('余荞把印章放回阅览桌。', [B('余荞', ['subject'], 'yu'),
                                         B('印章', ['object'], 'stamp'),
                                         B('阅览桌', ['destination'], 'desk')]),
         swap=('郑栖把印章放回阅览桌。', [B('郑栖', ['subject'], 'zheng'),
                                         B('印章', ['object'], 'stamp'),
                                         B('阅览桌', ['destination'], 'desk')]),
         result=('余荞把印章放回阅览桌，印章已经不见了。', [B('余荞', ['subject'], 'yu'),
                                                           B('印章', ['object'], 'stamp'),
                                                           B('阅览桌', ['destination'], 'desk')],
                 [E('unsettled_result', '印章已经不见了', 'main')]),
         special=('余荞拿起它。', [B('余荞', ['subject'], 'yu'),
                                     B('它', ['object'], status='ambiguous', basis='pronoun',
                                       candidates=['stamp', 'stamp_old'])],
                  'attempt', [], ['unresolved_role_object']),
         role=('余荞从郑栖那里取印章。', [B('余荞', ['subject'], 'yu'),
                                           B('郑栖', [], 'zheng', diagnostic=['source']),
                                           B('印章', ['object'], 'stamp')],
               'attempt', [], ['diagnostic_role_requires_review'])),
    dict(id='workshop-bowl', world='workshop-v1', actor='tang', other='lian',
         split='train', prompt='唐霁要把染料碗端到晾架。',
         core=('唐霁把染料碗端到晾架。', [B('唐霁', ['subject'], 'tang'),
                                         B('染料碗', ['object'], 'bowl'),
                                         B('晾架', ['destination'], 'rack')]),
         swap=('连笙把染料碗端到晾架。', [B('连笙', ['subject'], 'lian'),
                                         B('染料碗', ['object'], 'bowl'),
                                         B('晾架', ['destination'], 'rack')]),
         result=('唐霁把染料碗端到晾架，染料碗已经放稳了。', [B('唐霁', ['subject'], 'tang'),
                                                             B('染料碗', ['object'], 'bowl'),
                                                             B('晾架', ['destination'], 'rack')],
                 [E('unsettled_result', '染料碗已经放稳了', 'main')]),
         special=('她端起染料碗。', [B('她', ['subject'], 'lian', basis='pronoun'),
                                     B('染料碗', ['object'], 'bowl')],
                  'attempt', [], ['reference_requires_review']),
         role=('唐霁把染料碗递给连笙。', [B('唐霁', ['subject'], 'tang'),
                                         B('染料碗', ['object'], 'bowl'),
                                         B('连笙', ['recipient'], 'lian')],
               'attempt', [], [])),
    dict(id='workshop-rod', world='workshop-v1', actor='tang', other='lian',
         split='train', prompt='唐霁要先用搅拌棒把染料搅匀。',
         core=('唐霁用搅拌棒搅动染料碗。', [B('唐霁', ['subject'], 'tang'),
                                           B('搅拌棒', ['tool'], 'rod'),
                                           B('染料碗', ['object'], 'bowl')]),
         swap=('连笙用搅拌棒搅动染料碗。', [B('连笙', ['subject'], 'lian'),
                                           B('搅拌棒', ['tool'], 'rod'),
                                           B('染料碗', ['object'], 'bowl')]),
         result=('唐霁用搅拌棒搅动染料碗，染料已经调好了。', [B('唐霁', ['subject'], 'tang'),
                                                             B('搅拌棒', ['tool'], 'rod'),
                                                             B('染料碗', ['object'], 'bowl')],
                 [E('unsettled_result', '染料已经调好了', 'main')]),
         special=('唐霁拿起搅拌棒。\n唐霁用搅拌棒搅动染料碗。', [B('唐霁', ['subject'], 'tang'),
                                                                 B('搅拌棒', ['object'], 'rod'),
                                                                 B('唐霁', ['subject'], 'tang', occurrence=1),
                                                                 B('搅拌棒', ['tool'], 'rod', occurrence=1),
                                                                 B('染料碗', ['object'], 'bowl')],
                  'attempt', [], []),
         role=('唐霁把搅拌棒放到配色台。', [B('唐霁', ['subject'], 'tang'),
                                           B('搅拌棒', ['object'], 'rod'),
                                           B('配色台', ['destination'], 'bench')],
               'attempt', [], [])),
    dict(id='workshop-cloth', world='workshop-v1', actor='tang', other='lian',
         split='train', prompt='唐霁要用吸水纸把样布上的水吸掉。',
         core=('唐霁用吸水纸压住样布。', [B('唐霁', ['subject'], 'tang'),
                                         B('吸水纸', ['tool'], 'paper'),
                                         B('样布', ['object'], 'cloth')]),
         swap=('连笙用吸水纸压住样布。', [B('连笙', ['subject'], 'lian'),
                                         B('吸水纸', ['tool'], 'paper'),
                                         B('样布', ['object'], 'cloth')]),
         result=('唐霁用吸水纸压住样布，样布已经干了。', [B('唐霁', ['subject'], 'tang'),
                                                         B('吸水纸', ['tool'], 'paper'),
                                                         B('样布', ['object'], 'cloth')],
                 [E('unsettled_result', '样布已经干了', 'main')]),
         special=('唐霁没有碰样布。', [B('唐霁', ['subject'], 'tang'),
                                       B('样布', ['object'], 'cloth')],
                  'non_action', [E('negated_action', '没有碰', 'negation')], []),
         role=('唐霁把样布放到晾架。', [B('唐霁', ['subject'], 'tang'),
                                       B('样布', ['object'], 'cloth'),
                                       B('晾架', ['destination'], 'rack')],
               'attempt', [], [])),
    dict(id='workshop-newentity', world='workshop-v1', actor='tang', other='lian',
         split='sealed', prompt='唐霁发现搅拌棒松了，想找东西修好它。',
         core=('唐霁用搅拌棒搅动染料碗。', [B('唐霁', ['subject'], 'tang'),
                                           B('搅拌棒', ['tool'], 'rod'),
                                           B('染料碗', ['object'], 'bowl')]),
         swap=('连笙用搅拌棒搅动染料碗。', [B('连笙', ['subject'], 'lian'),
                                           B('搅拌棒', ['tool'], 'rod'),
                                           B('染料碗', ['object'], 'bowl')]),
         result=('唐霁用搅拌棒搅动染料碗，染料已经调好了。', [B('唐霁', ['subject'], 'tang'),
                                                             B('搅拌棒', ['tool'], 'rod'),
                                                             B('染料碗', ['object'], 'bowl')],
                 [E('unsettled_result', '染料已经调好了', 'main')]),
         special=('唐霁试着用铜齿轮修搅拌棒。', [B('唐霁', ['subject'], 'tang'),
                                               B('铜齿轮', ['tool'], status='unknown_entity'),
                                               B('搅拌棒', ['object'], 'rod')],
                  'attempt', [], ['unresolved_role_tool']),
         role=('唐霁试着用连笙撬动染料碗。', [B('唐霁', ['subject'], 'tang'),
                                         B('连笙', ['tool'], 'lian'),
                                         B('染料碗', ['object'], 'bowl')],
               'attempt', [], ['role_type_mismatch'])),
    dict(id='workshop-bench', world='workshop-v1', actor='tang', other='lian',
         split='sealed', prompt='唐霁要把染料碗稳稳放到配色台上。',
         core=('唐霁把染料碗放到配色台。', [B('唐霁', ['subject'], 'tang'),
                                           B('染料碗', ['object'], 'bowl'),
                                           B('配色台', ['destination'], 'bench')]),
         swap=('连笙把染料碗放到配色台。', [B('连笙', ['subject'], 'lian'),
                                           B('染料碗', ['object'], 'bowl'),
                                           B('配色台', ['destination'], 'bench')]),
         result=('唐霁把染料碗放到配色台，染料碗已经放稳了。', [B('唐霁', ['subject'], 'tang'),
                                                               B('染料碗', ['object'], 'bowl'),
                                                               B('配色台', ['destination'], 'bench')],
                 [E('unsettled_result', '染料碗已经放稳了', 'main')]),
         special=('如果放置成功，唐霁就把染料碗放到配色台。', [B('唐霁', ['subject'], 'tang'),
                                                               B('染料碗', ['object'], 'bowl'),
                                                               B('配色台', ['destination'], 'bench')],
                  'attempt', [E('success_word_in_condition', '成功', 'condition', False)], []),
         role=('唐霁和连笙一起抬起染料碗。', [B('唐霁', ['subject'], 'tang'),
                                               B('连笙', ['subject'], 'lian'),
                                               B('染料碗', ['object'], 'bowl')],
               'attempt', [], [])),
    dict(id='signal-radio', world='signal-v1', actor='wei', other='xie',
         split='train', prompt='周苇要用信号机向谢迟发出封路通知。',
         core=('周苇用信号机向谢迟发送通知。', [B('周苇', ['subject'], 'wei'),
                                               B('信号机', ['tool'], 'radio'),
                                               B('谢迟', ['recipient'], 'xie')]),
         swap=('谢迟用信号机向周苇发送通知。', [B('谢迟', ['subject'], 'xie'),
                                               B('信号机', ['tool'], 'radio'),
                                               B('周苇', ['recipient'], 'wei')]),
         result=('周苇用信号机向谢迟发送通知，通知已经发出了。', [B('周苇', ['subject'], 'wei'),
                                                                 B('信号机', ['tool'], 'radio'),
                                                                 B('谢迟', ['recipient'], 'xie')],
                 [E('unsettled_result', '通知已经发出了', 'main')]),
         special=('如果线路正常，周苇就用信号机发送通知。', [B('周苇', ['subject'], 'wei'),
                                                             B('信号机', ['tool'], 'radio')],
                  'attempt', [E('condition_scope', '线路正常', 'condition', False)], []),
         role=('周苇从谢迟那里取电池。', [B('周苇', ['subject'], 'wei'),
                                           B('谢迟', [], 'xie', diagnostic=['source']),
                                           B('电池', ['object'], 'battery')],
               'attempt', [], ['diagnostic_role_requires_review'])),
    dict(id='signal-cable', world='signal-v1', actor='wei', other='xie',
         split='train', prompt='周苇要把备用线插进信号机。',
         core=('周苇把备用线插进信号机。', [B('周苇', ['subject'], 'wei'),
                                           B('备用线', ['object'], 'cable'),
                                           B('信号机', ['destination'], 'radio')]),
         swap=('谢迟把备用线插进信号机。', [B('谢迟', ['subject'], 'xie'),
                                           B('备用线', ['object'], 'cable'),
                                           B('信号机', ['destination'], 'radio')]),
         result=('周苇把备用线插进信号机，信号机已经亮了。', [B('周苇', ['subject'], 'wei'),
                                                             B('备用线', ['object'], 'cable'),
                                                             B('信号机', ['destination'], 'radio')],
                 [E('unsettled_result', '信号机已经亮了', 'main')]),
         special=('他插好备用线。', [B('他', ['subject'], 'xie', basis='pronoun'),
                                     B('备用线', ['object'], 'cable')],
                  'attempt', [], ['reference_requires_review']),
         role=('周苇用备用线接通信号机。', [B('周苇', ['subject'], 'wei'),
                                           B('备用线', ['tool'], 'cable'),
                                           B('信号机', ['object'], 'radio')],
               'attempt', [], [])),
    dict(id='signal-gate', world='signal-v1', actor='wei', other='xie',
         split='calibration', prompt='周苇要用锁紧销把道口闸门固定住。',
         core=('周苇把锁紧销插进道口闸门。', [B('周苇', ['subject'], 'wei'),
                                               B('锁紧销', ['object'], 'pin'),
                                               B('道口闸门', ['destination'], 'gate')]),
         swap=('谢迟把锁紧销插进道口闸门。', [B('谢迟', ['subject'], 'xie'),
                                               B('锁紧销', ['object'], 'pin'),
                                               B('道口闸门', ['destination'], 'gate')]),
         result=('周苇把锁紧销插进道口闸门，闸门已经锁住了。', [B('周苇', ['subject'], 'wei'),
                                                               B('锁紧销', ['object'], 'pin'),
                                                               B('道口闸门', ['destination'], 'gate')],
                 [E('unsettled_result', '闸门已经锁住了', 'main')]),
         special=('假设道口闸门已经锁住，周苇就转身离开。', [B('周苇', ['subject'], 'wei'),
                                                         B('道口闸门', ['object'], 'gate')],
                  'attempt', [E('success_word_in_hypothesis', '道口闸门已经锁住', 'hypothesis', False)], []),
         role=('周苇在值守室等待。', [B('周苇', ['subject'], 'wei'),
                                       B('值守室', [], 'room', diagnostic=['static_location'])],
               'attempt', [], ['diagnostic_role_requires_review'])),
    dict(id='signal-background', world='signal-v1', actor='wei', other='xie',
         split='sealed', prompt='信号机此前已经修好，周苇现在检查备用线。',
         core=('周苇检查信号机。', [B('周苇', ['subject'], 'wei'),
                                     B('信号机', ['object'], 'radio')]),
         swap=('谢迟检查信号机。', [B('谢迟', ['subject'], 'xie'),
                                     B('信号机', ['object'], 'radio')]),
         result=('周苇检查信号机，信号机已经修好了。', [B('周苇', ['subject'], 'wei'),
                                                       B('信号机', ['object'], 'radio')],
                 [E('unsettled_result', '信号机已经修好了', 'main')]),
         special=('信号机已经修好，周苇检查备用线。', [B('周苇', ['subject'], 'wei'),
                                                       B('备用线', ['object'], 'cable'),
                                                       B('信号机', ['object'], 'radio')],
                  'attempt', [E('success_word_in_background', '信号机已经修好', 'background', False)], []),
         role=('周苇把备用线交给谢迟。', [B('周苇', ['subject'], 'wei'),
                                         B('备用线', ['object'], 'cable'),
                                         B('谢迟', ['recipient'], 'xie')],
               'attempt', [], [])),
    dict(id='signal-hope', world='signal-v1', actor='wei', other='xie',
         split='sealed', prompt='周苇希望信号机自己恢复，但还没有决定怎么做。',
         core=('周苇按下信号机。', [B('周苇', ['subject'], 'wei'),
                                     B('信号机', ['object'], 'radio')]),
         swap=('谢迟按下信号机。', [B('谢迟', ['subject'], 'xie'),
                                     B('信号机', ['object'], 'radio')]),
         result=('周苇按下信号机，信号已经发出了。', [B('周苇', ['subject'], 'wei'),
                                                     B('信号机', ['object'], 'radio')],
                 [E('unsettled_result', '信号已经发出了', 'main')]),
         special=('周苇希望信号机自己响起来。', [B('周苇', ['subject'], 'wei'),
                                               B('信号机', ['object'], 'radio')],
                  'non_action', [E('no_action_predicate', '希望', 'main')], []),
         role=('周苇用谢迟敲信号机。', [B('周苇', ['subject'], 'wei'),
                                       B('谢迟', ['tool'], 'xie'),
                                       B('信号机', ['object'], 'radio')],
               'attempt', [], ['role_type_mismatch'])),
]


def document(texts):
    text = '\n'.join(texts)
    steps, cursor = [], 0
    for index, value in enumerate(texts):
        steps.append({'stepId': 's' + str(index + 1), 'start': cursor,
                      'end': cursor + len(value)})
        cursor += len(value) + 1
    return text, steps


def locate(text, surface, occurrence=0):
    start = -1
    for _ in range(occurrence + 1):
        start = text.index(surface, start + 1)
    return start, start + len(surface)


def build_audits(sample_id, case, world, actor):
    texts = case['text'].split('\n')
    text, steps = document(texts)
    mentions = []
    for index, spec in enumerate(case['bindings']):
        start, end = locate(text, spec['surface'], spec['occurrence'])
        row = {'mentionId': 'm' + str(index + 1), 'start': start, 'end': end,
               'surface': spec['surface'], 'roles': list(spec['roles']),
               'diagnosticRoles': list(spec.get('diagnostic', [])),
               'status': spec['status'], 'bindingBasis': spec['basis'],
               'scope': 'main'}
        if spec['entityId'] is not None:
            row['entityId'] = spec['entityId']
        if spec['status'] == 'ambiguous':
            row['candidates'] = list(spec.get('candidates', []))
        mentions.append(row)
    role_audit = {'schema': checkers.ROLE_SCHEMA, 'textSha256': checkers.digest(text),
                  'steps': [], 'issues': []}
    for step in steps:
        own = [m for m in mentions if step['start'] <= m['start'] < step['end']]
        role_status = {}
        for role in checkers.ROLES:
            ids = [m['mentionId'] for m in own if role in m['roles']]
            if not ids:
                role_status[role] = {'status': 'absent', 'mentionIds': []}
                continue
            statuses = {m['status'] for m in own if m['mentionId'] in ids}
            status = ('ambiguous' if 'ambiguous' in statuses else
                      'unknown_entity' if 'unknown_entity' in statuses else
                      'insufficient' if 'insufficient' in statuses else 'bound')
            role_status[role] = {'status': status, 'mentionIds': ids}
        override = case.get('roleOverride', {}).get(step['stepId'])
        if override:
            role_status.update(override)
        role_audit['steps'].append({'stepId': step['stepId'], 'mentions': own,
                                    'roleStatus': role_status})
    if case.get('implicit'):
        role_audit['issues'].append({'code': 'implicit_subject',
                                     'message': 'subject omitted from the sentence',
                                     'blocking': True, 'stepId': 's1',
                                     'scope': 'main'})
    issues = []
    for spec in case.get('exprIssues', []):
        start, end = locate(text, spec['surface'])
        step_id = spec.get('stepId', steps[0]['stepId'])
        issues.append({'code': spec['code'], 'message': spec['code'],
                       'blocking': spec['blocking'], 'stepId': step_id,
                       'start': start, 'end': end, 'scope': spec['scope']})
    expr_audit = {'schema': checkers.EXPRESSION_SCHEMA,
                  'textSha256': checkers.digest(text),
                  'label': case.get('label', 'attempt'),
                  'issues': issues, 'abstain': case.get('abstain')}
    return {'text': text, 'steps': steps, 'roleAudit': role_audit,
            'expressionAudit': expr_audit}


M1_TARGET = {
    'actor_mismatch', 'alias_requires_review', 'reference_requires_review',
    'diagnostic_role_requires_review', 'role_type_mismatch',
    'unresolved_role_subject', 'unresolved_role_object', 'unresolved_role_tool',
    'unresolved_role_recipient', 'unresolved_role_destination',
}
M2_TARGET = {
    'unsettled_result', 'result_assertion', 'no_action_predicate',
    'negated_action', 'ambiguous_expression', 'uncertain',
}


def expected_for(codes, label):
    """Explicit target decisions implied by the authored issue codes."""
    codes = set(codes)
    m1 = 'upgrade' if codes & M1_TARGET else 'accept'
    m2 = 'upgrade' if codes & M2_TARGET or label in (
        'mixed', 'result_assertion', 'non_action', 'uncertain') else 'accept'
    combined = 'upgrade' if 'upgrade' in (m1, m2) else 'accept'
    return (m1, m2, combined)


SPECIAL_TAG_BY_CODE = {
    'alias_requires_review': 'alias',
    'reference_requires_review': 'pronoun_ellipsis',
    'unresolved_role_subject': 'implicit_subject',
    'diagnostic_role_requires_review': 'diagnostic_role_only',
    'role_type_mismatch': 'type_mismatch',
    'success_word_in_condition': 'condition_success',
    'success_word_in_quote': 'quote_success',
    'success_word_in_background': 'background_success',
    'success_word_in_hypothesis': 'hypothesis_success',
    'no_action_predicate': 'non_action',
    'negated_action': 'negation',
}


def tags_for(suffix, bindings, codes, label):
    tags = set()
    if suffix == 'special':
        if label in ('non_action', 'uncertain'):
            tags.add(label)
        for code in codes:
            if code in SPECIAL_TAG_BY_CODE:
                tags.add(SPECIAL_TAG_BY_CODE[code])
    for spec in bindings:
        if spec['status'] == 'unknown_entity':
            tags.add('unknown_entity')
        elif spec['status'] == 'ambiguous':
            tags.add('ambiguous_entity')
    if suffix == 'role':
        roles = {role for spec in bindings for role in spec['roles']}
        if 'recipient' in roles:
            tags.add('recipient')
        if 'destination' in roles:
            tags.add('destination')
        if 'tool' in roles:
            tags.add('tool_role')
        if any(spec.get('diagnostic') for spec in bindings):
            tags.add('diagnostic_role')
        if len([s for s in bindings if 'subject' in s['roles']]) > 1:
            tags.add('joint_subject')
        for code in codes:
            if code in ('implicit_subject', 'unresolved_role_subject'):
                tags.add('implicit_subject')
            if code == 'role_type_mismatch':
                tags.add('type_mismatch')
    return sorted(tags)


def case_rows(groups):
    for group in groups:
        world = WORLDS[group['world']]
        base = dict(group=group, world=world)
        clean_text, clean_bindings = group['core']
        swap_text, swap_bindings = group['swap']
        result_text, result_bindings, result_issues = group['result']
        special_text, special_bindings, special_label, special_issues, special_codes = group['special'][:5]
        special_extra = group['special'][5] if len(group['special']) > 5 else {}
        role_text, role_bindings, role_label, role_issues, role_codes = group['role'][:5]
        role_extra = group['role'][5] if len(group['role']) > 5 else {}
        rows = [
            dict(suffix='clean', kind='clean_attempt', text=clean_text,
                 bindings=clean_bindings, label='attempt', exprIssues=[],
                 expected=('accept', 'accept', 'accept'), mustCodes=[],
                 tags=['clean', 'explicit_name', 'no_result_claim']),
            dict(suffix='actor-swap', kind='actor_mismatch', text=swap_text,
                 bindings=swap_bindings, label='attempt', exprIssues=[],
                 expected=('upgrade', 'accept', 'upgrade'),
                 mustCodes=['actor_mismatch'], tags=['actor_mismatch', 'same_role']),
            dict(suffix='result', kind='unsettled_result', text=result_text,
                 bindings=result_bindings, label='mixed', exprIssues=result_issues,
                 expected=('accept', 'upgrade', 'upgrade'),
                 mustCodes=['unsettled_result'], tags=['result_assertion', 'late_error']),
            dict(suffix='special', kind='special', text=special_text,
                 bindings=special_bindings, label=special_label,
                 exprIssues=special_issues,
                 expected=expected_for(special_codes, special_label),
                 mustCodes=special_codes,
                 tags=['special'] + tags_for('special', special_bindings,
                                             special_codes + [i['code'] for i in special_issues],
                                             special_label),
                 **special_extra),
            dict(suffix='role', kind='role_or_scope', text=role_text,
                 bindings=role_bindings, label=role_label, exprIssues=role_issues,
                 expected=expected_for(role_codes, role_label),
                 mustCodes=role_codes,
                 tags=['role'] + tags_for('role', role_bindings,
                                             role_codes + [i['code'] for i in role_issues],
                                             role_label),
                 **role_extra),
        ]
        for row in rows:
            row.update(base)
            yield row


def decide(expected, got):
    return expected is None or expected == got


def build(output=ROOT, include_natural=True):
    output.mkdir(parents=True, exist_ok=True)
    (output / 'worlds.json').write_text(json.dumps(WORLDS, ensure_ascii=False,
                                                   indent=2, sort_keys=True) + '\n')
    scenarios = []
    samples = []
    failures = []
    for index, case in enumerate(case_rows(GROUPS)):
        sample_id = case['group']['id'] + ':' + case['suffix']
        try:
            built = build_audits(sample_id, case, case['world'], case['group']['actor'])
        except ValueError as exc:
            raise SystemExit('locate failure at ' + sample_id + ': ' + str(exc))
        m1 = checkers.validate_role_audit(built['text'], built['steps'],
                                          built['roleAudit'], case['world'],
                                          case['group']['actor'])
        m2 = checkers.validate_expression_audit(built['text'], built['steps'],
                                                built['expressionAudit'])
        combined = checkers.combine(m1, m2)
        expected = case['expected']
        if expected[0] is not None:
            if not decide(expected[0], m1.decision) or not decide(expected[1], m2.decision) \
                    or not decide(expected[2], combined.decision):
                failures.append({'sampleId': sample_id, 'expected': expected,
                                 'got': [m1.decision, m2.decision, combined.decision],
                                 'codes': sorted({x['code'] for x in combined.issues})})
        codes = {x['code'] for x in combined.issues}
        missing = set(case['mustCodes']) - codes
        if missing:
            failures.append({'sampleId': sample_id, 'missingCodes': sorted(missing),
                             'got': sorted(codes)})
        samples.append({
            'schema': 'jity-d02-checker-pilot-sample-v1',
            'sampleId': sample_id,
            'scenarioGroup': case['group']['id'],
            'split': case['group']['split'],
            'source': 'assistant_authored_targeted',
            'worldId': case['group']['world'],
            'actorId': case['group']['actor'],
            'text': built['text'],
            'steps': built['steps'],
            'roleAudit': built['roleAudit'],
            'expressionAudit': built['expressionAudit'],
            'expected': {'m1': expected[0], 'm2': expected[1],
                         'combined': expected[2]},
            'tags': sorted(set(case['tags'] + [case['kind']])),
            'annotationStatus': 'assistant_draft_pending_human',
            'reviewNote': '规则试验稿；不是人审金标准，不得用于训练或验收。',
        })
        if case['suffix'] == 'clean':
            scenarios.append({
                'scenarioGroup': case['group']['id'],
                'split': case['group']['split'],
                'worldId': case['group']['world'],
                'actorId': case['group']['actor'],
                'prompt': case['group']['prompt'],
            })
    if failures:
        raise SystemExit('pilot expectation failures:\n' + json.dumps(failures, ensure_ascii=False, indent=2))
    (output / 'scenarios.json').write_text(json.dumps(scenarios, ensure_ascii=False, indent=2) + '\n')
    (output / 'samples-targeted.jsonl').write_text(
        ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in samples))
    natural = []
    natural_path = output / 'api-natural.jsonl'
    if include_natural and natural_path.exists():
        natural = [json.loads(line) for line in natural_path.read_text().splitlines() if line.strip()]
        samples.extend(natural)
    (output / 'samples.jsonl').write_text(
        ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in samples))
    counts = {split: sum(1 for row in samples if row['split'] == split) for split in SPLITS}
    manifest = {
        'schema': 'jity-d02-checker-pilot-manifest-v1',
        'annotationStatus': 'assistant_draft_pending_human',
        'trainingAuthorized': False,
        'sealedUse': 'opened_by_pilot_api_proxy_not_reusable_as_sealed_test',
        'assistantReview': {
            'status': 'completed', 'reviewedSamples': len(samples),
            'humanReview': 'pending', 'artifact': 'REVIEW.md',
        },
        'humanReview': {
            'status': 'pending', 'packet': 'artifacts/world-components-logic/d02-checkers/pilot-review.html',
            'sop': 'HUMAN_REVIEW.md', 'reviewedSamples': 0,
        },
        'groupCount': len(GROUPS),
        'sampleCount': len(samples),
        'targetedCount': len(samples) - len(natural),
        'naturalApiCount': len(natural),
        'splitCounts': counts,
        'splits': {split: sorted({row['scenarioGroup'] for row in samples if row['split'] == split})
                   for split in SPLITS},
        'sha256': {name: hashlib.sha256((output / name).read_bytes()).hexdigest()
                   for name in ('worlds.json', 'scenarios.json', 'samples.jsonl')},
    }
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT)
    parser.add_argument('--no-natural', action='store_true')
    args = parser.parse_args()
    print(json.dumps(build(args.output, include_natural=not args.no_natural),
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
