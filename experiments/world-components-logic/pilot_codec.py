"""Reversible input serialization, with no semantic selection or truncation.

Short Chinese field names, shared exact strings and uniform-row tables reduce
repetition. Decode(pack(input)) must equal the entire original stage input.
All facts, IDs, ordering, booleans and missing-vs-null distinctions survive.
"""
from __future__ import annotations

from collections import Counter
import copy

FIELDS = {
    'world': '世界', 'time': '时间', 'places': '地点', 'items': '物品', 'characters': '人物',
    'id': '编号', 'name': '名称', 'parentId': '上级', 'position': '位置',
    'containerId': '容器', 'slot': '部位', 'appearance': '外貌', 'tasks': '任务',
    'text': '正文', 'status': '状态', 'personality': '个性', 'sanity': '理智',
    'actorId': '当前人物', 'protagonistId': '主角', 'advance': '本次输入',
    'inputText': '玩家原文', 'intentStatus': '输入状态', 'confirmedPrefix': '冻结前缀',
    'source': '冻结源', 'memberId': '成员', 'actionText': '行动原文',
    'candidateIds': '完整候选', 'alreadyActedIds': '已行动',
    'confirmedGroup': '已确认组', 'members': '成员行动', 'knownPriorJudgments': '过去判定',
    'admission': '准入', 'eligible': '有资格', 'admitted': '已准入',
    'previouslySkippedIds': '先前跳过', 'judgments': '实际判定',
    'sourceId': '来源', 'targetId': '目标', 'rollId': '骰点编号',
    'ruleVersion': '规则版本', 'value': '点数', 'threshold': '阈值', 'passed': '通过',
    'group': '闭组', 'closed': '已闭合', 'memberIds': '完整成员',
    'confirmedTargets': '已确认目标集', 'targetIds': '目标集',
}
INVERSE = {v: k for k, v in FIELDS.items()}


def pack(value):
    counts = Counter()
    def count(node):
        if isinstance(node, str): counts[node] += 1
        elif isinstance(node, list):
            for item in node: count(item)
        elif isinstance(node, dict):
            for item in node.values(): count(item)
    count(value)
    shared = sorted(s for s, n in counts.items() if n >= 2 and len(s) >= 12)
    refs = {s: i for i, s in enumerate(shared)}
    def encode(node):
        if isinstance(node, str) and node in refs: return {'同文': refs[node]}
        if isinstance(node, list):
            if len(node) >= 2 and all(isinstance(row, dict) for row in node) and all(set(row) == set(node[0]) for row in node):
                keys = sorted(node[0])
                return {'列': [FIELDS.get(k, k) for k in keys],
                        '行': [[encode(row[k]) for k in keys] for row in node]}
            return [encode(item) for item in node]
        if isinstance(node, dict):
            keys = [FIELDS.get(k, k) for k in node]
            if len(set(keys)) != len(keys) or {'同文', '列', '行'} & set(keys):
                raise ValueError('input key collides with serialization syntax')
            return {FIELDS.get(k, k): encode(v) for k, v in node.items()}
        return copy.deepcopy(node)
    result = {'格式': '无损表格1', '共用文本': shared, '资料': encode(value)}
    if unpack(result) != value:
        raise ValueError('input serialization is not lossless')
    return result


def unpack(packed):
    if set(packed) != {'格式', '共用文本', '资料'} or packed['格式'] != '无损表格1':
        raise ValueError('unsupported serialization')
    def decode(node):
        if isinstance(node, list): return [decode(item) for item in node]
        if isinstance(node, dict):
            if set(node) == {'同文'}:
                index = node['同文']
                if type(index) is not int or not 0 <= index < len(packed['共用文本']):
                    raise ValueError('invalid shared string reference')
                return packed['共用文本'][index]
            if set(node) == {'列', '行'}:
                keys = [INVERSE.get(k, k) for k in node['列']]
                if len(keys) != len(set(keys)) or any(len(row) != len(keys) for row in node['行']):
                    raise ValueError('invalid table coverage')
                return [{k: decode(v) for k, v in zip(keys, row)} for row in node['行']]
            return {INVERSE.get(k, k): decode(v) for k, v in node.items()}
        return copy.deepcopy(node)
    return decode(packed['资料'])


def readable(value):
    """Translate field names only; preserve all values, lists, order and nulls."""
    def convert(node,mapping):
        if isinstance(node,list):return [convert(x,mapping) for x in node]
        if isinstance(node,dict):
            names=[mapping.get(k,k) for k in node]
            if len(set(names))!=len(names):raise ValueError('readable field collision')
            return {mapping.get(k,k):convert(v,mapping) for k,v in node.items()}
        return copy.deepcopy(node)
    result=convert(value,FIELDS)
    if convert(result,INVERSE)!=value:raise ValueError('readable input cannot be restored')
    return result


def restore_readable(value):
    def convert(node):
        if isinstance(node,list):return [convert(x) for x in node]
        if isinstance(node,dict):
            names=[INVERSE.get(k,k) for k in node]
            if len(set(names))!=len(names):raise ValueError('readable field collision')
            return {INVERSE.get(k,k):convert(v) for k,v in node.items()}
        return copy.deepcopy(node)
    return convert(value)
