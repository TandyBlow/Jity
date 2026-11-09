"""Author NEW exploratory supervision; this is not a model or a runtime backend.

Every semantic choice below is an assistant-authored label. Orchestrators are
used only to capture their actual complete task inputs, including all preceding
reference candidates. These reference inputs define the diagnostic arm, never
live-upstream model quality. No existing protected scenario file is read.
"""
from __future__ import annotations
import copy
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from run_pilot import digest,exclusive
from short_contracts import result
from short_intent import produce_intent,analyze_targets,produce_reaction
from short_settlement import settle_joint,run_updates
from short_lifecycle import InitialDraft
from short_training import validate_rows,END

ROOT=Path(__file__).resolve().parent
# Distinct causal scenarios. Names are not used to manufacture extra sources.
SCENES=[
 dict(id='buoy',split='train',place='浮标维护棚',away='潮位观察台',actor='温禾',other='杜岑',off='辛序',item='浮标灯',tool='绝缘钳',
      goal='恢复航道浮标的照明。',steps=['温禾尝试用绝缘钳接好浮标灯的松线。'],
      otherAction='杜岑尝试固定浮标灯的外壳。',relation='supports',judgment='not_achieved',
      facts=['浮标灯的松线仍未接通。','温禾的袖口沾上了灯壳上的油。'],appearance='袖口有一小片油迹。',
      descriptionOwner='a',done=False,subtasks=['检查接线端的腐蚀。','清理接线端。']),
 dict(id='archive',split='train',place='潮汐档案室',away='借阅核验柜',actor='余荞',other='郑栖',off='费宁',item='借阅牌',tool='封存夹',
      goal='向核验员借取现存的借阅牌。',steps=['余荞尝试向郑栖请求借阅牌。'],
      otherAction='郑栖尝试把借阅牌交给余荞。',relation='supports',judgment='achieved',
      facts=['郑栖把借阅牌交到余荞手中。'],move={'object':'a'},done=True,
      preference='更愿意先向同伴提出明确请求。',sanity=68,subtasks=[]),
 dict(id='dye',split='train',place='织物配色台',away='样布晾架',actor='唐霁',other='连笙',off='曲尧',item='染料碗',tool='搅拌棒',
      goal='把染料碗稳妥交到样布晾架。',steps=['唐霁尝试拿起染料碗。'],
      otherAction='连笙尝试把染料碗拉到自己面前。',relation='contests',judgment='not_achieved',
      facts=['两人拉扯染料碗时，少量染料溅到了配色台上，碗仍留在原处。'],appearance='台面多了几滴蓝色染料。',
      descriptionOwner='loc',done=False,subtasks=['先与连笙商定谁搬运染料碗。']),
 dict(id='swap',split='train',place='仪器调校间',away='仪器储存间',actor='柏晴',other='裴弦',off='陆知',item='校准箱',tool='护角垫',
      goal='把校准箱送到仪器储存间。',steps=['柏晴尝试抱着校准箱前往仪器储存间。'],
      otherAction='裴弦尝试从仪器储存间走到仪器调校间。',relation=None,judgment='achieved',
      facts=['柏晴抱着校准箱到达仪器储存间，裴弦同时到达仪器调校间。'],move={'a':'far','b':'loc','object':'a'},done=True,
      preference='搬运前会主动核对通道是否空闲。',sanity=74,subtasks=[]),
 dict(id='drying',split='train',place='海图修复台',away='湿度记录间',actor='叶予',other='何铎',off='穆澄',item='海图',tool='吸水纸',
      goal='让海图表面不再潮湿。',steps=['叶予尝试用吸水纸轻压海图表面。'],
      otherAction='何铎尝试稳住海图边缘。',relation='supports',judgment='achieved',
      facts=['海图表面的水分被吸走，原先的潮湿状态不再存在。'],removeAppearance=True,done=True,
      preference='处理易损物时会先寻求同伴协助。',sanity=81,subtasks=[]),
 dict(id='conditional',split='train',place='种子分类室',away='种子领取台',actor='柳絮',other='阮明',off='苏朔',item='种子盒',tool='封口签',
      goal='检查封口后把种子盒交给阮明。',steps=['柳絮尝试检查种子盒的封口签。','若封口签完整，柳絮尝试把种子盒交给阮明。'],
      otherAction='阮明尝试接住柳絮递来的种子盒。',relation='depends',judgment='partial',
      facts=['柳絮发现封口签已经破损，因此没有交出种子盒。'],done=False,
      subtasks=['核对种子盒内的数量。','向负责人报告封口破损。']),
 dict(id='missing',split='train',place='陶片复原室',away='残片存放架',actor='江岚',other='沈知',off='罗歆',item='残缺陶碗',tool='软尺',
      goal='确认残缺陶碗的缺口尺寸。',steps=['江岚尝试用软尺量出残缺陶碗的缺口。'],
      otherAction='沈知尝试扶稳残缺陶碗。',relation='supports',judgment='achieved',
      facts=['江岚量出残缺陶碗的缺口宽约三厘米。'],appearance='缺口宽约三厘米，边沿仍有破损。',descriptionOwner='object',done=True,
      preference='倾向于先测量再决定修补方法。',sanity=88,subtasks=[]),
 dict(id='signal',split='train',place='山口信号站',away='远端值守室',actor='周苇',other='谢迟',off='季闻',item='信号机',tool='备用插头',
      goal='向远端值守室发出道路封闭通知。',steps=['周苇尝试用信号机向季闻发送道路封闭通知。'],
      otherAction='谢迟尝试压紧信号机的备用插头。',relation='supports',judgment='not_achieved',
      facts=['信号机没有发出通知，屏幕显示线路故障。'],appearance='屏幕显示线路故障。',descriptionOwner='object',done=False,
      subtasks=['检查信号机的线路连接。']),
 dict(id='gate',split='development',place='防潮闸控制室',away='下层检修道',actor='宋黎',other='易安',off='孟遥',item='闸门手柄',tool='锁紧销',
      goal='让防潮闸保持关闭。',steps=['宋黎尝试把锁紧销插入闸门手柄的销孔。'],
      otherAction='易安尝试向外扳动闸门手柄。',relation='obstructs',judgment='partial',
      facts=['锁紧销只插入一半，闸门手柄受到卡阻，但仍不能确认防潮闸已锁定。'],appearance='锁紧销有一半露在销孔外。',descriptionOwner='tool',done=False,
      subtasks=['检查锁紧销卡住的原因。']),
 dict(id='waiting',split='development',place='测震观察室',away='外侧走廊',actor='陶青',other='顾芒',off='任澈',item='记录仪',tool='计时表',
      goal='等到五分钟稳定观测期结束。',steps=['陶青尝试在测震观察室等待稳定观测期结束。'],
      otherAction='顾芒尝试保持安静，避免碰动记录仪。',relation='supports',judgment='achieved',
      facts=['五分钟稳定观测期已经结束，记录仪没有受到碰动。'],done=True,
      preference='等待观察结果时更愿意遵守约定。',sanity=86,offPreference=True,subtasks=[]),
 dict(id='jointlift',split='test',place='标本整理室',away='恒温存放间',actor='柯遥',other='伍澄',off='韩朔',item='标本托盘',tool='防滑垫',
      goal='将标本托盘平稳送到恒温存放间。',steps=['柯遥尝试与伍澄共同抬起标本托盘。','柯遥尝试与伍澄把标本托盘送到恒温存放间。'],
      otherAction='伍澄尝试托住标本托盘另一侧并配合柯遥移动。',relation='supports',judgment='achieved',
      facts=['两人共同抬着标本托盘到达恒温存放间，托盘仍保持水平。'],move={'a':'far','b':'far','object':'far'},done=True,
      preference='搬运脆弱物件时会主动与同伴分工。',sanity=79,subtasks=[]),
 dict(id='newentity',split='test',place='天文校时台',away='设备存放柜',actor='方禾',other='奚白',off='宁砚',item='校时钟',tool='拨针杆',
      goal='把校时钟调整到正确时间。',steps=['方禾尝试从空的设备存放柜中取出一块未登记的替换齿轮，再修好校时钟。'],
      otherAction='奚白尝试用拨针杆固定校时钟的指针。',relation='supports',judgment='not_achieved',
      facts=['设备存放柜中没有替换齿轮，校时钟仍然停摆。'],done=False,
      subtasks=['检查现有齿轮是否能够重新啮合。'])]


def world_for(s):
    names={'loc':s['place'],'far':s['away'],'a':s['actor'],'b':s['other'],'off':s['off'],'object':s['item'],'tool':s['tool']}
    world={'worldId':'world:'+s['id'],'protagonistId':'a','time':{'dateTime':'2026-11-09T09:00:00'},'initial':{k:{} for k in ('locations','items','characters')},
           'locations':{},'items':{},'characters':{}}
    for kind,keys in (('locations',('loc','far')),('items',('object','tool')),('characters',('a','b','off'))):
        for key in keys:
            initial={'id':key,'name':names[key],'initialAppearance':'现有实体，外观完整。','slots':[]}
            current={'id':key,'appearanceChanges':[]}
            if kind=='locations':
                initial['parentLocationId']='loc' if key=='far' and s['id']=='archive' else None
                if key=='loc':initial['slots']=[{'id':'slot:surface','label':'工作台面'}]
            else:
                container='far' if key=='off' or (s['id']=='swap' and key=='b') else 'loc'
                if key=='tool':container='a'
                initial['initialPosition']={'containerId':container};current['position']=copy.deepcopy(initial['initialPosition'])
            if kind=='characters':
                preferences={
                  'a':('习惯先检查'+s['item']+'的状态，再提出具体尝试。',62+next(i for i,x in enumerate(SCENES) if x['id']==s['id'])%7*4),
                  'b':('遇到物品争用时倾向于坚持自己先使用。',46) if s['relation']=='contests' else ('愿意回应同伴的明确请求，操作时注意保持物品稳定。',78),
                  'off':('远处发生变化时倾向于先等待确认，再决定是否介入。',89)}
                initial.update(initialPersonality=preferences[key][0],initialSanity=preferences[key][1])
                current.update(personalityChanges=[],sanity=initial['initialSanity'],tasks={key+'-task':{'id':key+'-task','ownerId':key,'parentTaskId':None,
                    'goal':s['goal'] if key=='a' else '协助同伴安全完成当前工作。' if key=='b' else '等待工作情况的正式确认。','status':'pending'}})
            world['initial'][kind][key]=initial;world[kind][key]=current
    world['initial']['protagonistId']='a'
    if s['id'] in ('buoy','conditional','jointlift'):
        world['characters']['a']['tasks']['a-inspect']={'id':'a-inspect','ownerId':'a','parentTaskId':'a-task',
          'goal':'确认'+s['item']+'在当前操作中保持稳定。','status':'pending'}
    conditions={
      'buoy':{'object':'灯壳外侧有油，接线端松脱且有腐蚀，灯不亮。'},
      'archive':{'b':'负责借阅牌发放的核验员，愿意按请求办理交接。'},
      'dye':{'object':'盛有蓝色染料的敞口碗，移动时容易溅出。'},
      'swap':{'object':'装有校准仪的箱子，箱体完好。'},
      'missing':{'object':'陶碗缺了一块，缺口边缘有破损。'},
      'signal':{'object':'线路接头断开，当前无法向远端发送信号。'},
      'gate':{'tool':'锁紧销前端有毛刺，插入时可能受阻。'},
      'waiting':{'tool':'显示稳定观察期已进行了五分钟。'},
      'newentity':{'object':'校时钟的齿轮卡住，指针已经停摆。'}}
    for key,text in conditions.get(s['id'],{}).items():
        kind=next(k for k in ('locations','items','characters') if key in world['initial'][k])
        world['initial'][kind][key]['initialAppearance']=text
    if s['id']=='dye':world['characters']['b']['tasks']['b-task']['goal']='把染料碗拿到自己面前进行调色。'
    if s['id']=='swap':world['items']['object']['position']={'containerId':'a'};world['initial']['items']['object']['initialPosition']={'containerId':'a'}
    if s['id']=='conditional':world['items']['tool']['position']={'containerId':'object'};world['initial']['items']['tool']['initialPosition']={'containerId':'object'}
    if s.get('removeAppearance'):
        world['items']['object']['appearanceChanges']=[{'id':'damp','text':'表面潮湿。','supersedes':[],'active':True}]
    if s['id']=='conditional':
        world['items']['tool']['appearanceChanges']=[{'id':'seal-broken','text':'封口签上有一道明显裂口。','supersedes':[],'active':True}]
    if s['id']=='newentity':world['initial']['locations']['far']['initialAppearance']='柜内没有替换零件。'
    world.update(engineVersion='world-engine-v1',schemaVersion=1)
    world['time'].update(calendar='gregorian',instantOrdinal=0)
    world['initial'].update(engineVersion='world-engine-v1',schemaVersion=1,worldId=world['worldId'],initialTime=copy.deepcopy(world['time']))
    for key,person in world['characters'].items():world['initial']['characters'][key]['tasks']=copy.deepcopy(person['tasks'])
    for kind in ('locations','items','characters'):
        for entity in world[kind].values():
            for field in ('appearanceChanges','personalityChanges'):
                for record in entity.get(field,[]):record.update(sourcePointId='prelude:'+s['id'],sourceSequence=1)
    return world


def lab_world(world):
    result={'time':'2026-11-09T09:00:00','places':[],'items':[],'characters':[]}
    for kind,target in (('locations','places'),('items','items'),('characters','characters')):
        for key,entity in world[kind].items():
            initial=world['initial'][kind][key]
            row={'id':key,'name':initial['name'],'appearance':initial['initialAppearance']+' '.join(r['text'] for r in entity['appearanceChanges'] if r.get('active') and r['text'])}
            if kind=='locations':row['parentId']=initial['parentLocationId']
            else:row['position']=entity['position']
            if kind=='characters':
                row.update(personality=[initial['initialPersonality']],sanity=entity['sanity'],tasks=[
                   {'id':t['id'],'parentId':t['parentTaskId'],'text':t['goal'],'status':t['status']} for t in entity['tasks'].values()])
            result[target].append(row)
    return result


class AuthorCapture:
    def __init__(self,scene,world):self.scene=scene;self.world=world;self.rows=[];self.phase='intent';self.fact_index=0
    def record(self,component,payload,value,codec='json'):
        kind='annotation_only' if codec=='json' else 'text';target=json.dumps(value,ensure_ascii=False,separators=(',',':')) if codec=='json' else value
        extra={}
        if component in ('D02.1','D07.2','D07.3'):
            kind='label';target=value;extra['labels']={'D02.1':['act','skip'],'D07.2':['likely','unlikely'],'D07.3':['related','unrelated']}[component]
        elif component in ('D01.6','U6.1'):kind='number';target=value
        elif codec=='text':target=value
        elif codec in ('fragment_or_end','fact_or_end'):
            target=END if value['kind']=='end' else value['text']
        row={'exampleId':self.scene['id']+':'+component+':'+str(len(self.rows)+1),'sourceGroup':'short-20261109:'+self.scene['id'],
          'split':self.scene['split'],'component':component,'kind':kind,'outputCodec':codec,'input':copy.deepcopy(payload),'target':target,
          'annotationStatus':'assistant_draft','sourceStatus':'unverified','origin':'new_assistant_authored_scene_2026-11-09',
          'reviewStatus':'pending_human','trainingPurpose':'exploratory_draft_only','inputProvenance':'authored_correct_intermediate_diagnostic',**extra}
        row['contentSha256']=digest(row);self.rows.append(row)
    def call(self,c,p):
        s=self.scene;codec='json'
        if c=='D01.1':
            v={'entities':[{'kind':k,'name':e['name'],'slots':[slot['label'] for slot in e.get('slots',[])]} for k in ('locations','items','characters') for e in self.world['initial'][k].values()],'protagonistIndex':4}
        elif c=='D01.2':
            by_name={e['name']:key for k in ('locations','items','characters') for key,e in p['draft'][k].items()}
            v={}
            for k in ('locations','items','characters'):
                for key,e in p['draft'][k].items():
                    original=next(x for x in self.world['initial'][k].values() if x['name']==e['name'])
                    parent=original.get('parentLocationId') if k=='locations' else original['initialPosition']['containerId']
                    if parent is None:v[key]=None
                    else:
                        parent_name=next(x[parent]['name'] for x in self.world['initial'].values() if isinstance(x,dict) and parent in x)
                        v[key]=by_name[parent_name] if k=='locations' else {'containerId':by_name[parent_name]}
        elif c=='D01.3':
            name=next(x[p['entityId']]['name'] for x in p['draft'].values() if isinstance(x,dict) and p['entityId'] in x)
            v=next(e['initialAppearance'] for k in self.world['initial'].values() if isinstance(k,dict) for e in k.values() if e['name']==name);codec='text'
        elif c=='D01.4':
            person=p['draft']['characters'][p['characterId']]
            original=next(key for key,e in self.world['initial']['characters'].items() if e['name']==person['name'])
            tasks=list(self.world['characters'][original]['tasks'].values());index=len(person['tasks'])
            if index>=len(tasks):v={'kind':'end'}
            else:v={'kind':'task','goal':tasks[index]['goal'],'parentTaskId':next(iter(person['tasks'])) if tasks[index]['parentTaskId'] else None}
        elif c in ('D01.5','D01.6'):
            person=p['draft']['characters'][p['characterId']]
            original=next(e for e in self.world['initial']['characters'].values() if e['name']==person['name'])
            v=original['initialPersonality'] if c=='D01.5' else original['initialSanity'];codec='text' if c=='D01.5' else 'scalar'
        elif c=='D02.1':v='act'
        elif c=='D02.2':
            steps=[s['otherAction']] if p['context']['actorId']=='b' else s['steps']
            index=len(p['fragments']);v={'kind':'fragment','text':steps[index]} if index<len(steps) else {'kind':'end'};codec='fragment_or_end'
        elif c=='D02.3':
            refs=[]
            names={key:e['name'] for k in ('locations','items','characters') for key,e in self.world['initial'][k].items()}
            roles={'a':'subject' if p['context']['actorId']=='a' else 'recipient','b':'subject' if p['context']['actorId']=='b' else 'recipient','off':'recipient','object':'object','tool':'tool','far':'destination','loc':'destination'}
            for key,name in names.items():
                start=p['text'].find(name)
                if start>=0:refs.append({'role':roles[key],'entityId':key,'start':start,'end':start+len(name)})
            v={'verdict':'pass','references':refs}
        elif c in ('D02.4','D02.5'):
            checks=('dependencies','conditions','requirements') if c=='D02.4' else ('actor','tools','objects','qualifiers','attempt')
            v={'verdict':'pass','fragmentIds':[f['fragmentId'] for f in p['fragments']],'checks':{k:'pass' for k in checks},'issues':[]}
        elif c=='D03.1':v=[{'candidateId':key,'relation':'target' if key=='b' and s['relation'] in ('contests','obstructs') else 'none'} for key in p['candidateIds']]
        elif c=='D03.2':v={'verdict':'pass','candidateIds':p['candidateIds'],'targetIds':p['targetIds']}
        elif c=='D04.1':
            v={'threatSourceIds':[t['memberId'] for t in p['threats']],
               'constraint':'回应'+s['actor']+'对'+s['item']+'的尝试，保持当前工具与对象的角色，采用防护或协助行动，不宣告结果。'}
        elif c=='D05.1':v={'checkedActionIds':['a','b'],'relations':[] if not s['relation'] else [{'sourceId':'b','targetId':'a','kind':s['relation']}]}
        elif c=='D05.2':v={'judgments':[{'attemptId':a['attemptId'],'label':('achieved' if a['attemptId']=='a:fragment-1' else 'not_achieved') if s['id']=='conditional' and a['memberId']=='a' else s['judgment'] if a['memberId']=='a' else ('not_achieved' if s['relation']=='contests' or s['id']=='conditional' else 'partial' if s['id']=='gate' else 'achieved')} for a in p['attempts']]}
        elif c=='D05.3':
            index=len(p['candidates']);v={'kind':'fact','text':s['facts'][index]} if index<len(s['facts']) else {'kind':'end'};codec='fact_or_end'
        elif c=='D05.4':v={'verdict':'pass','checkedActionIds':['a','b'],'checkedFactIds':[f['id'] for f in p['candidates']],'checkedRollIds':['roll:1','roll:2']}
        elif c=='D05.5':v={'facts':[{'factId':f['id'],'memberIds':['a','b'] if s['relation']=='contests' else ['b'] if i==len(p['candidates'])-1 else ['a']} for i,f in enumerate(p['candidates'])],'checkedMemberIds':['a','b']}
        elif c=='U1.1':v={'decisions':[{'entityId':key,'change':key in s.get('move',{})} for key in p['entityIds']]}
        elif c=='U1.2':v={'positions':[{'entityId':key,'position':{'containerId':s['move'][key]}} for key in p['entityIds']]}
        elif c in ('U2.1','U5.1'):
            ops=[]
            for key in p['entityIds']:
                op='keep';records=list(p['activeRecords'][key])
                if c=='U2.1' and s.get('appearance') and key==s['descriptionOwner']:op='add';records=[]
                if c=='U2.1' and s.get('removeAppearance') and key=='object':op='remove';records=['damp']
                owner='off' if s.get('offPreference') else 'a'
                if c=='U5.1' and s.get('preference') and key==owner:op='add';records=[]
                ops.append({'entityId':key,'op':op,'recordIds':records})
            v={'checkedEntityIds':p['entityIds'],'checkedRecordIds':[rid for key in p['entityIds'] for rid in p['activeRecords'][key]],'operations':ops}
        elif c=='U2.2':v=s['appearance'];codec='text'
        elif c=='U3.1':v={'checkedCharacterIds':p['characterIds'],'decisions':[{'taskId':key,'label':'achieved' if key=='a-task' and s['done'] else 'pending'} for key in p['taskIds']]}
        elif c=='U4.1':v={'checkedParentTaskIds':p['parentTaskIds'],'checkedCharacterIds':p['characterIds'],'needs':[{'parentTaskId':key,'count':len(s['subtasks']) if key=='a-task' else 0} for key in p['parentTaskIds']]}
        elif c=='U4.2':v=s['subtasks'][p['goalIndex']];codec='text'
        elif c=='U5.2':v=s['preference'];codec='text'
        elif c=='U6.1':v=s['sanity']
        elif c=='D06.P.review':v={'verdict':'pass','checkedEntityIds':list(p['proposed']['changes'])}
        elif c=='D06.P.mapping':
            # All source facts remain visible. This association is a draft semantic
            # judgment, never a proof obtained from simply numbering candidates.
            mappings=[]
            for i,f in enumerate(p['facts']):
                targets=[r for r in p['candidateRefs'] if (i==1 if s['id']=='buoy' and r['stage']=='appearance' else i==0)]
                mappings.append({'factId':f['id'],'kind':'state' if targets else 'transient','targets':targets})
            v={'verdict':'pass','mappings':mappings}
        else:raise ValueError('author has not labeled '+c)
        self.record(c,p,v,'scalar' if c in ('D02.1','D01.6','U6.1') else codec);return result(v)


def author_preview(base):
    def apply(req):
        world=copy.deepcopy(base)
        for call in req['completedStages']:
            for owner,delta in call['changes'].items():
                entity=next(world[k][owner] for k in ('locations','items','characters') if owner in world[k])
                if 'positionSet' in delta:entity['position']=copy.deepcopy(delta['positionSet'])
                for field in ('appearanceChanges','personalityChanges'):
                    for change in delta.get(field,[]):
                        for old in entity[field]:
                            if old['id'] in change['supersedes']:old['active']=False
                        entity[field].append({**change,'active':change['text'] is not None,'sourcePointId':req['binding']['pointId'],'sourceSequence':1})
                for key in delta.get('tasksAchieved',[]):entity['tasks'][key]['status']='achieved'
                for task in delta.get('subtasksAdded',[]):entity['tasks'][task['id']]=copy.deepcopy(task)
                if 'sanitySet' in delta:entity['sanity']=delta['sanitySet']
        return result({**{k:req[k] for k in ('binding','candidateHash','baseWorldHash','stage')},'world':world})
    return apply


def build():
    all_rows=[];sources=[]
    for s in SCENES:
        s=copy.deepcopy(s)
        other_facts={
          'buoy':'杜岑稳住了浮标灯的外壳。','archive':'郑栖完成了借阅牌的交接。',
          'swap':'裴弦到达了仪器调校间。','drying':'何铎稳住了海图边缘。',
          'conditional':'阮明伸出手准备接盒，但没有接到种子盒。','missing':'沈知扶稳了残缺陶碗。',
          'signal':'谢迟压紧了备用插头，但断开的线路未恢复。','gate':'易安扳动手柄时受到卡阻。',
          'waiting':'顾芒保持了安静，没有碰动记录仪。','jointlift':'伍澄在搬运中托住了托盘另一侧。',
          'newentity':'奚白用拨针杆固定住了校时钟的指针。'}
        if s['id'] in other_facts:s['facts'].append(other_facts[s['id']])
        world=world_for(s);author=AuthorCapture(s,world)
        initial=InitialDraft('draft:'+s['id'],s['place']+'与'+s['away']+'中的现有物品和人物，当前工作：'+s['goal'],world['time'])
        draft=initial.generate(author)
        if draft.status!='result':raise ValueError(s['id']+':D01:'+str(draft.reason))
        context={'world':world,'actorId':'a','protagonistId':'a','advance':{'advanceId':'advance:'+s['id'],'inputId':'input:'+s['id'],'inputText':'请帮我处理这件事：'+s['goal'],'intentStatus':'pending'},'confirmedPrefix':[]}
        action=produce_intent(author,context,'op:'+s['id'])
        if action.status!='result':raise ValueError(s['id']+':intent:'+str(action.reason))
        group={'groupId':'group:'+s['id'],'closed':True,'memberIds':['a','b'],
          'members':[{'memberId':'a','actionText':action.value.text,'fragments':action.value.material()['renderedFragments']},{'memberId':'b','actionText':s['otherAction'],'fragments':[{'id':'b:fragment-1','text':s['otherAction']}]}],
          'confirmedTargets':[{'sourceId':'a','targetIds':['b','off']},{'sourceId':'b','targetIds':[]}],
          'judgments':[{'sourceId':'a','targetId':'b','rollId':'roll:1','result':15,'target':11,'groupId':'group:'+s['id'],'triggerKey':'trigger:1','eligibilityBaselineDigest':digest(world),'ruleVersion':'reaction-d20-v1','eligible':True,'admitted':True},
                       {'sourceId':'a','targetId':'off','rollId':'roll:2','result':5,'target':11,'groupId':'group:'+s['id'],'triggerKey':'trigger:2','eligibilityBaselineDigest':digest(world),'ruleVersion':'reaction-d20-v1','eligible':False,'admitted':False}],
          'alreadyActedIds':['off']}
        reaction=produce_reaction(author,context,'reaction:'+s['id'],member_id='b',confirmed_actions=[action.value],
          threats=[{'memberId':'a','actionText':action.value.text}],judgments=group['judgments'])
        if reaction.status!='result':raise ValueError('reaction reference:'+str(reaction.reason))
        settlement_context={'world':world,'timeAdvance':{'boundary':'elapsed','duration':{'amount':5 if s['id']=='waiting' else 1,'unit':'minute'}},'binding':{'pointId':'point:'+s['id'],'version':1,'epoch':1},'group':group}
        settlement=settle_joint(author,settlement_context)
        if settlement.status!='result':raise ValueError(s['id']+':D05:'+str(settlement.reason))
        updates=run_updates(author,settlement_context,settlement.value,author_preview(world),lambda kind,slot:kind+':'+slot)
        if updates.status!='result':raise ValueError(s['id']+':D06:'+str(updates.reason))
        # Narrow role-selection supervision is a separate trained pointer head.
        reference_input={'world':context['world'],'actorId':'a','fragment':s['steps'][0],
          'candidates':[{'id':key,'name':e['name'],'kind':kind} for kind in ('locations','items','characters') for key,e in world['initial'][kind].items()]}
        pointer={'exampleId':s['id']+':D02.3.subject','sourceGroup':'short-20261109:'+s['id'],'split':s['split'],
          'component':'D02.3.subject','kind':'reference','outputCodec':'scalar','input':reference_input,'target':'a',
          'annotationStatus':'assistant_draft','sourceStatus':'unverified','origin':'new_assistant_authored_scene_2026-11-09',
          'reviewStatus':'pending_human','trainingPurpose':'exploratory_draft_only','inputProvenance':'authored_correct_intermediate_diagnostic'}
        pointer['contentSha256']=digest(pointer);author.rows.append(pointer)
        # Negative disposition, target candidates and admitted-reaction constraints.
        skip=copy.deepcopy(next(r for r in author.rows if r['component']=='D02.1')['input']);skip['context']['advance']={'advanceId':'advance:'+s['id'],'inputId':'input:'+s['id'],'inputText':None,'intentStatus':'expired'}
        skip['context']['world']['characters']['a']['tasks']={}
        author.record('D02.1',skip,'skip','scalar')
        # Capture D03 using the real complete request shape, before actual rolls.
        targets=analyze_targets(author,context,action.value,confirmed_group=[{'memberId':'a','actionText':action.value.text}],already_acted_ids=['off'],judgments=[])
        if targets.status=='incomplete':raise ValueError('D03:'+str(targets.reason))
        # NPC autonomy: same source group, no player-supplied action sentence.
        npc=copy.deepcopy(context);npc['protagonistId']='off';npc['world']['protagonistId']='off';npc['world']['initial']['protagonistId']='off'
        npc['advance']={'advanceId':'advance:'+s['id'],'inputId':'input:'+s['id'],'inputText':'我先在原地等候消息。','intentStatus':'consumed'}
        autonomous=produce_intent(author,npc,'npc-op:'+s['id'])
        if autonomous.status!='result':raise ValueError('NPC draft:'+str(autonomous.reason))
        # Frozen committed-shaped diagnostic inputs; these are authored receipts,
        # never claimed as a production commit or real C ready event.
        point='point:'+s['id'];round_id='round:'+s['id']
        after=author_preview(world)({'completedStages':updates.value['updates'],'binding':settlement_context['binding'],
            'candidateHash':digest(updates.value['updates']),'baseWorldHash':digest(world),'stage':'sanity'}).value['world']
        follow={'world':after,'roundId':round_id,'requiredPointIds':[point],'completedPointIds':[point],
          'readyPointIds':[point],'roundComplete':True,'budgetPaused':False,
          'roundChanges':{'roundId':round_id,'points':[{'pointId':point,'previousPointId':'initial:'+s['id'],
              'version':1,'stateDigest':digest(after),'timeAdvance':{'boundary':'elapsed','duration':{'amount':1,'unit':'minute'}},
              'entityDeltas':{key:{field:value for call in updates.value['updates'] for field,value in call['changes'].get(key,{}).items()} for key in {owner for call in updates.value['updates'] for owner in call['changes']}}}]},
          'committedHead':{'worldId':world['worldId'],'pointId':point,'version':1,'stateDigest':digest(after)},
          'currentWorldHash':digest(after),
          'requiredGates':{point:{'pointId':point,'requestId':'authored-request:'+s['id'],'epoch':1,'version':1}},
          'readyReceipts':[{'pointId':point,'requestId':'authored-request:'+s['id'],'epoch':1,'version':1,'status':'ready'}]}
        candidate={'kind':'candidate','characterId':'a','text':s['subtasks'][0] if s['subtasks'] else '尝试核对当前工作的完成情况。'}
        author.record('D07.1',{**follow,'proposed':[]},candidate)
        author.record('D07.1',{**follow,'proposed':[candidate]},{'kind':'end'})
        author.record('D07.2',{**follow,'proposed':[candidate],'candidateIndex':0},'likely','scalar')
        author.record('D07.3',{**follow,'proposed':[candidate],'candidateIndex':0},'related','scalar')
        unrelated={'kind':'candidate','characterId':'off','text':'尝试整理自己房间内的衣袖。'}
        author.record('D07.3',{**follow,'proposed':[unrelated],'candidateIndex':0},'unrelated','scalar')
        impossible={'kind':'candidate','characterId':'a','text':'尝试立即前往世界中不存在的另一颗星球。'}
        author.record('D07.2',{**follow,'proposed':[impossible],'candidateIndex':0},'unlikely','scalar')
        time_value={'boundary':'instant','duration':{'amount':0,'unit':'second'}} if s['id'] in ('dye','gate') else {'boundary':'elapsed','duration':{'amount':5 if s['id']=='waiting' else 10 if s['id']=='archive' else 1,'unit':'second' if s['id']=='archive' else 'minute'}}
        author.record('D08.1',{'world':world,'pointId':point,'timeLocked':False,'timeAdvance':None,'frozenActions':group['members']},time_value)
        author.record('D08.2',{'world':world,'roundId':round_id,'order':['a','b','off'],'actedIds':[],
             'visitedIds':[],'frozenActions':{}},[{'kind':'instant' if time_value['boundary']=='instant' else 'normal','timeAdvance':time_value,'actorIds':['a','b','off']}])
        # Bad success wording and omitted-step counterexamples are explicit
        # authored labels, not automatically inferred correctness decisions.
        for component in ('D02.4','D02.5'):
            source=next(r for r in author.rows if r['component']==component)
            bad=copy.deepcopy(source['input']);bad['fragments'][0]['text']=s['actor']+'已经成功完成全部目标。'
            checks=('dependencies','conditions','requirements') if component=='D02.4' else ('actor','tools','objects','qualifiers','attempt')
            author.record(component,bad,{'verdict':'reject','fragmentIds':[f['fragmentId'] for f in bad['fragments']],
              'checks':{key:'fail' for key in checks},'issues':[{'fragmentId':bad['fragments'][0]['fragmentId'],'code':'asserted_success_or_omitted_requirement'}]})
        binding=copy.deepcopy(next(r for r in author.rows if r['component']=='D02.3'))
        wrong=copy.deepcopy(binding['input']);wrong['text']=wrong['text'].replace(s['actor'],s['other'])
        author.record('D02.3',wrong,{'verdict':'reject','references':[]})
        check=next(r for r in author.rows if r['component']=='D03.2');wrong=copy.deepcopy(check['input'])
        wrong['targetIds']=['b'] if not wrong['targetIds'] else []
        author.record('D03.2',wrong,{'verdict':'reject','candidateIds':wrong['candidateIds'],'targetIds':wrong['targetIds']})
        stage=next(r for r in author.rows if r['component']=='D06.P.review')
        wrong=copy.deepcopy(stage['input']);wrong['proposed']={'stage':'position','changes':{'off':{'entityId':'off','positionSet':{'containerId':'a'}}}}
        author.record('D06.P.review',wrong,{'verdict':'reject','checkedEntityIds':['off']})
        if s['judgment']!='achieved':
            positive=next(r for r in author.rows if r['component']=='D05.4')
            wrong=copy.deepcopy(positive['input']);wrong['candidates'][0]['text']='所有尝试均已完全达成，且没有任何副作用。'
            rejected=json.loads(positive['target']);rejected['verdict']='reject'
            author.record('D05.4',wrong,rejected)
        # Every candidate count and label is reported separately from successful
        # packaging. These are new labels inside the same source group.
        all_rows.extend(author.rows)
        sources.append({'sourceGroup':'short-20261109:'+s['id'],'split':s['split'],'scenario':s,'world':world,
          'sourceStatus':'assistant_authored_unverified','humanReview':'pending','independence':'not_established',
          'candidateBytesSha256':digest({'scenario':s,'world':world})})
    return all_rows,sources


def write():
    rows,sources=build()
    from project_primitives import project_annotations
    primitives,packaging=project_annotations(rows)
    # Explicit same-source negative threat coverage labels, never extra sources.
    negatives=[]
    for row in primitives:
        if row['component']=='D04.1.covered':
            bad=copy.deepcopy(row);bad['exampleId']+=':missing-threat'
            bad['input']['semanticQuery']['constraints']=['只讨论与当前行动无关的天气。']
            bad['target']='missing';bad['inputProvenance']='authored_counterexample_same_source'
            bad['contentSha256']=digest({k:v for k,v in bad.items() if k!='contentSha256'});negatives.append(bad)
    primitives.extend(negatives);rows.extend(primitives)
    inventory=validate_rows(rows)
    packet=ROOT/'supervision.jsonl.gz';source=ROOT/'sources.jsonl'
    import gzip
    for path,values in ((packet,rows),(source,sources)):
        raw=''.join(json.dumps(v,ensure_ascii=False,sort_keys=True)+'\n' for v in values).encode()
        if path.suffix=='.gz':raw=gzip.compress(raw,mtime=0)
        if path.exists():
            if path.read_bytes()!=raw:raise FileExistsError('preserve original draft: '+str(path))
        else:path.write_bytes(raw)
    from lab import sha256_file
    manifest={'schema':'jity-d-short-supervision-v1','inventory':inventory,'files':{p.name:sha256_file(p) for p in (packet,source)},'uncompressedSupervisionSha256':__import__('hashlib').sha256(gzip.decompress(packet.read_bytes())).hexdigest(),
      'author':'assistant','humanReview':'pending','sourceVerification':'pending','formalEvaluationAllowed':False,
      'authorization':'current_user_request_to_author_training_data_2026-11-09',
      'protectedDatasetsRead':[],'old42Or90Used':False,'otherBranchesUsed':False,
      'modelCalls':0,'trainingSteps':0,'primitiveExamples':len(primitives),'annotationOnlyExamples':sum(r['kind']=='annotation_only' for r in rows),'packagingChecks':packaging,'diagnosticInputs':'author-provided intermediates, not live model upstream',
      'limitations':['only twelve authored scenario groups','common structural template across splits','no human source/semantic independence verification',
                     'test candidates are openly authored, not a sealed benchmark','teacher generation is data preparation only, never model capability']}
    coverage={}
    for component in sorted({r['component'] for r in rows}):
        subset=[r for r in rows if r['component']==component];train=[r for r in subset if r['split']=='train']
        labels=sorted({str(r['target']) for r in train}) if subset[0]['kind'] in ('label','number') else None
        coverage[component]={'kind':subset[0]['kind'],'splitExamples':{split:sum(r['split']==split for r in subset) for split in ('train','development','test')},
          'sourceGroups':len({r['sourceGroup'] for r in subset}),'trainingObservedLabels':labels,
          'allLabelsSupported':set(labels or [])==set(subset[0].get('labels',[])) if subset[0]['kind']=='label' else None,
          'validationStatus':'candidate_only_no_human_or_model_validation',
          'distinctTrainingTargets':len({digest(r['target']) for r in train}),
          'missingSplits':[split for split in ('train','development','test') if not any(r['split']==split for r in subset)],
          'readiness':'annotation_only' if subset[0]['kind']=='annotation_only' else 'not_ready_for_discrimination_or_generalization' if (not train or len({digest(r['target']) for r in train})<2 or not all(any(r['split']==split for r in subset) for split in ('train','development','test'))) else 'exploration_only_pending_semantic_review'}
    manifest['componentCoverage']=coverage
    exclusive(ROOT/'manifest.json',manifest);return manifest

if __name__=='__main__':print(json.dumps(write(),ensure_ascii=False))
