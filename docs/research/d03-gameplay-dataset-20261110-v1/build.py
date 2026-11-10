"""Small source-grounded D03 curation; no model training or original-file edits."""
import collections
import hashlib
import json
from pathlib import Path

ROOT=Path('/Users/davidz/Documents/GitHub/jity-eval/runs/full-games-20261106')
OUT=Path(__file__).resolve().parent
# game, submitted turn, complete relevant roster for this local excerpt, targets,
# pre-action synopsis, optional ambiguity (excluded from usable splits).
CASES=[
(1,8,['诺诺'],['诺诺'],'玩家已读完预备任务单；诺诺在办公室示意同行，准备带玩家去档案室见导师。值班人员在远处报到窗口。',''),
(1,9,['诺诺','导师'],['导师'],'诺诺把玩家带到档案室门外，敲门后侧身让开，说明导师在里面等。门内有翻纸声。','诺诺仍在门外，是否听见并受到本次报到询问的信息影响不明确。'),
(1,10,['导师'],['导师'],'玩家已经进入旧档案室。导师刚递来温室调查任务单，说要连续三晚记录光源并在三天内交报告。',''),
(1,11,['导师'],[],'导师已结束交代并低头翻纸，玩家站在档案室门口，自己的任务单已放进外套内袋。',''),
(1,35,['影子'],[],'玩家已到夹层，观察确认影子被梯脚锈线拦住，暂时不会追上来。夹层金属牌旁散着几页观测记录。',''),
(1,55,['影子'],[],'玩家刚听清门后是定时记录机构，门缝冷白光正在收窄，身后影子皮下纹路随光变化而变亮。','停止维持门缝可能改变光照并影响影子；不能把记笔记部分当作整个行动无影响。'),
(2,16,['诺诺','迎接者'],['诺诺'],'玩家在旧档案室门外向诺诺低声讲过部分发现；诺诺追问标签细节，迎接者的脚步从走廊逐渐靠近。','本次完整告知的音量与迎接者能否听见不明确，目标集合可能不止诺诺。'),
(2,19,['诺诺','取档者'],['诺诺'],'取档者已经关门上闩，脚步远去。玩家在楼梯转角平台，诺诺追到铁梯中段，低声提醒玩家不要再追。',''),
(2,22,['诺诺','门后追来的人'],['诺诺'],'玩家和诺诺已撤向楼梯井，诺诺抓着玩家袖口。听证室的人正在后方追来。','追来的人不止一个，身份与听见问话的范围不明确，不能强行合并为一个角色。'),
(2,24,['诺诺'],[],'玩家和诺诺躲入维护工具间，追来的脚步已经远去。地上有烟蒂和手电，铁架有擦痕；本行动仅检查这些痕迹。',''),
(2,25,['诺诺'],['诺诺'],'玩家数出七枚烟蒂并看见铁架擦痕；诺诺说上个月有人从铁架后搬过旧档案室封存件。',''),
(2,27,['诺诺','监视者'],[],'玩家和诺诺在后门走廊的铁皮柜阴影里，诺诺提醒走廊那头有人监视。柜后有箱子停留的痕迹。','不惊动是玩家意图，不是已证明的结果；检查动作是否暴露位置并影响监视者未确定。'),
(3,11,['诺诺'],[],'玩家和诺诺刚到登记台，屏幕显示三分钟前有人以玩家身份取件。诺诺站在玩家侧后方，也在看屏幕。','核对记录可能向共同看屏幕的诺诺暴露新信息，暂不强标空集。'),
(3,13,['诺诺'],[],'备份已经完成，玩家抽回通行卡。诺诺提出可以追查维护通道，也可以留在档案室分析卡内日志。',''),
(3,15,['诺诺'],['诺诺'],'维护通道的门被另一侧铁楔卡住，入侵者已经远去。诺诺与玩家在门外，地上留下断线和半枚接入凭证。',''),
(3,21,['诺诺'],[],'玩家仍在听证室桌前，报告的样本编号没有记全。诺诺在门外催促离开；本次动作只补记报告后半段。',''),
(3,23,['执行部核查员','诺诺','另一名执行部人员'],['执行部核查员'],'核查员已进门拿走报告，另一人在走廊堵住退路，诺诺从更远处喊玩家。','超过三个总角色，且公开亮出备份会影响哪些旁观者未明确。'),
(3,27,['核查员'],['核查员'],'核查员刚松口说编号对应的包裹早该被取走，并警告玩家不要去碰，随后重新收起文件。',''),
(4,11,['诺诺'],['诺诺'],'玩家检查过空报到桌和未干水渍。诺诺在灯影边缘，说有人比玩家先到并清空了桌子。',''),
(4,18,['诺诺','墙里的东西'],[],'诺诺带玩家离开异常走廊回门厅，墙内声音已经向深处退去。玩家准备沿路观察门框编号。',''),
(4,21,['诺诺'],['诺诺'],'玩家刚用通行卡比对投影屏，卡微微发热。诺诺在灯柱旁提醒这不是光烤的。',''),
(4,24,['诺诺','墙里的东西'],['诺诺'],'玩家和诺诺已经来到侧廊。鳞纹被拱门旧灼痕挡在原走廊，诺诺刚交出任务单并说玩家是S级观察对象。',''),
(4,26,['诺诺'],[],'玩家进入档案室并取到任务单对应档案，旁边空位的索引编号与第二项相近。诺诺留在门外提醒不要久留。',''),
(4,30,['诺诺'],['诺诺'],'玩家撕开档案袋，露出模糊编号和半个暗红残印。诺诺在楼梯口望风并催促撤离。',''),
]

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    rows=[]
    for g,t,npcs,targets,context,ambiguity in CASES:
        game=f'game-{g:02d}'
        prior=ROOT/game/'checkpoints'/f'turn-{t-1:04d}.json'
        intent=ROOT/game/'intents'/f'turn-{t:04d}.json'
        p=json.loads(prior.read_text()); a=json.loads(intent.read_text())
        action=a['request']['player_action']
        chars=[{'id':'player','name':'玩家'}]+[{'id':f'n{i}','name':n} for i,n in enumerate(npcs)]
        ids={c['name']:c['id'] for c in chars}
        split='train' if g<=2 else 'development' if g==3 else 'test'
        rows.append({'sceneId':f'gameplay:{game}:T{t:04d}', 'sourceGroup':game,'split':split,
            'reviewStatus':'needs_adjudication' if ambiguity else 'assistant_labeled_pending_human',
            'usableForTrainingOrScoring':not bool(ambiguity),
            'input':{'actorId':'player','action':action,
                     'world':context+' 原录制没有当前D03轮次的已行动名册；不能据此排除角色。',
                     'characters':chars,'alreadyActedIds':[]},
            'targetIds':[ids[n] for n in targets],
            'labelNote':ambiguity or ('明确询问或请求的对象；不把未来反应当成本次已发生结果。' if targets else
                                    '仅检查、记录或回想；截至行动前材料没有显示会对名册中其他角色产生具体影响。空集仍待人审。'),
            'alreadyActedStatus':'unknown_in_legacy_capture_not_observed_empty',
            'projectionStatus':'assistant_summary_of_local_scene_not_complete_world_state',
            'provenance':{'sourceDataset':'full-games-20261106','intentPath':str(intent),
                          'intentSha256':digest(intent),'actionPointer':'/request/player_action',
                          'preActionCheckpointPath':str(prior),'checkpointSha256':digest(prior),
                          'preActionTurn':t-1,'actionTurn':t,
                          'evidencePointers':['/output/narration','/output/dialogue','/state/npcs'],
                          'futureOutcomeUsed':False,'diceIncludedInModelInput':False},
            'auditOnly':{'preActionNarration':p['output'].get('narration',''),
                         'preActionDialogue':p['output'].get('dialogue',[]),
                         'recordedNpcs':p['state'].get('npcs',[])}})
    assert len({r['sceneId'] for r in rows})==len(rows)
    usable=[r for r in rows if r['usableForTrainingOrScoring']]
    assert all(2<=len(r['input']['characters'])<=3 for r in usable)
    assert len({r['input']['action'] for r in usable})==len(usable)
    for name,items in [('all-candidates',rows),('review-queue',[r for r in rows if not r['usableForTrainingOrScoring']])]+[(s,[r for r in usable if r['split']==s]) for s in ['train','development','test']]:
        (OUT/(name+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n' for r in items))
    summary={'status':'curated_draft_not_trained','sourceGames':4,'candidateScenes':len(rows),
        'usableDraftScenes':len(usable),'needsAdjudication':len(rows)-len(usable),'humanReviewed':0,
        'splits':{s:{'games':sorted({r['sourceGroup'] for r in usable if r['split']==s}),
                     'scenes':sum(r['split']==s for r in usable),
                     'nonempty':sum(r['split']==s and bool(r['targetIds']) for r in usable),
                     'empty':sum(r['split']==s and not r['targetIds'] for r in usable)} for s in ['train','development','test']},
        'exactDuplicateActionsAcrossSplits':0,
        'limitations':['Same campaign and recurring characters across games; game split is not an independent-world test.',
                       'Assistant-selected/annotated drafts. No original D03 labels exist in the legacy recordings.',
                       'Local-scene projection; distant world facts and current D03 acted-state unavailable.',
                       'Small sample, few positive target names, no stable quality estimate or training claim.'],
        'files':{p.name:digest(p) for p in sorted(OUT.glob('*.jsonl'))}}
    (OUT/'manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    lines=['# 四份游戏剧情 → D03 初选数据','',
        '这批只整理数据，不运行训练，不改动R1–R3及原录制。所有行动逐字取自真实提交的 player_action，前置事实来自上一回合检查点。没有用当前行动后的结果、骰点或记忆题标准答案充当输入。','',
        'game-01/02训练，game-03开发，game-04测试；有歧义的候选仅进review-queue，不进可用划分。原故事是同一学院战役的四条录制路线，且均预算收束，不能视为四个独立世界或完整通关。','',
        '标注仍需人工复核。空集只表示未发现明确影响，不是把未知当无影响；涉及旁听、被发现、角色漏记等明显歧义已移出。本批沿用2–3总角色的局部剧情片段，不伪称覆盖完整世界。旧系统没有D03已行动标记，模型上下文明确注明未知。','',
        '| ID | 划分 | 原始行动 | 草稿目标 | 状态 |','|---|---|---|---|---|']
    for r in rows:
        names={c['id']:c['name'] for c in r['input']['characters']}
        label='、'.join(names[i] for i in r['targetIds']) or '空集'
        lines.append(f"| {r['sceneId']} | {r['split']} | {r['input']['action']} | {label} | {'待裁定，已排除' if not r['usableForTrainingOrScoring'] else '助手草稿'} |")
    lines+=['','模型仅应读取input，不能把auditOnly、targetIds、labelNote或provenance整体拼入输入。原文证据与SHA仅供核验。','',
            '下一步宜扩大每局的清晰片段、核对目标和旁观者边界，再训练；不要拿这批极小测试集估计上线质量。']
    (OUT/'README.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
