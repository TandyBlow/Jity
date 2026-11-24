# -*- coding: utf-8 -*-
"""Rule-based fact settlement: targets, destination, negation."""
NEG = ['没有', '没', '未', '谁也没']
TRANSFER = ['递给', '交给', '给', '问', '找到', '理']
BLOCK = ['拦', '挡住', '被顶住', '没能', '没进', '没推开', '没有推开']


def settle(action, dice, present, current, candidates):
    negated = any(k in action for k in NEG) and '没有停留' not in action
    targets = [name for name in present if name in action]
    if not targets:
        if '他们' in action or '两个人' in action or '在场的' in action:
            targets = list(present)
        elif '第二个人' in action and len(present) >= 2:
            targets = [present[1]]
        elif ('他' in action or '她' in action) and len(present) == 1:
            targets = list(present)
    if negated and any(k in action for k in TRANSFER):
        targets = []
    place = None
    for cand in candidates:
        if cand in action:
            place = cand
    if '离开' in action and '去' in action:
        after = action.split('去', 1)[1]
        for cand in candidates:
            if cand in after:
                place = cand
    if any(k in dice for k in BLOCK):
        place = current
    elif negated and place:
        place = current
    if '没有动' in action:
        place = current
    return {'targets': targets, 'destination': place or current, 'negated': negated}
