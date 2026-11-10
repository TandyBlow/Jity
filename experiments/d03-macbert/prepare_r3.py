"""Authored relational contrasts; all paraphrases and contrasts share one group.

Labels and explanations stay outside model input. Only R2 TRAIN is replayed.
"""
import hashlib
import json
from pathlib import Path
import random

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'docs/research/d03-macbert/r3'
# category, group, number of total characters, two context/action/gold contrasts.
# A=actor; B,C=other characters. Three authored expressions per contrast.
FAMILIES=[
('ownership','camera',3,[
 ('乙正拿着从甲那里借来的相机拍照，相机所有权仍归甲。', ['从乙手中夺走正在使用的相机。','伸手把乙握着的那台相机抢走。','将正在乙手里的相机强行取走。'],'甲乙'),
 ('乙正用自己的相机拍照，甲的相机另锁在柜里。', ['从乙手中夺走正在使用的相机。','伸手把乙握着的那台相机抢走。','将正在乙手里的相机强行取走。'],'乙')]),
('ownership','tablet',3,[
 ('甲正用乙借给他的平板记账，平板归乙所有。', ['拿走甲正在用的平板。','将甲手中记账的平板收走。','把甲正操作的那台平板取走。'],'甲乙'),
 ('甲使用的是丙借给他的平板，乙与这台平板无关。', ['拿走甲正在用的平板。','将甲手中记账的平板收走。','把甲正操作的那台平板取走。'],'甲')]),
('ownership','violin',2,[
 ('丙手里拿着借自甲的小提琴，琴仍属于甲。', ['割断手中小提琴的琴弦。','用刀切开这把琴上的弦。','将自己拿着的小提琴弦剪断。'],'甲'),
 ('丙手里拿着自己的小提琴；甲的琴完好地留在甲家。', ['割断手中小提琴的琴弦。','用刀切开这把琴上的弦。','将自己拿着的小提琴弦剪断。'],'')]),
('ownership','toolbox',3,[
 ('工具箱由甲与乙共同所有，两人各有一半份额，箱子放在地上。', ['将地上的工具箱砸坏。','砸毁面前的那只工具箱。','把这只放在地上的工具箱破坏掉。'],'甲乙'),
 ('工具箱仅归甲所有；乙只是曾经看过它，没有占有或使用。', ['将地上的工具箱砸坏。','砸毁面前的那只工具箱。','把这只放在地上的工具箱破坏掉。'],'甲')]),
('ownership','umbrella_loan',2,[
 ('甲将自己的折叠伞交给丙暂时保管，没有赠送；甲本人不在伞下。', ['将保管的折叠伞扔进垃圾压缩机。','把手中这把伞投入正在压缩垃圾的机器。','丢弃这把代为保存的伞，让机器将其压坏。'],'甲'),
 ('甲已将折叠伞完整赠送给丙，当前所有权归丙；甲本人不在伞下。', ['将保管的折叠伞扔进垃圾压缩机。','把手中这把伞投入正在压缩垃圾的机器。','丢弃这把保存着的伞，让机器将其压坏。'],'')]),
('ownership','seedbox',3,[
 ('盒中的种子全部归乙所有。甲只是指过盒子，从未持有、使用或共有它。', ['把盒子里的种子倒入炉火。','将盒内保存的种子全部烧掉。','把这一盒种子投入火中。'],'乙'),
 ('盒中的种子全部归甲所有。乙只是指过盒子，从未持有、使用或共有它。', ['把盒子里的种子倒入炉火。','将盒内保存的种子全部烧掉。','把这一盒种子投入火中。'],'甲')]),
('reference','latter',3,[
 ('记录依次列出甲、乙，两人站在空地上。“后者”指这份记录中的第二个人。', ['拍一下后者的肩。','伸手轻拍记录中后一个人的肩膀。','在后者肩头轻轻拍了一下。'],'乙'),
 ('记录依次列出乙、甲，两人站在空地上。“后者”指这份记录中的第二个人。', ['拍一下后者的肩。','伸手轻拍记录中后一个人的肩膀。','在后者肩头轻轻拍了一下。'],'甲')]),
('reference','red_sleeve',3,[
 ('甲穿红袖上衣，乙穿蓝袖上衣，两人分别站着。', ['拉住穿红袖上衣那个人的手腕。','握住红袖者的腕部。','伸手扣住红色衣袖露出的手腕。'],'甲'),
 ('甲穿蓝袖上衣，乙穿红袖上衣，两人分别站着。', ['拉住穿红袖上衣那个人的手腕。','握住红袖者的腕部。','伸手扣住红色衣袖露出的手腕。'],'乙')]),
('reference','speaker',3,[
 ('刚才提出“请递给我”的是甲，乙一直没有开口；现在两人都伸着手。', ['把水杯交给刚才提出请求的人。','将杯子递到刚刚开口那个人手中。','把这杯水送到先前请求者的手里。'],'甲'),
 ('刚才提出“请递给我”的是乙，甲一直没有开口；现在两人都伸着手。', ['把水杯交给刚才提出请求的人。','将杯子递到刚刚开口那个人手中。','把这杯水送到先前请求者的手里。'],'乙')]),
('reference','left_person',3,[
 ('按丙当前视角，甲在左边，乙在右边；两人各自独立站着。', ['将一枚木牌放到左边那个人的掌心。','递给左手边的人一枚木牌。','把木牌交到自己左侧之人手上。'],'甲'),
 ('按丙当前视角，乙在左边，甲在右边；两人各自独立站着。', ['将一枚木牌放到左边那个人的掌心。','递给左手边的人一枚木牌。','把木牌交到自己左侧之人手上。'],'乙')]),
('reference','own_ref',2,[
 ('只有丙和甲在场。这里“自己”指采取本次动作的丙，不指甲。', ['揉一揉自己的手腕。','只按摩自己的腕部。','用另一只手搓揉自己的手腕。'],''),
 ('只有丙和甲在场。这里“对方”指甲，不指采取动作的丙。', ['揉一揉对方的手腕。','只按摩对方的腕部。','用手搓揉对方的手腕。'],'甲')]),
('reference','hat_owner',3,[
 ('这里只有甲戴帽子，乙没有戴帽子。帽子属于甲本人。', ['取下戴帽者头上的帽子。','伸手摘走戴帽子那个人的帽子。','把唯一戴帽之人的帽子摘下来。'],'甲'),
 ('这里只有乙戴帽子，甲没有戴帽子。帽子属于乙本人。', ['取下戴帽者头上的帽子。','伸手摘走戴帽子那个人的帽子。','把唯一戴帽之人的帽子摘下来。'],'乙')]),
('condition','green',2,[
 ('指示灯现在亮绿灯；甲站在装有扶手的平台上。丙控制只作用于该平台的按钮。', ['仅在绿灯时按下按钮使平台移动，否则保持不动。','看灯操作：绿灯就启动甲所在平台，不是绿灯便不做动作。','若此刻是绿灯，就推动甲所在的平台；否则原地等待。'],'甲'),
 ('指示灯现在亮红灯而非绿灯；甲站在装有扶手的平台上。丙控制只作用于该平台的按钮。', ['仅在绿灯时按下按钮使平台移动，否则保持不动。','看灯操作：绿灯就启动甲所在平台，不是绿灯便不做动作。','若此刻是绿灯，就推动甲所在的平台；否则原地等待。'],'')]),
('condition','permission',2,[
 ('甲刚明确表示允许丙取走自己手中的书，没有撤回许可。', ['甲同意才取走他手里的书；不同意就不伸手。','如果已得到甲的允许，就拿走甲的书，否则维持原样。','只在甲已经许可的情况下收走他的书，未许可则不动。'],'甲'),
 ('甲刚明确拒绝丙取走自己手中的书，此前也从未允许。', ['甲同意才取走他手里的书；不同意就不伸手。','如果已得到甲的允许，就拿走甲的书，否则维持原样。','只在甲已经许可的情况下收走他的书，未许可则不动。'],'')]),
('condition','dry',3,[
 ('甲的雨衣是湿的，乙的雨衣是干的；两件雨衣都各归穿着者本人。', ['只给雨衣湿着的人披上毛巾。','给穿湿雨衣的人加一条毛巾，干雨衣的不碰。','逐个查看雨衣，仅为衣服仍湿的那个人搭上毛巾。'],'甲'),
 ('甲的雨衣是干的，乙的雨衣是湿的；两件雨衣都各归穿着者本人。', ['只给雨衣湿着的人披上毛巾。','给穿湿雨衣的人加一条毛巾，干雨衣的不碰。','逐个查看雨衣，仅为衣服仍湿的那个人搭上毛巾。'],'乙')]),
('condition','not_blue',3,[
 ('甲戴蓝色手环，乙戴白色手环；没有其他手环。', ['把贴纸贴在没有戴蓝色手环的人的袖子上。','只给非蓝色手环者的衣袖贴一枚标记。','略过蓝手环，把贴纸贴给另一人的袖口。'],'乙'),
 ('甲戴白色手环，乙戴蓝色手环；没有其他手环。', ['把贴纸贴在没有戴蓝色手环的人的袖子上。','只给非蓝色手环者的衣袖贴一枚标记。','略过蓝手环，把贴纸贴给另一人的袖口。'],'甲')]),
('condition','empty_hands',3,[
 ('甲与乙双手都是空的，两人都没有托举物品。', ['给每个双手空着的人递一块木板。','把木板逐一交给手里没有东西的人。','只向空着双手的人递木板，每人一块。'],'甲乙'),
 ('甲与乙都用双手托着满筐水果，手里都没有空位。', ['给每个双手空着的人递一块木板。','把木板逐一交给手里没有东西的人。','只向空着双手的人递木板，每人一块。'],'')]),
('condition','cancelled',2,[
 ('甲独自站着，丙可以伸手触及甲的肩膀。', ['轻轻按住甲的肩膀。','把手搭在甲的肩上并轻按。','伸手触碰甲的肩头。'],'甲'),
 ('甲独自站着，丙可以伸手触及甲的肩膀。', ['没有按住甲的肩膀，只把自己的手放回口袋。','取消触碰甲的打算，双手保持在自己身侧。','并未向甲伸手，而是安静地整理自己的袖子。'],'')]),
('isolation','music',3,[
 ('甲的耳机接通了丙的播放器，乙的耳机没有连接；耳机声音不外放。', ['开启播放器播放音乐。','启动这台播放器，让音频输出。','按播放键，把音乐送入已连接的耳机。'],'甲'),
 ('乙的耳机接通了丙的播放器，甲的耳机没有连接；耳机声音不外放。', ['开启播放器播放音乐。','启动这台播放器，让音频输出。','按播放键，把音乐送入已连接的耳机。'],'乙')]),
('isolation','glass',2,[
 ('甲站在丙的灯前，隔板是透明玻璃，光能穿过玻璃到达甲。', ['打开朝向隔板的亮灯。','点亮面朝玻璃隔板的灯。','开启这盏灯，让灯光照向隔板。'],'甲'),
 ('甲站在丙的灯前，隔板是完全不透光的板，甲在板后；热和声音也不会传到甲那里。', ['打开朝向隔板的亮灯。','点亮面朝隔板的灯。','开启这盏灯，让灯光照向隔板。'],'')]),
('isolation','fan',3,[
 ('风扇的出风管只通向甲的工位。乙的工位被完整隔墙隔开，收不到风。风扇没有可闻噪音。', ['启动风扇送风。','打开风扇，让空气流入出风管。','使风扇开始沿管道吹风。'],'甲'),
 ('风扇的出风管只通向乙的工位。甲的工位被完整隔墙隔开，收不到风。风扇没有可闻噪音。', ['启动风扇送风。','打开风扇，让空气流入出风管。','使风扇开始沿管道吹风。'],'乙')]),
('isolation','heated_pad',2,[
 ('甲坐在垫子上，垫子的供电线接在丙面前的插座；这个插座仅给这张垫子供电。', ['断开眼前插座的电源。','把这个插座的供电关闭。','切断面前插座所连接的电路。'],'甲'),
 ('甲坐在使用独立电池的垫子上，与丙面前的空插座没有连接。', ['断开眼前插座的电源。','把这个插座的供电关闭。','切断面前插座所连接的电路。'],'')]),
('isolation','scent',3,[
 ('甲和乙在与香薰器连通的房间里，空气能从香薰器流向两人，没有其他气味屏障。', ['开启香薰器释放气味。','启动这台香薰装置散发香气。','让香薰器开始向空气中送出气味。'],'甲乙'),
 ('甲和乙分别在完全密封的隔离舱中，香薰器在舱外；舱外气味、声音和热量均不会进入。', ['开启香薰器释放气味。','启动这台香薰装置散发香气。','让香薰器开始向空气中送出气味。'],'')]),
('isolation','rope_barrier',3,[
 ('甲的货箱与丙的牵引绳连接，乙的货箱没有连接；各箱独立，不会碰撞，货箱各归其主人。', ['拉动这根牵引绳移动所连接的货箱。','向后牵拉绳索，使连着绳子的箱子挪动。','拽动牵引绳带动与它相接的箱子。'],'甲'),
 ('乙的货箱与丙的牵引绳连接，甲的货箱没有连接；各箱独立，不会碰撞，货箱各归其主人。', ['拉动这根牵引绳移动所连接的货箱。','向后牵拉绳索，使连着绳子的箱子挪动。','拽动牵引绳带动与它相接的箱子。'],'乙')]),
]

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    split_of={}
    for category in sorted({f[0] for f in FAMILIES}):
        families=sorted([f for f in FAMILIES if f[0]==category],key=lambda f:hashlib.sha256(('r3:'+f[1]).encode()).hexdigest())
        for i,f in enumerate(families):
            split_of[f[1]]='train' if i<4 else 'development' if i==4 else 'test'
    rows=[]
    name_pool=['江遥','魏宁','程禾','齐川','赵澄','孟秋','徐白','梁青','秦月','陶安','韩松','杜雪']
    for fi,(category,key,count,contrasts) in enumerate(FAMILIES):
        rng=random.Random(303000+fi)
        chosen=rng.sample(name_pool,count)
        slots='丙甲乙'[:count]
        names=dict(zip(slots,chosen))
        ids=dict(zip(slots,rng.sample(['p13','p27','p46','p71','p88'],count)))
        def replace(s):
            for marker in slots:
                s=s.replace(marker,names[marker])
            return s
        roster=[{'id':ids[m],'name':names[m]} for m in slots]
        rng.shuffle(roster)
        acted=[ids[m] for m in slots[1:] if rng.random()<.5]
        for ci,(world,actions,gold) in enumerate(contrasts):
            for pi,action in enumerate(actions):
                rows.append({'sceneId':f'r3:{key}:{ci}:{pi}', 'sourceGroup':'r3:'+key,
                    'split':split_of[key],'category':category,'characterCount':count,
                    'contrastIndex':ci,'paraphraseIndex':pi,'origin':'r3_new_assistant_authored',
                    'input':{'actorId':ids['丙'],'action':names['丙']+'采取行动：'+replace(action),
                             'world':replace(world),'characters':roster,'alreadyActedIds':acted},
                    'targetIds':[ids[m] for m in gold],
                    'annotationStatus':'assistant_authored_unreviewed'})
    old_path=ROOT/'docs/research/d03-macbert/r2/scenes.jsonl'
    old_manifest=json.loads((old_path.parent/'data-manifest.json').read_text())
    assert hashlib.sha256(old_path.read_bytes()).hexdigest()==old_manifest['datasetSha256']
    # Replay only the explicitly frozen R2 TRAIN split. No previous held-out labels.
    replay=[json.loads(line) for line in old_path.read_text().splitlines() if json.loads(line)['split']=='train']
    for row in replay:
        row['category']='r2_replay'
        row['origin']='r2_train_replay'
    rows+=replay
    path=OUT/'scenes.jsonl'
    path.write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in rows))
    manifest={'datasetSha256':hashlib.sha256(path.read_bytes()).hexdigest(),
              'humanReviewedCount':0,'author':'assistant','r2DatasetSha256':old_manifest['datasetSha256'],
              'r2TrainReplayScenes':len(replay),'newScenes':144,
              'groups':{s:sorted({r['sourceGroup'] for r in rows if r['split']==s}) for s in ['train','development','test']},
              'counts':{s:{'scenes':sum(r['split']==s for r in rows),
                           'pairs':sum(r['characterCount'] for r in rows if r['split']==s)} for s in ['train','development','test']},
              'limitations':['Shared author and contrast/paraphrase construction, not independent natural-game validation.',
                             'Only four new held-out source groups; paraphrases do not multiply independent evidence.',
                             'Owned property and current borrower/use are both targets when both are affected.',
                             'Known unmet condition means no physical action; unknown future dice never appear.']}
    (OUT/'data-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    print(json.dumps(manifest,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
