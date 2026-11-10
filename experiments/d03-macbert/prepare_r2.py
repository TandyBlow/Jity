"""R2: 2-3 total characters, simple direct and one-hop ownership effects.

All six variants of a mechanism stay in one split. Assistant-authored labels,
not human-reviewed ground truth. No R1 rows or labels are read or changed.
"""
import hashlib
import json
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs/research/d03-macbert/r2'
# key, setup per other character, action aimed at a named recipient, self-only action.
# Ownership actions deliberately name the owner: this round excludes remote causal chains.
FAMILIES = [
    ('shoulder', '{name}站在空地上。', '轻拍{target}的肩膀。', '轻拍自己的肩膀。'),
    ('handshake', '{name}伸着手站在旁边。', '握住{target}的手。', '将自己的双手握在一起。'),
    ('forehead', '{name}坐在凳子上。', '用手背轻触{target}的额头。', '用手背轻触自己的额头。'),
    ('wrist', '{name}的手腕上没有物品。', '将一条丝带系在{target}的手腕上。', '将一条丝带系在自己的手腕上。'),
    ('comb', '{name}坐着梳理头发。', '用梳子梳理{target}的头发。', '用梳子梳理自己的头发。'),
    ('sleeve', '{name}穿着宽袖上衣。', '轻拉{target}的袖口。', '轻拉自己的袖口。'),
    ('water', '{name}站在桌边，双手空着。', '将一瓶饮用水递到{target}手中。', '自己喝掉一瓶饮用水。'),
    ('flashlight', '{name}站在旁边，手里没有工具。', '把一支手电筒放进{target}手里。', '把自己的手电筒放回自己口袋。'),
    ('badge', '{name}的衣襟上空着。', '把一枚徽章别在{target}的衣襟上。', '把一枚徽章别在自己的衣襟上。'),
    ('towel', '{name}刚洗完手，手是湿的。', '拿毛巾擦干{target}的手。', '拿自己的毛巾擦自己的手。'),
    ('glove', '{name}的双手没有戴手套。', '给{target}戴上一副手套。', '给自己戴上一副手套。'),
    ('back', '{name}站着不动，背部没有接触其他物体。', '用手掌轻推{target}的背部。', '把自己的双手放到自己背后。'),
    ('notebook', '{name}有一本属于自己的笔记本，放在身边。', '拿走{target}的笔记本。', '合上自己的笔记本。'),
    ('pencil', '{name}有一支属于自己的铅笔，放在身边。', '折断{target}的铅笔。', '把自己的铅笔收回自己笔袋。'),
    ('map', '{name}有一张属于自己的地图，放在身边。', '撕破{target}的地图。', '把自己的地图叠好收起来。'),
    ('ticket', '{name}有一张属于自己的车票，放在身边。', '剪碎{target}的车票。', '查看自己的车票后放回自己口袋。'),
    ('bottle', '{name}有一个属于自己的水壶，装着清水，放在身边。', '倒空{target}的水壶。', '拧紧自己的水壶盖。'),
    ('watch', '{name}有一只属于自己的手表，放在身边。', '取走{target}的手表。', '调整自己手表的表带。'),
    ('scarf', '{name}有一条属于自己的围巾，放在身边。', '用剪刀剪断{target}的围巾。', '把自己的围巾卷好。'),
    ('lunchbox', '{name}有一个属于自己的饭盒，装着食物，放在身边。', '拿走{target}饭盒中的食物。', '盖好自己的饭盒。'),
    ('drawing', '{name}有一张属于自己的画作，放在身边。', '用橡皮擦掉{target}画作上的图案。', '在自己的草稿纸上安静练字。'),
    ('racket', '{name}有一支属于自己的球拍，放在身边。', '剪断{target}球拍上的网线。', '把自己的球拍放回自己球袋。'),
    ('puzzle', '{name}有一幅属于自己的已拼好拼图，放在身边。', '打散{target}已拼好的拼图。', '把自己的拼图放进自己盒子。'),
    ('flowerpot', '{name}有一盆属于自己的盆栽，放在身边。', '给{target}的盆栽浇水。', '给自己的盆栽浇水。'),
]

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ordered = sorted(FAMILIES, key=lambda f: hashlib.sha256(('r2:'+f[0]).encode()).hexdigest())
    rows = []
    names = ['许晨', '叶青', '白露', '宋宁', '何川', '谢雨', '方明', '罗星']
    variants = [(2,'one',[1]), (2,'none',[]), (3,'first',[1]),
                (3,'second',[2]), (3,'both',[1,2]), (3,'none',[])]
    for rank, (key, setup, effect, empty) in enumerate(ordered):
        split = 'train' if rank < 16 else 'development' if rank < 20 else 'test'
        for v, (count, label, targets) in enumerate(variants):
            rng = random.Random(20261110+rank*100+v)
            chosen = rng.sample(names, count)
            ids = rng.sample(['p11','p28','p53','p76','p94'],count)
            world = ''.join(setup.format(name=name) for name in chosen[1:])
            world += '每个人的物品彼此独立；本次动作没有声音传播，也没有触碰或改变未指明的人及其物品。'
            action = ''.join(effect.format(target=chosen[t]) for t in targets) if targets else empty
            roster = [dict(id=i,name=n) for i,n in zip(ids,chosen)]
            rng.shuffle(roster)
            acted = [cid for cid in ids[1:] if rng.random()<.5]
            rows.append({
                'sceneId':f'r2:{key}:{count}:{label}', 'sourceGroup':'r2:'+key, 'split':split,
                'characterCount':count, 'variant':label,
                'input':{'actorId':ids[0], 'action':chosen[0]+'采取行动：'+action,
                         'world':world, 'characters':roster, 'alreadyActedIds':acted},
                'targetIds':[ids[t] for t in targets],
                'annotationStatus':'assistant_authored_unreviewed',
                'scope':'simplified_direct_or_explicit_ownership_effect',
            })
    path = OUT/'scenes.jsonl'
    path.write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in rows))
    manifest = {'datasetSha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                'author':'assistant','humanReviewedCount':0,'historicalDataImported':False,
                'groups':{s:sorted({r['sourceGroup'] for r in rows if r['split']==s})
                          for s in ['train','development','test']},
                'scenes':len(rows),'pairs':sum(r['characterCount'] for r in rows),
                'totalCharacters':[2,3], 'grouping':'all variants of a mechanism in one split',
                'limitations':['Shared templates across groups; held-out mechanisms are not independent natural-game validation.',
                               'Direct recipients and explicit ownership only; no remote or uncertain causal paths.',
                               'This is a new easier dataset, not a controlled comparison isolating character count.']}
    (OUT/'data-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    print(json.dumps(manifest,ensure_ascii=False,indent=2))

if __name__ == '__main__':
    main()
