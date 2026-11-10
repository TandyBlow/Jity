"""New assistant-authored short scenes. No historical/B/C samples are imported.

Each row specifies a world, a consequential source action, a non-consequential
counterpart, and the explicitly authored target indices for the first action.
These are unreviewed hypotheses, not independent human ground truth.
"""
import hashlib
import json
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs/research/d03-macbert'
# Referents 甲乙丙 are replaced consistently by fresh names and shuffled IDs.
SCENES = [
('bridge', '甲和乙正在吊桥上，丙在远处山坡；吊桥仅靠眼前的绳索支撑。', '割断吊桥的支撑绳索。', '在不触碰绳索的情况下默数吊桥木板。', '甲乙'),
('watergate', '甲在下游河道修船，乙在下游浅滩取水，丙在高处封闭屋内；开闸的水会流过河道和浅滩。', '打开水库闸门放水。', '把手放进口袋，默想闸门的形状。', '甲乙'),
('ladder', '甲站在梯子顶端，乙扶着这架梯子的底部，丙在另一栋楼；梯子下面没有其他支撑。', '从侧面猛推这架梯子。', '在远处默读自己的笔记。', '甲乙'),
('cart', '甲坐在推车里，乙站在推车正前方狭窄轨道上，丙在护栏外；推车沿轨道只能直行。', '用力向前推动推车。', '轻轻整理自己的袖口，不触碰推车。', '甲乙'),
('shelf', '甲在书架下取书，乙在房间另一侧坚固隔墙后，丙在屋外；书架若倒下会压向甲。', '把书架向甲所在方向推倒。', '站着不动，在心里给书架编号。', '甲'),
('rope', '甲用安全绳悬在井中，乙在井外独立平台上，丙在隔壁屋内；这根绳子只连接甲。', '解开甲的安全绳固定扣。', '查看自己手表上的时间。', '甲'),
('ice', '甲站在薄冰中央，乙在岸上护栏后，丙在远处房里；脚边冰层与甲脚下相连。', '用铁锤猛烈砸击这片薄冰。', '把铁锤平放在岸边，不接触冰面。', '甲'),
('lift', '甲和丙在升降平台内，乙在独立楼梯间；眼前开关控制该平台升降。', '按下平台下降开关。', '在心中回忆开关说明，不碰设备。', '甲丙'),
('lamp', '甲在这盏灯下修钟，乙在同一盏灯下看图纸，丙在不透光的隔壁房间用另一盏灯。', '关闭甲和乙共用的灯。', '在灯旁闭上自己的眼睛，保持设备不动。', '甲乙'),
('vent', '甲和乙在密闭实验室，丙在室外；唯一通风口由眼前阀门控制。', '关闭实验室唯一的通风阀门。', '在纸上画一个阀门，不触碰真实设备。', '甲乙'),
('alarm', '甲在办公室，乙戴着完全隔音的耳罩，丙在走廊；警铃能被办公室和走廊的人听见，听不穿耳罩。', '按下警铃按钮。', '只在心里想象警铃声，保持安静。', '甲丙'),
('smoke', '甲在厨房，乙在与厨房连通的餐厅，丙在隔绝烟气的独立舱；风从厨房吹向餐厅。', '点燃会冒大量烟的湿柴。', '在不点火的情况下默数柴块。', '甲乙'),
('flood', '甲在地下仓库，乙在与仓库相通的低洼走廊，丙在楼上；水管破裂后水流向仓库和走廊。', '砸破正在供水的主管。', '把自己的帽子戴正，不接触水管。', '甲乙'),
('door', '甲正从门口通过，乙在门后紧贴门板，丙在远处庭院；门向乙所在一侧打开。', '猛地把门向内推开。', '站在门外默背号码，不发声也不碰门。', '甲乙'),
('heater', '甲在温室内照料植物，乙在同一温室休息，丙在独立冷库；锅炉只给温室供暖。', '切断温室锅炉的燃料供应。', '用铅笔在自己的本子上记下锅炉型号。', '甲乙'),
('curtain', '甲在屏幕后投影演讲，乙在观众席观看投影，丙在隔音室；拉开的窗帘会让阳光直照投影屏幕。', '拉开遮住阳光的窗帘。', '轻轻调整自己衣领，不遮挡屏幕。', '甲乙'),
('cup', '甲端着盛满热水的杯子，乙在桌子另一端，丙在门外；杯子与乙和丙没有接触。', '拍打甲端杯子的手腕。', '在自己的空杯子里放入一枚糖块，不碰他人。', '甲'),
('bag', '甲背着布包，乙手里拿着独立的篮子，丙在另一房间；只有甲的布包里装着目标钥匙。', '伸手拉开甲的布包，取出钥匙。', '把自己的空口袋翻出来。', '甲'),
('medicine', '甲正在等发起者递药，乙在远处房间，丙正独自读书；药物只交给甲。', '把一杯药递到甲手中。', '将自己的药瓶放回自己的抽屉，不给任何人。', '甲'),
('letter', '甲在桌边，乙在窗边，丙在室外；这封密信将当面只交给乙，其他人看不到内容。', '把密信交到乙手里。', '把未拆开的密信收回自己的口袋。', '乙'),
('coat', '甲站在雨里，乙在雨棚下，丙在封闭车内；发起者手里拿着自己的外套。', '把外套披到甲肩上。', '把外套叠好抱在自己怀里。', '甲'),
('coin', '甲和乙各有一个放在桌上的钱袋，丙的钱袋锁在柜中；两个桌上钱袋相互独立。', '从甲和乙的钱袋里各拿走一枚钱币。', '只数自己掌心的钱币，不接触别人的财物。', '甲乙'),
('seat', '甲坐在椅子上，乙站在窗边，丙坐在固定长凳上；这把椅子只承载甲。', '抽走甲身下的椅子。', '轻轻擦拭自己身边的空椅子，不制造声响。', '甲'),
('blanket', '甲与丙盖着同一条毯子休息，乙盖着另一条毯子；毯子之间没有连接。', '把甲和丙共用的毯子拉走。', '将自己的围巾整齐叠在自己膝上。', '甲丙'),
('request', '甲和乙面对发起者，能听清说话，丙在完全隔音的房间里；请求明确只指向甲。', '对甲说：“请帮我扶住这块木板。”', '在心里组织请求的措辞，没有开口或示意。', '甲乙'),
('warning', '甲在栈道，乙在栈道入口，丙在远处听不到声音；发起者的喊声能被甲和乙听到。', '大声喊：“栈道要塌了，快离开！”', '在心里想起栈道照片，没有发声。', '甲乙'),
('whisper', '甲贴近发起者耳边，乙与丙都在远处且听不到低语。', '贴着甲的耳朵低声告诉他门锁密码。', '默想门锁密码，嘴唇和身体保持不动。', '甲'),
('insult', '甲与乙都能听见发起者的正常说话声，丙在隔音舱里。', '当面对甲和乙说：“你们俩都在撒谎。”', '在心里怀疑甲和乙，没有表达出来。', '甲乙'),
('radio', '甲戴着接通频道的耳机，乙的接收器已关闭，丙的接收器也接通同一频道。', '通过无线电广播撤离通知。', '在断开话筒的情况下默读通知。', '甲丙'),
('sign', '甲与乙正看着电子告示牌，丙在背面且看不到；告示牌只显示视觉文字，没有声音。', '把告示牌文字改为“立刻停止作业”。', '在自己的遮蔽屏幕上编辑未发送的告示草稿。', '甲乙'),
('phone', '甲的手机已接通扬声器，乙在甲身边能听到，丙在远处；发起者正在通话另一端。', '通过电话宣布取消今天的约定。', '将自己的话筒静音后在心里组织措辞。', '甲乙'),
('gesture', '甲面对发起者，乙背对发起者，丙在不透明墙后；手势安静且没有接触。', '向甲挥手示意停下。', '双手不动，只在心里想象挥手。', '甲'),
('cable', '甲和乙分别使用连接同一电源线的电脑，丙的电脑使用独立电池。', '拔掉甲和乙电脑共用的电源线。', '把自己的未连接备用线卷好。', '甲乙'),
('valve', '甲穿着由软管供气的潜水服，乙使用独立气瓶，丙在岸上；此阀门只控制甲的供气软管。', '关闭甲的供气阀门。', '查看自己手腕上的深度表，不碰阀门。', '甲'),
('network', '甲和丙正在通过这个路由器传输资料，乙使用独立网络；拔插会中断当前传输。', '拔掉路由器电源。', '在自己的离线笔记里记录路由器颜色。', '甲丙'),
('magnet', '甲手持铁板，乙手持木板，丙站在磁场范围外；眼前电磁铁开启后会强烈吸引范围内的铁板。', '开启电磁铁。', '在电磁铁断电时观察自己的鞋带。', '甲'),
('train', '甲在列车车厢内，乙也在车厢内，丙在站台护栏后；发起者控制列车制动。', '突然拉下列车紧急制动杆。', '只在心里回忆制动操作，不触碰控制器。', '甲乙'),
('conveyor', '甲站在输送带末端接货，乙的手正放在输送带表面，丙在另一房间；开关启动这条输送带。', '启动输送带。', '在不触碰设备的情况下看自己的手表。', '甲乙'),
('lock', '甲在无其他出口的小屋内，乙在院子里，丙在另一个房间；屋门是甲唯一出口。', '从外面锁上小屋的门。', '把自己不用的备用锁放进袋子。', '甲'),
('trap', '甲的脚踩在踏板上，乙与丙在踏板范围外；拉杆会使踏板下陷。', '拉动控制踏板下陷的拉杆。', '背对拉杆，在心里计算步数。', '甲'),
('umbrella', '甲与乙站在同一把大伞下避雨，丙在车内；大伞由发起者握着。', '突然收起这把大伞。', '保持伞的位置不变，在心里哼歌。', '甲乙'),
('boat', '甲和丙坐在小船内，乙在稳固码头上；这根缆绳是小船唯一的系泊绳，河流正在推动船身。', '解开小船的系泊绳。', '轻轻整理自己的帽檐，不碰船或绳子。', '甲丙'),
('stretcher', '甲躺在担架上，乙抬着担架另一端，丙在另一房间；发起者握着担架这一端。', '突然松开担架把手。', '保持担架平稳，只在心里数数。', '甲乙'),
('tent', '甲与乙在帐篷里，丙在独立木屋里；这根主杆是帐篷唯一支撑。', '拔出帐篷主杆。', '在自己帐外的本子上安静画画。', '甲乙'),
('paint', '甲的衣服挂在眼前晾衣绳上，乙与丙的衣服在室内封闭柜中；发起者手里有一桶染料。', '将染料泼向甲挂着的衣服。', '把密封染料桶轻放在自己脚边。', '甲'),
('food', '甲和乙共用桌上的一锅汤，丙有另一份密封饭盒；发起者不享用这锅汤。', '往甲和乙的汤里倒入一整罐盐。', '将自己杯中的清水喝掉，不碰汤锅。', '甲乙'),
('parcel', '甲委托发起者保管自己的包裹，乙与丙的物品存放在别处；包裹只有甲所有。', '撕开甲的包裹封条。', '整理自己空纸袋的折角。', '甲'),
('shield', '甲站在发起者举着的挡板后，乙在独立墙后，丙在屋内；正在飞来的碎石会被挡板挡住。', '突然移走保护甲的挡板。', '保持挡板位置不变，默数自己的呼吸。', '甲'),
]

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    order = sorted(range(len(SCENES)), key=lambda i: hashlib.sha256(SCENES[i][0].encode()).hexdigest())
    split_of = {index: ('train' if rank < 32 else 'development' if rank < 40 else 'test')
                for rank, index in enumerate(order)}
    rows = []
    names = ['沈宁', '陆遥', '苏禾', '周岑', '陈朔', '林澄', '顾川', '唐雨']
    for i, (key, world, positive, negative, targets) in enumerate(SCENES):
        rng = random.Random(91000 + i)
        chosen = rng.sample(names, 4)
        mapping = dict(zip('甲乙丙', chosen[1:]))
        def replace(text):
            for old, new in mapping.items():
                text = text.replace(old, new)
            return text.replace('发起者', chosen[0])
        ids = rng.sample(['p17', 'p42', 'p68', 'p93'], 4)
        characters = [{'id': cid, 'name': name} for cid, name in zip(ids, chosen)]
        for variant, action, gold in [('effect', positive, targets), ('empty', negative, '')]:
            roster = characters.copy()
            rng.shuffle(roster)
            acted = [ids[1]] if i % 2 == 0 else [ids[2], ids[3]]
            row = {
                'sceneId': f'{key}:{variant}', 'sourceGroup': key, 'split': split_of[i],
                'input': {'actorId': ids[0], 'action': chosen[0] + '采取行动：' + replace(action),
                          'world': replace(world), 'characters': roster, 'alreadyActedIds': acted},
                'targetIds': [ids['甲乙丙'.index(c) + 1] for c in gold],
                'annotationStatus': 'assistant_authored_unreviewed',
                'scope': 'short_self_contained_scene',
            }
            rows.append(row)
    path = OUT / 'scenes.jsonl'
    path.write_text(''.join(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n' for r in rows))
    manifest = {
        'datasetSha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'author': 'assistant', 'humanReviewedCount': 0, 'historicalDataImported': False,
        'groups': {s: sorted({r['sourceGroup'] for r in rows if r['split'] == s})
                   for s in ['train', 'development', 'test']},
        'scenes': len(rows), 'pairs': sum(len(r['input']['characters']) for r in rows),
        'limitations': ['Artificial matched positive/empty pairs; not representative game prevalence.',
                       'Held-out scenes share author and construction method; not independent validation.',
                       'World text is authored in full; no projection of production state is validated.',
                       'Hearing an actual utterance counts as informational exposure; mental unexpressed intent does not.',
                       'Only the current frozen source is labeled; no speculative future reaction chain.'],
    }
    (OUT / 'data-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
