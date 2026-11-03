"""Keep complete JSON facts in atomic <=512-token BERT windows.

Every original leaf, empty container and list index remains in the sidecar.
Facts are not selected by label, target score, distance or semantic rules.
"""
from __future__ import annotations

import copy
from pilot_codec import FIELDS
from lab import canonical_bytes


def flatten(value, path=()):
    if isinstance(value, dict) and value:
        return [row for key in sorted(value) for row in flatten(value[key], path+(key,))]
    if isinstance(value, list) and value:
        return [row for index, item in enumerate(value) for row in flatten(item, path+(index,))]
    return [{'path': list(path), 'value': copy.deepcopy(value)}]


def restore(facts):
    if not facts: raise ValueError('missing facts')
    if len(facts)==1 and facts[0]['path']==[]: return copy.deepcopy(facts[0]['value'])
    missing = object()
    root = [] if type(facts[0]['path'][0]) is int else {}
    seen = set()
    for fact in facts:
        path = fact['path']; key = tuple(path)
        if not path or key in seen or any(key[:i] in seen for i in range(1,len(key))): raise ValueError('duplicate/root/overlapping fact')
        seen.add(key); node = root
        for i, part in enumerate(path):
            if type(part) is int:
                if not isinstance(node,list) or part<0: raise ValueError('invalid list path')
                while len(node)<=part: node.append(missing)
            elif isinstance(part,str):
                if not isinstance(node,dict): raise ValueError('invalid object path')
            else: raise ValueError('invalid path type')
            if i==len(path)-1:
                if (isinstance(node,dict) and part in node) or (isinstance(node,list) and node[part] is not missing): raise ValueError('overlapping fact')
                node[part]=copy.deepcopy(fact['value'])
            else:
                expected=[] if type(path[i+1]) is int else {}
                current=node.get(part,missing) if isinstance(node,dict) else node[part]
                if current is missing: node[part]=expected
                elif not isinstance(current,type(expected)): raise ValueError('conflicting container types')
                node=node[part]
    def check(node):
        if node is missing: raise ValueError('missing list coverage')
        if isinstance(node,(dict,list)):
            for v in node.values() if isinstance(node,dict) else node: check(v)
    check(root)
    return root


def fact_text(fact):
    path=[FIELDS.get(p,p) if isinstance(p,str) else p for p in fact['path']]
    return canonical_bytes([path,fact['value']]).decode('utf-8')+'\n'


def make_windows(value, tokenizer, prefix, limit=512, *, with_spans=False, batch_tokenize=False):
    facts=flatten(value)
    if canonical_bytes(restore(facts))!=canonical_bytes(value): raise ValueError('fact round trip mismatch')
    if batch_tokenize:
        encoded=tokenizer([prefix]+[fact_text(f) for f in facts],add_special_tokens=False,
                          padding=False,truncation=False)['input_ids']
        if len(encoded)!=len(facts)+1:raise ValueError('tokenizer batch coverage mismatch')
        prefix_ids=encoded[0];parts=encoded[1:]
    else:
        prefix_ids=tokenizer.encode(prefix,add_special_tokens=False);parts=None
    budget=limit-len(prefix_ids)-tokenizer.num_special_tokens_to_add(pair=True)
    if budget<=0: raise ValueError('prefix exceeds token budget')
    windows=[]; ids=[]; indices=[];spans=[]
    def emit():
        if not indices: return
        full=tokenizer.build_inputs_with_special_tokens(prefix_ids,ids)
        types=tokenizer.create_token_type_ids_from_sequences(prefix_ids,ids)
        if len(full)>limit or len(types)!=len(full): raise ValueError('invalid window budget/types')
        windows.append({'inputIds':full,'tokenTypeIds':types,'factIds':indices.copy(),
                        'payloadTokens':len(ids),'totalTokens':len(full)})
        if with_spans:
            offset=len(prefix_ids)+2
            if full[:offset]!=[tokenizer.cls_token_id]+prefix_ids+[tokenizer.sep_token_id] or full[offset:-1]!=ids or full[-1]!=tokenizer.sep_token_id:
                raise ValueError('unsupported BERT pair layout')
            windows[-1]['factSpans']=[{'factIndex':i,'start':offset+a,'end':offset+b} for i,a,b in spans]
    for index,fact in enumerate(facts):
        part=parts[index] if parts is not None else tokenizer.encode(fact_text(fact),add_special_tokens=False)
        if with_spans and not part:raise ValueError('empty fact tokens')
        if len(part)>budget: raise ValueError(f'atomic fact {index} exceeds window budget; no truncation allowed')
        if len(ids)+len(part)>budget: emit();ids=[];indices=[];spans=[]
        if with_spans:spans.append((index,len(ids),len(ids)+len(part)))
        ids.extend(part);indices.append(index)
    emit()
    if [i for w in windows for i in w['factIds']]!=list(range(len(facts))): raise ValueError('incomplete fact coverage')
    return facts,windows
