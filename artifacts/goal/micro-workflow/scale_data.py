# -*- coding: utf-8 -*-
"""Template-gold training rows for the fixed BERT candidate-pointer curve."""
import importlib.util
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('v2', HERE / 'micro_generative_v2.py')
v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)
from hand_train import FROST  # noqa: E402

v2.WORLDS['frost'] = FROST

TIMES = ['15:45前', '停赛前', '天亮前', '午夜前', '广播结束前', '十分钟内']
CONFS = ['确认', '核实', '问清', '检查', '核对']
ACTS = ['交给', '戴好', '守住', '退回', '塞进', '换上', '登记', '打开']
TOPICS = ['红蓝双方的位置', '小桥是否可通行', '伤员能不能走', '旗台还有几个人', '备用弹匣在哪里']
PROMISES = ['停火后带回空弹匣', '把路线告诉小队', '守住东回廊', '把担架留在医护区']
ENVS = ['检修盖已经打开', '楼梯口已经让出', '安全绳已经固定', '锁扣已经释放']
DECISIONS = ['从地下通道走', '从玻璃门退回顶层', '留在东回廊', '走西回廊']
CAUSES = ['弹匣脱手', '相机没电', '红方占用频段', '护栏松动', '担架不够']


def pick(rng, seq, exclude=()):
    pool = [value for value in seq if value not in exclude]
    return rng.choice(pool)


def make_condition(rng, world_name, index):
    world = v2.WORLDS[world_name]
    uni = v2.universe(world)
    chars = [ident for ident, row in uni.items() if row['type'] == 'char']
    items = [ident for ident, row in uni.items() if row['type'] == 'item']
    locs = [ident for ident, row in uni.items() if row['type'] == 'loc']
    actor = rng.choice(chars)
    target = pick(rng, chars, (actor,))
    item = rng.choice(items)
    loc, loc2 = rng.sample(locs, 2) if len(locs) >= 2 else (locs[0], locs[0])
    kind = rng.choice(['time', 'info', 'location', 'decision', 'promise', 'environment', 'transfer',
                       'composite', 'negation'])
    time = rng.choice(TIMES)
    conf = rng.choice(CONFS)
    act = rng.choice(ACTS)
    topic = rng.choice(TOPICS)
    promise = rng.choice(PROMISES)
    env = rng.choice(ENVS)
    decision = rng.choice(DECISIONS)
    name = lambda ident: uni[ident]['name']
    if kind == 'time':
        gold = {'time': time, 'item': item, 'conf': conf, 'act': act}
        text = f'在{time}{act}{name(item)}，再{conf}{name(item)}'
    elif kind == 'info':
        gold = {'target': target, 'conf': conf, 'info': topic}
        text = f'向{name(target)}{conf}{topic}'
    elif kind == 'location':
        gold = {'loc': loc, 'target': target, 'act': '守住', 'time': time}
        text = f'在{name(loc)}守住{time}，别让{name(target)}靠近'
    elif kind == 'decision':
        gold = {'decision': decision}
        text = f'在{name(loc)}和{name(loc2)}之间选择{decision}'
    elif kind == 'promise':
        gold = {'target': target, 'promise': promise}
        text = f'让{name(target)}答应{promise}'
    elif kind == 'environment':
        gold = {'loc': loc, 'conf': '确认', 'env': env}
        text = f'确认{name(loc)}的{env}'
    elif kind == 'transfer':
        gold = {'item': item, 'target': target, 'act': '交给'}
        text = f'把{name(item)}交给{name(target)}'
    elif kind == 'composite':
        gold = {'time': time, 'target': target, 'conf': '确认', 'info': topic, 'promise': promise}
        text = f'在{time}向{name(target)}确认{topic}，并答应{promise}'
    else:
        gold = {'neg': '1', 'item': item, 'act': act}
        text = f'没有{conf}{name(item)}之前不要{act}'
    candidates = v2.build_candidates(world, gold, text, f'{index}-{kind}')
    return {'id': f'sc{index}', 'kind': 'conditions', 'world': world_name, 'type': kind, 'actor': actor,
            'text': text + f'；角色={actor}', 'gold': gold, 'candidates': candidates,
            'prefix': 'COND|'}


def make_event(rng, world_name, index):
    world = v2.WORLDS[world_name]
    uni = v2.universe(world)
    chars = [ident for ident, row in uni.items() if row['type'] == 'char']
    items = [ident for ident, row in uni.items() if row['type'] == 'item']
    locs = [ident for ident, row in uni.items() if row['type'] == 'loc']
    actor = rng.choice(chars)
    target = pick(rng, chars, (actor,))
    item = rng.choice(items)
    loc = rng.choice(locs)
    topic = rng.choice(TOPICS)
    promise = rng.choice(PROMISES)
    env = rng.choice(ENVS)
    decision = rng.choice(DECISIONS)
    cause = rng.choice(CAUSES)
    act = rng.choice(ACTS)
    name = lambda ident: uni[ident]['name']
    kind = rng.choice(['transfer', 'dialogue', 'environment', 'promise', 'decision', 'failure',
                       'multi', 'refusal', 'move'])
    if kind == 'transfer':
        gold = {'result': 'completed', 'item': item, 'dest': loc}
        text = f'{name(actor)}把{name(item)}放进{name(loc)}'
    elif kind == 'dialogue':
        gold = {'result': 'completed', 'target': target, 'info': topic}
        text = f'{name(actor)}告诉{name(target)}{topic}'
    elif kind == 'environment':
        gold = {'result': 'completed', 'item': item, 'env': env}
        text = f'{name(actor)}{act}{name(item)}，{env}'
    elif kind == 'promise':
        gold = {'result': 'completed', 'target': target, 'promise': promise}
        text = f'{name(actor)}答应{name(target)}{promise}'
    elif kind == 'decision':
        gold = {'result': 'completed', 'decision': decision}
        text = f'{name(actor)}决定{decision}'
    elif kind == 'failure':
        gold = {'result': 'failed', 'item': item, 'cause': cause}
        text = f'{name(actor)}想{act}{name(item)}，但{cause}'
    elif kind == 'multi':
        gold = {'result': 'partial', 'item': item, 'target': target, 'cause': cause}
        text = f'{name(actor)}先{act}{name(item)}，再找{name(target)}，但{cause}'
    elif kind == 'refusal':
        gold = {'result': 'blocked', 'target': target, 'item': item, 'cause': cause}
        text = f'{name(actor)}拒绝{name(target)}借{name(item)}的请求，因为{cause}'
    else:
        gold = {'result': 'completed', 'item': item, 'dest': loc, 'info': '物品留在原地'}
        text = f'{name(actor)}{act}{name(loc)}，把{name(item)}留在原地'
    candidates = v2.build_candidates(world, gold, text, f'{index}-{kind}')
    return {'id': f'se{index}', 'kind': 'events', 'world': world_name, 'type': kind, 'actor': actor,
            'text': text + f'；角色={actor}', 'gold': gold, 'candidates': candidates,
            'prefix': f'EV|actor={actor}|'}


def make_rows(count, seed=20261126):
    rng = random.Random(seed)
    rows = []
    for index in range(count):
        world_name = rng.choice(['dragon', 'frost'])
        if rng.random() < 0.45:
            rows.append(make_condition(rng, world_name, index))
        else:
            rows.append(make_event(rng, world_name, index))
    return rows


def finalize(rows):
    for row in rows:
        row['input'] = row['text'] + '；候选=' + '；'.join(
            f'{i + 1}:{v2.universe(v2.WORLDS[row["world"]])[ident]["name"]}={ident}'
            for i, ident in enumerate(row['candidates']))
    return rows
