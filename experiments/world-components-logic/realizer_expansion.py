"""D-only authored contrastive data and metadata, never a runtime action policy.

Eighteen authored source candidates each have two related variants. Generated
reference wording is supervision draft, not human gold or independent evidence.
Training, generation, supervision and reporting stay in plan_training.py.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
from generate_dev_drafts import world,actor
from lab import canonical_bytes,guard_case,sha256_file
from run_pilot import digest
import action_plan as contract

BASE=Path(__file__).resolve().parent;ROOT=contract.ROOT
DATA=BASE/'data/realizer-expansion';ART=ROOT/'artifacts/world-components-logic'
BATCH='d-realizer-expanded36-r1';RUN='m02-realizer-expanded-20261104-r1'
HEAD='84d4d5f5a012f992bfc42fbd7a568788848ef872'
PROTOCOL=ROOT/'design/world-engine-reports/components-logic/realizer-expansion-protocol.md'
# Role is fixed before model outputs. Two variants never increase source groups.
TOOLS=(
 ('01','train_candidate','砚港标本室','梅岭',1,'叶片','苔片','镊子','夹起'),
 ('02','train_candidate','桐湾测绘台','宁澈',2,'粉笔条','炭笔条','夹钳','夹住'),
 ('03','train_candidate','暮石陶艺间','沈遥',1,'泥片','蜡片','木刮板','刮平'),
 ('04','train_candidate','沄浦藏品室','陶晏',2,'铜牌','木牌','细毛刷','刷净'),
 ('05','development_candidate','白溪印制所','谢竹',2,'版纸','垫纸','竹镊','夹取'),
 ('06','development_candidate','星棉纺线房','文芷',1,'线团','布卷','软刷','轻刷'),
)
RELATIONS=(
 ('07','train_candidate','澜堤调度屋','林昭','温笙','信号灯','请求','请查看信号灯'),
 ('08','train_candidate','栖露记录室','季亭','郁禾','记事册','递交',None),
 ('09','train_candidate','含章排演厅','黎韵','韩萤','节拍器','请求','请暂时停下节拍器'),
 ('10','train_candidate','青罗装订室','尹河','池岚','纸签','展示',None),
 ('11','development_candidate','泽川校验站','洛宁','袁青','测量尺','请求','请把测量尺递给我'),
 ('12','development_candidate','归岫值守间','桑榆','阮溪','交班单','递给',None),
)


def step(verb,objects=(),tools=(),destinations=(),recipients=(),utterance=None):
    return {'verb':verb,'objects':[{'kind':'item','id':i} for i in objects],
        'tools':[{'kind':'item','id':i} for i in tools],
        'destinations':[{'kind':k,'id':i} for k,i in destinations],
        'recipients':[{'kind':'character','id':i} for i in recipients],'utterance':utterance}


def source(num,role,coverage,variant,w,index,steps,reference,reason):
    case={'caseId':f'expanded-{num}-{variant}','sourceGroup':'d-expression-source-'+num,
        'anchorCase':variant=='a','derivedFrom':None if variant=='a' else f'expanded-{num}-a',
        'split':'training_candidate' if role=='train_candidate' else 'development_candidate',
        'purpose':'assistant_checked_expression_supervision_draft','task':'D02',
        'stageCut':'actor_opportunity_before_action_confirmation',
        'input':{'world':w,'actorId':'p'+str(index),'protagonistId':'p1',
                 'advance':{'inputText':'当前人物按自己的待办任务行动。' if index==1 else '先前主角的登记请求已处理。',
                            'intentStatus':'pending' if index==1 else 'consumed'},'confirmedPrefix':[]}}
    plan={'actorId':case['input']['actorId'],'kind':'act','mode':'attempt',
          'basis':['/world/characters/'+str(index-1),'/world/items','/advance/intentStatus'],'steps':steps}
    if not guard_case(case)['shouldCall']:raise ValueError('expanded source invalid')
    contract.validate_candidate(case,plan)
    return {'annotationId':case['caseId'],'sourceGroup':case['sourceGroup'],'role':role,'coverage':coverage,
        'sourceCase':case,'sourceInputSha256':digest(case['input']),'planDraft':plan,'planSha256':digest(plan),
        'expressionDraft':reference,'expressionSha256':digest(reference),'author':'assistant',
        'sourceAuthorship':'authored_D_source_with_template_composed_paired_annotation_variants',
        'sourceIndependence':'unverified','labelStatus':'assistant_prechecked_draft_not_human_gold','trainingEligible':False,
        'assistantPrecheck':reason,'variant':variant,'cohort':'new_expansion'}


def ordered_specs():
    # Explicit authored sequences and labels; never consulted by live inference.
    return (
      ('13','train_candidate','玲浦织造间','罗瑾',1,'线轴','布袋','收纳柜',
       ([step('收进',['item_1'],destinations=[('item','item_2')]),step('放置',['item_2'],destinations=[('place','loc_b')])],
        '尝试将线轴收进布袋，再把布袋放到收纳柜。'),
       ([step('放置',['item_2'],destinations=[('place','loc_b')]),step('收进',['item_1'],destinations=[('item','item_2')])],
        '尝试先把布袋放到收纳柜，再将线轴收进布袋。')),
      ('14','train_candidate','锦溪制香坊','许星',2,'木片','竹盘','晾架',
       ([step('拿起',['item_1']),step('放入',['item_1'],destinations=[('item','item_2')])],'尝试拿起木片，再把木片放入竹盘。'),
       ([step('拿起',['item_2']),step('放置',['item_2'],destinations=[('place','loc_b')])],'尝试拿起竹盘，再把竹盘放到晾架。')),
      ('15','train_candidate','竹汀称样处','梁墨',1,'量杯','盖子','托架',
       ([step('取下',['item_2']),step('放置',['item_2'],destinations=[('place','loc_b')])],'尝试取下盖子，再把盖子放到托架。'),
       ([step('拿起',['item_1']),step('移至',['item_1'],destinations=[('place','loc_b')])],'尝试拿起量杯，再把量杯移至托架。')),
      ('16','train_candidate','舟月封样台','纪辰',2,'纸包','封口夹','置物架',
       ([step('折好',['item_1']),step('夹住',['item_1'],tools=['item_2'])],'尝试折好纸包，再用封口夹夹住纸包。'),
       ([step('拿起',['item_2']),step('夹住',['item_1'],tools=['item_2'])],'尝试拿起封口夹，再用封口夹夹住纸包。')),
      ('17','development_candidate','栖虹器材角','唐薇',1,'镜片','收纳盒','软垫',
       ([step('取出',['item_1']),step('放置',['item_1'],destinations=[('place','loc_b')])],'尝试取出镜片，再把镜片放到软垫。'),
       ([step('合上',['item_2']),step('移动',['item_2'],destinations=[('place','loc_b')])],'尝试合上收纳盒，再把收纳盒移到软垫。')),
      ('18','development_candidate','远碧工艺桌','顾宁',2,'小匙','瓷托','器具架',
       ([step('收进',['item_1'],destinations=[('item','item_2')]),step('移至',['item_2'],destinations=[('place','loc_b')])],'尝试将小匙收进瓷托，再把瓷托移至器具架。'),
       ([step('摆放',['item_1'],destinations=[('place','loc_b')]),step('移至',['item_2'],destinations=[('place','loc_b')])],'尝试把小匙摆到器具架，再把瓷托移至器具架。')),
    )


def new_rows():
    rows=[]
    for num,role,setting,name,index,obj1,obj2,tool,verb in TOOLS:
        for variant,selected in zip(('a','b'),('item_1','item_2')):
            obj=obj1 if selected=='item_1' else obj2;reference=f'{name}尝试用{tool}{verb}{obj}。'
            people=[actor('田衡','loc_a','整理自己的记录。','不代替同伴行动。') for _ in range(2)]
            people[index-1]=actor(name,'loc_a',f'用{tool}{verb}{obj}。','认真按当前对象操作。')
            w=world(setting,'同一工作间的操作桌','同一工作间的备用架',[(obj1,'loc_a'),(obj2,'loc_a'),(tool,'p'+str(index))],people)
            rows.append(source(num,role,'object_tool_retention',variant,w,index,[step(verb,[selected],['item_3'])],reference,
                f'当前{name}持有{tool}；同组两条只换作用对象，必须保留{obj}，不能只写工具和动词。'))
    for num,role,setting,a,b,obj,verb,utterance in RELATIONS:
        for variant,index in (('a',1),('b',2)):
            name,other=(a,b) if index==1 else (b,a);target='p2' if index==1 else 'p1'
            if utterance:reference=f'{name}尝试向{other}提出请求：“{utterance}。”';task=f'向{other}请求：{utterance}。'
            elif verb=='展示':reference=f'{name}尝试向{other}展示{obj}。';task=f'向{other}展示{obj}。'
            else:reference=f'{name}尝试将{obj}递给{other}。';task=f'将{obj}递给{other}。'
            people=[actor(a,'loc_a','等候自己的下一项事务。','不代替同伴行动。'),actor(b,'loc_a','等候自己的下一项事务。','不代替同伴行动。')]
            people[index-1]=actor(name,'loc_a',task,'主动完成当前沟通事项。')
            w=world(setting,'协作桌','备用台',[(obj,'loc_a' if utterance else 'p'+str(index))],people)
            rows.append(source(num,role,'actor_recipient_direction',variant,w,index,
                [step(verb,[] if utterance else ['item_1'],recipients=[target],utterance=utterance)],reference,
                f'当前人物{name}，接收人{other}；同组镜像方向反转，不能把接收人或物品当行动人，请求不等于已经完成对方行动。'))
    for num,role,setting,name,index,obj1,obj2,dest,a,b in ordered_specs():
        for variant,(steps,suffix) in zip(('a','b'),(a,b)):
            people=[actor('汪霁','loc_a','维护自己的登记册。','不干扰同伴任务。') for _ in range(2)]
            people[index-1]=actor(name,'loc_a',suffix.replace('尝试','',1),'按给定先后顺序处理。')
            w=world(setting,'相邻操作区，目标工作点可直接步行抵达',dest,[(obj1,'loc_a'),(obj2,'loc_a')],people)
            if num=='15':w['items'][1]['position']={'containerId':'item_1','slot':'已松开的杯口'}
            if num=='17':w['items'][0]['position']={'containerId':'item_2','slot':'打开的盒内'}
            rows.append(source(num,role,'ordered_roles_and_containers',variant,w,index,steps,name+suffix,
                '同组变体改变步骤/对象/容器；逐步核对引用及先后顺序，输出只能表达尝试，不能把容器写成被移动物品自身。'))
    if len(rows)!=36 or len({r['sourceGroup'] for r in rows})!=18:raise ValueError('expanded counts drift')
    return rows


def rows():
    import plan_training as t
    return t.audited_candidate_rows()+new_rows()


def packet():return digest({'batchId':BATCH,'rows':rows()})


def groups(role):return list(dict.fromkeys(r['sourceGroup'] for r in rows() if r['role']==role))


def materials(write=False):
    data=rows();raw=b''.join(canonical_bytes(r)+b'\n' for r in data)
    train=[r for r in data if r['role']=='train_candidate'];dev=[r for r in data if r['role']=='development_candidate']
    if len(train)!=30 or len(dev)!=18 or set(groups('train_candidate'))&set(groups('development_candidate')):raise ValueError('expanded split drift')
    for g in {r['sourceGroup'] for r in new_rows()}:
        siblings=[r for r in data if r['sourceGroup']==g]
        if len(siblings)!=2 or len({r['role'] for r in siblings})!=1:raise ValueError('related variants split across roles')
    manifest={'schema':'jity-d-realizer-expanded-source-manifest-v1','batchId':BATCH,'sourceHead':HEAD,'packetSha256':packet(),
        'fileSha256':__import__('hashlib').sha256(raw).hexdigest(),'newSourceCandidateGroups':18,'newExamples':36,
        'trainingExamples':30,'developmentExamples':18,'trainingGroups':groups('train_candidate'),'developmentGroups':groups('development_candidate'),
        'newIndependentTrainingGroups':0,'humanReviewedGroups':0,'sourceIndependence':'unverified','formalEvaluationAllowed':False,
        'oldDevelopmentNeverUsedForTraining':True,'authoring':'18 authored scene candidates, two template-composed related variants each; not 36 independent sources',
        'sources':[{'annotationId':r['annotationId'],'sourceGroup':r['sourceGroup'],'role':r['role'],'annotationSha256':digest(r),
                    'sourceInputSha256':r['sourceInputSha256'],'planSha256':r['planSha256'],'expressionSha256':r['expressionSha256']} for r in data]}
    files={DATA/'candidates.jsonl':raw,DATA/'source-manifest.json':canonical_bytes(manifest)+b'\n'}
    for path,content in files.items():
        if path.exists() and path.read_bytes()!=content:raise ValueError('preserve expansion source: '+str(path))
        if not write and not path.exists():raise ValueError('expansion source missing')
    if write:
        for path,content in files.items():
            path.parent.mkdir(parents=True,exist_ok=True)
            if not path.exists():path.write_bytes(content)
    return manifest
