"""D-only controlled references for a learned plan-to-text realizer.

The model still writes verbs and syntax. This module binds existing IDs, copies
explicit literal speech and rejects incomplete references; it never repairs a
sentence, chooses an action or applies a world-state change.
"""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import re
import statistics
import subprocess
import time
import plan_training as t
import realizer_expansion as x
import realizer_search as search
from generate_dev_drafts import actor,world

ROOT=t.ROOT;ART=t.ART;RUN='m02-realizer-slots-20261105-r1'
DATA=t.BASE/'data/realizer-slots';BATCH='d-slots-new24-r1'
PROTOCOL=t.PROTOCOL.with_name('realizer-slots-protocol.md')
MANIFEST=ART/'m01-fitting'/f'{RUN}.manifest.json'
REVIEW=ART/'m01-fitting'/f'{RUN}.output-review.json'
PAGE='l3-22-realizer-slots';SEEDS=(42,7)
CONFIG={**t.CONFIG,'allowGroupedExamples':True,'steps':320,'learningRate':.003,'maxInputTokens':384}
CODE=tuple(dict.fromkeys((*t.CODE,'realizer_expansion.py','realizer_search.py','realizer_slots.py')))
MARKER=re.compile(r'【(?:人|物|地|话)[1-9][0-9]*】')


def bindings(row):
    original=t.realizer_payload(row);lookup=t.contract.lookup(row['sourceCase'])
    keys={('character',row['planDraft']['actorId'])}
    for step in row['planDraft']['steps']:
        for role in t.contract.ROLES:keys.update((r['kind'],r['id']) for r in step[role])
    labels={'character':'人','item':'物','place':'地'};counts={};entries=[]
    for kind,entity_id in sorted(keys):
        counts[kind]=counts.get(kind,0)+1;value=lookup[kind,entity_id]['name']
        if not isinstance(value,str) or not value:raise ValueError('reference name must be nonempty')
        entries.append({'marker':f'【{labels[kind]}{counts[kind]}】','kind':kind,'id':entity_id,'value':value,'type':'entity'})
    for index,step in enumerate(row['planDraft']['steps'],1):
        if step['utterance'] is not None:
            entries.append({'marker':f'【话{index}】','step':index,'value':step['utterance'],'type':'literal'})
    return {'sourceInputSha256':t.digest(row['sourceCase']['input']),'planSha256':t.digest(row['planDraft']),
            'originalPayloadSha256':t.digest(original),'entries':entries}


def slot_payload(row):
    # Keep every original name, verb, literal, typed ID, role and step in input.
    value=copy.deepcopy(t.realizer_payload(row));bound=bindings(row)
    value['表达要求']='保留全部动作和顺序；人物与实体使用引用，原话使用原话引用。'
    entities={(v['kind'],v['id']):v['marker'] for v in bound['entries'] if v['type']=='entity'}
    value['人物引用']=entities['character',row['planDraft']['actorId']]
    literals={v['step']:v['marker'] for v in bound['entries'] if v['type']=='literal'}
    for index,step in enumerate(value['计划'],1):
        for label in ('对象','工具','目的地','接收人'):
            for ref in step[label]:ref['引用']=entities[ref['种类'],ref['编号']]
        step['原话引用']=literals.get(index)
    return value


def original_payload(projected):
    value=copy.deepcopy(projected);value.pop('人物引用');value.pop('表达要求')
    for step in value['计划']:
        step.pop('原话引用')
        for label in ('对象','工具','目的地','接收人'):
            for ref in step[label]:ref.pop('引用')
    return value


def lexicalize(raw,bound):
    if not isinstance(raw,str) or not raw.strip():return {'status':'rejected','text':None,'problems':['empty_output']}
    mapping={entry['marker']:entry['value'] for entry in bound['entries']}
    found=MARKER.findall(raw);problems=[]
    unknown=sorted(set(found)-set(mapping));missing=sorted(set(mapping)-set(found))
    if unknown:problems.append('unknown_markers:'+','.join(unknown))
    if missing:problems.append('missing_markers:'+','.join(missing))
    residue=MARKER.sub('',raw)
    if '【' in residue or '】' in residue:problems.append('malformed_marker')
    for entry in bound['entries']:
        if entry['type']=='literal' and found.count(entry['marker'])!=1:problems.append('literal_reference_count:'+entry['marker'])
    if problems:return {'status':'rejected','text':None,'problems':problems,'usedMarkers':found}
    # One pass: an inserted name/literal can itself contain marker-like text.
    text=MARKER.sub(lambda match:mapping[match.group()],raw)
    return {'status':'rendered_not_semantically_approved','text':text,'problems':[],
            'usedMarkers':found,'coverage':'reference_presence_only_not_verb_step_or_direction_approval'}


def annotation_projection(row):
    """Bind authored label spans to IDs; never used by inference/relexicalization.

    The D authoring helper adds （甲/乙/丙） to registered character names, while
    its existing reference drafts omit that display suffix. Declare those known
    authoring aliases explicitly, retain the old reference bytes and return a
    reversible span trace. Runtime always restores the complete registered name.
    """
    bound=bindings(row);values={};reference=row['expressionDraft'];trace=[]
    for entry in bound['entries']:
        aliases=[entry['value']]
        if entry.get('kind')=='character':
            for suffix in ('（甲）','（乙）','（丙）'):
                if entry['value'].endswith(suffix):aliases.append(entry['value'][:-len(suffix)])
        for value in aliases:
            if not value or value in values:raise ValueError('ambiguous automatic target spans; explicit annotation required')
            if entry['type']=='literal' and reference.count(value)!=1:raise ValueError('ambiguous literal span')
            if entry['type']=='entity' and any(value in step['verb'] for step in row['planDraft']['steps']):raise ValueError('entity name overlaps lexical verb')
            values[value]=entry['marker']
    pattern=re.compile('|'.join(re.escape(v) for v in sorted(values,key=lambda value:(-len(value),value))))
    def replace(match):
        marker=values[match.group()];trace.append({'marker':marker,'sourceText':match.group(),'start':match.start(),'end':match.end()});return marker
    result=pattern.sub(replace,reference)
    restored=lexicalize(result,bound)
    if restored['text'] is None:raise ValueError('automatic target omitted a required reference')
    spans=iter(trace)
    def reverse(match):
        span=next(spans)
        if span['marker']!=match.group():raise ValueError('annotation span order mismatch')
        return span['sourceText']
    if MARKER.sub(reverse,result)!=reference:raise ValueError('original label span roundtrip failed')
    return {'annotationId':row['annotationId'],'sourceGroup':row['sourceGroup'],'role':row['role'],
        'originalAnnotationSha256':t.digest(row),'originalReferenceSha256':t.digest(reference),
        'target':result,'targetSha256':t.digest(result),'canonicalReference':restored['text'],
        'canonicalReferenceSha256':t.digest(restored['text']),'spanTrace':trace,'bindingSha256':t.digest(bound)}


def slot_target(row):return annotation_projection(row)['target']


def abstract_shape(row):
    p=slot_payload(row)
    return t.digest({'actor':p['人物引用'],'mode':p['语气'],'steps':[
        {'verb':step['动作'],'speech':step['原话引用'],**{k:[r['引用'] for r in step[k]] for k in ('对象','工具','目的地','接收人')}}
        for step in p['计划']]})


def authored(number,variant,family,w,index,steps,reference,reason):
    row=x.source('slots-'+number,'development_candidate',family,variant,w,index,steps,reference,reason)
    row.update(annotationId=f'slots-probe-{number}-{variant}',sourceGroup='d-slots-source-'+number,
        sourceAuthorship='new_D_authored_probe_scenes_with_paired_variants_not_verified_independent_sources',cohort='new_slots_probe')
    row['sourceCase'].update(caseId=row['annotationId'],sourceGroup=row['sourceGroup'],
        purpose='new_controlled_reference_expression_probe_not_training',derivedFrom=None if variant=='a' else f'slots-probe-{number}-a')
    return row


def new_rows():
    """Authoring only; references are drafts and never runtime action templates."""
    rows=[]
    tools=(
      ('01','岑禾','晴屿检验间',1,'陶环','玻璃钮','长柄镊','夹起'),
      ('02','邵沐','竹岚纤维室',2,'麻线结','棉线结','细绒刷','轻刷'),
      ('03','容霁','白砾修整台',1,'石纹片','竹纹片','软布','轻轻擦拭'),
      ('04','许棠','岚桥装配室',2,'铜扣','银扣','木夹','夹住'))
    for number,name,setting,index,one,two,tool,verb in tools:
        for variant,item,obj in (('a','item_1',one),('b','item_2',two)):
            people=[actor('申珂','loc_a','整理自己的票据。','只处理自己的事务。') for _ in range(2)]
            people[index-1]=actor(name,'loc_a',f'用{tool}{verb}{obj}。','准确区分待处理对象。')
            w=world(setting,'当前操作台','备用架',[(one,'loc_a'),(two,'loc_a'),(tool,'p'+str(index))],people)
            rows.append(authored(number,variant,'new_object_tool_and_modifier',w,index,
                [x.step(verb,[item],['item_3'])],f'{name}尝试用{tool}{verb}{obj}。',
                '区分对象与工具，同组只换对象；轻刷／轻轻限定须保留，不能把工具写成对象。'))
    relations=(
      ('05','桑苒','黎越','羽川登记站','刻度样卡','请求','请把刻度样卡递给我'),
      ('06','秦舟','杜宁','清石交接亭','值守牌','递给',None),
      ('07','孟汀','苏砚','青谷测记室','编号夹板','展示',None),
      ('08','林萦','白朔','云汀讨论间','草图册','展示',None))
    for number,a,b,setting,obj,verb,utterance in relations:
        for variant,index in (('a',1),('b',2)):
            name,other=(a,b) if index==1 else (b,a);recipient='p2' if index==1 else 'p1'
            people=[actor(a,'loc_a','等待自己的交接事项。','不代替别人发言。'),actor(b,'loc_a','等待自己的交接事项。','不代替别人发言。')]
            recipients=[recipient];others=other
            if number=='08':
                people.append(actor('范澄','loc_a','参与查看草图。','先听完同伴说明。'));recipients.append('p3');others=other+'和范澄'
            if utterance:reference=f'{name}尝试向{other}提出请求：“{utterance}。”';task=f'向{other}请求：{utterance}。'
            elif verb=='展示':reference=f'{name}尝试向{others}展示{obj}。';task=f'向{others}展示{obj}。'
            else:reference=f'{name}尝试将{obj}递给{other}。';task=f'将{obj}递给{other}。'
            people[index-1]=actor(name,'loc_a',task,'准确表达当前沟通对象。')
            w=world(setting,'交接桌','资料架',[(obj,'loc_a' if utterance else 'p'+str(index))],people)
            rows.append(authored(number,variant,'new_actor_recipient_and_literal',w,index,
                [x.step(verb,[] if utterance else ['item_1'],recipients=recipients,utterance=utterance)],reference,
                '镜像反转人物方向；请求原话逐字保留，08须覆盖两位接收人，不把请求写成对方已经递交。'))
    sequences=(
      ('09','齐萝','江叶试件台',1,'试块','布盒','低架',
       ([x.step('拿起',['item_1']),x.step('放入',['item_1'],destinations=[('item','item_2')])],'尝试拿起试块，再把试块放入布盒。'),
       ([x.step('合上',['item_2']),x.step('移至',['item_2'],destinations=[('place','loc_b')])],'尝试合上布盒，再把布盒移至低架。')),
      ('10','何砚','棠溪存放处',2,'短绳','纸筒','横架',
       ([x.step('卷好',['item_1']),x.step('收进',['item_1'],destinations=[('item','item_2')]),x.step('放置',['item_2'],destinations=[('place','loc_b')])],'尝试卷好短绳，再把短绳收进纸筒，最后把纸筒放到横架。'),
       ([x.step('放置',['item_2'],destinations=[('place','loc_b')]),x.step('卷好',['item_1']),x.step('收进',['item_1'],destinations=[('item','item_2')])],'尝试先把纸筒放到横架，再卷好短绳，最后把短绳收进纸筒。')),
      ('11','闻柚','榆舟分拣桌',1,'薄片','浅盘','边台',
       ([x.step('取出',['item_1']),x.step('放置',['item_1'],destinations=[('item','item_2')])],'尝试取出薄片，再把薄片放到浅盘。'),
       ([x.step('放置',['item_2'],destinations=[('place','loc_b')]),x.step('取出',['item_1'])],'尝试先把浅盘放到边台，再取出薄片。')),
      ('12','蒋荞','松岩样本架',2,'木签','网袋','高台',
       ([x.step('拿起',['item_1','item_2']),x.step('放置',['item_1','item_2'],destinations=[('place','loc_b')])],'尝试拿起木签和网袋，再把木签和网袋放到高台。'),
       ([x.step('拿起',['item_2']),x.step('收进',['item_1'],destinations=[('item','item_2')]),x.step('放置',['item_2'],destinations=[('place','loc_b')])],'尝试拿起网袋，再把木签收进网袋，最后把网袋放到高台。')))
    for number,name,setting,index,one,two,dest,a,b in sequences:
        for variant,(steps,suffix) in zip(('a','b'),(a,b)):
            people=[actor('江衡','loc_a','整理自己的名册。','不改变同伴的待办。') for _ in range(2)]
            people[index-1]=actor(name,'loc_a',suffix.replace('尝试','',1),'遵循给定先后顺序，不把物品与容器混用。')
            w=world(setting,'当前工作区',dest,[(one,'loc_a'),(two,'loc_a')],people)
            if number=='09':w['items'][1]['appearance']='布盒敞开，盒盖可合上；内部有足够空间容纳试块。'
            if number=='10':w['items'][1]['appearance']='纸筒开口可用，卷好的短绳能放入其中。'
            if number=='11':
                w['items'].append({'id':'item_3','name':'打开的取片槽','appearance':'槽口已打开且薄片可取出。','position':{'containerId':'loc_a','slot':'台面'}})
                w['items'][0]['position']={'containerId':'item_3','slot':'槽内'}
            rows.append(authored(number,variant,'new_ordered_roles_and_containers',w,index,steps,name+suffix,
                '逐步核对全部对象和目的地；含新动词组合、三步、双对象及次序变化，不因引用齐全就签动作完整。'))
    if len(rows)!=24 or len({r['sourceGroup'] for r in rows})!=12:raise ValueError('new slot probe count drift')
    return rows


def train_rows():return [r for r in x.rows() if r['role']=='train_candidate']
def evaluation_rows():return [r for r in x.rows() if r['role']=='development_candidate']+new_rows()


def source_materials(write=False):
    train=train_rows();rows=new_rows();old=x.rows();shapes={abstract_shape(r) for r in train}
    if {t.digest(r['sourceCase']['input']) for r in old}&{r['sourceInputSha256'] for r in rows}:raise ValueError('exact old input reused as new source')
    for row in train+evaluation_rows():
        if original_payload(slot_payload(row))!=t.realizer_payload(row):raise ValueError('slot input lost original plan information')
        slot_target(row)
    manifest={'schema':'jity-d-realizer-slot-probe-sources-v1','batchId':BATCH,'sourceHead':'da5cfb625e34730131d235da2715c2c380332676',
        'newExamples':24,'newSourceCandidateGroups':12,'newIndependentVerifiedGroups':0,'formalEvaluationAllowed':False,
        'humanLabelReviews':0,'sourceIndependence':'unverified','labelProvenance':'assistant_checked_draft_not_human_gold',
        'oldTrainingManifestSha256':t.sha256_file(x.DATA/'source-manifest.json'),'oldSourceExactInputOverlap':0,
        'sources':[{'annotationId':r['annotationId'],'sourceGroup':r['sourceGroup'],'annotationSha256':t.digest(r),
                    'sourceInputSha256':r['sourceInputSha256'],'planSha256':r['planSha256'],'expressionSha256':r['expressionSha256'],
                    'abstractReferenceVerbPatternSeenInTraining':abstract_shape(r) in shapes,'assistantPrecheck':r['assistantPrecheck']} for r in rows]}
    projections=[annotation_projection(r) for r in train]
    manifest['trainingProjectionSha256']=t.digest(projections)
    manifest['annotationAliasPolicy']='D_authoring_display_suffix_aliases_only_in_training_span_conversion_runtime_restores_full_registered_names'
    files={DATA/'candidates.jsonl':b''.join(t.canonical_bytes(r)+b'\n' for r in rows),DATA/'source-manifest.json':t.canonical_bytes(manifest)+b'\n',
           DATA/'training-projection.jsonl':b''.join(t.canonical_bytes(r)+b'\n' for r in projections)}
    for path,raw in files.items():
        if path.exists() and path.read_bytes()!=raw:raise ValueError('preserve slot source material')
        if not write and not path.exists():raise ValueError('slot sources missing')
    if write:
        DATA.mkdir(parents=True,exist_ok=True)
        for path,raw in files.items():
            if not path.exists():
                with path.open('xb') as stream:stream.write(raw)
    return manifest


def baseline_source(seed):
    summary=t.run.read_json(ART/'l3-21-realizer-grid-summary.json')
    source_id=summary['selection']['selected']['candidateId'] if seed==42 else summary['confirmationScores'][0]['candidateId']
    run=next(r for r in summary['trajectories'] if any(c['candidateId']==source_id for c in r['candidates']))
    full=search.observed(run['runId']);candidate=next(c for c in full['candidates'] if c['candidateId']==source_id)
    config=candidate['config']
    if (config['seed']!=seed or config['learningRate']!=.003 or config['weightDecay']!=.01 or config['steps']!=320):raise ValueError('frozen natural baseline config drift')
    ids={r['annotationId'] for r in evaluation_rows() if not r['annotationId'].startswith('slots-probe-')}
    predictions={p['annotationId']:{k:p[k] for k in ('annotationId','inputText','inputTokenIds','tokenIds','raw')} for p in candidate['predictions'] if p['annotationId'] in ids}
    if len(predictions)!=18:raise ValueError('frozen baseline regression outputs missing')
    return {'sourceRunId':run['runId'],'sourceRecordSha256':full['recordSha256'],
            'checkpoint':candidate['adapter'],'config':config,'regressionPacketSha256':t.digest(predictions)},predictions


def tokenizer_materials(write=False):
    path=ART/'l3-22-slots-tokenizer-check.json'
    if not write:
        result=t.run.read_json(path)
        if result['dataSha256']!=t.digest(train_rows()+evaluation_rows()) or result['config']!=CONFIG:raise ValueError('slot tokenizer data/config drift')
        return result
    from transformers import T5Tokenizer
    model=t.observe_m02(ROOT);tokenizer=T5Tokenizer.from_pretrained(ROOT/model['directory'],local_files_only=True,extra_ids=0,legacy=True)
    examples=[]
    for row in train_rows()+evaluation_rows():
        normal=t.tokenize_example(tokenizer,row,CONFIG)
        slots=t.tokenize_example(tokenizer,row,CONFIG,payload_builder=slot_payload,target_text=slot_target(row))
        for entry in bindings(row)['entries']:
            ids=tokenizer.encode(entry['marker'],add_special_tokens=False,truncation=False)
            if tokenizer.unk_token_id in ids or tokenizer.decode(ids,skip_special_tokens=True)!=entry['marker']:raise ValueError('marker tokenizer does not roundtrip')
        examples.append({'annotationId':row['annotationId'],'role':row['role'],'natural':normal,'slots':slots,
            'naturalInputUnknownTokens':normal['inputIds'].count(tokenizer.unk_token_id),
            'slotInputUnknownTokens':slots['inputIds'].count(tokenizer.unk_token_id)})
    result={'schema':'jity-d-slot-tokenizer-check-v1','dataSha256':t.digest(train_rows()+evaluation_rows()),
        'config':CONFIG,'examples':examples,'neuralForwardCalls':0,'neuralModelLoaded':False,
        'maxNaturalInputTokens':max(len(e['natural']['inputIds']) for e in examples),
        'maxSlotInputTokens':max(len(e['slots']['inputIds']) for e in examples),
        'maxSlotTargetTokens':max(len(e['slots']['labels']) for e in examples),
        'modelIdentity':model,'formalEvaluationAllowed':False}
    t.exclusive(path,result);return result


def authorization():
    return {'instruction':'开始','context':'用户同意先验证角色引用表达及程序按既有ID填回名称，和当前最佳表达器同一批新题对照。',
        'scope':'one_controlled_reference_probe_two_fixed_seeds_no_formal_claims','humanLabelReviews':0,
        'labelProvenance':'assistant_checked_draft_not_human_gold','sourceIndependence':'unverified','formalEvaluationAllowed':False}


def prepare():
    if MANIFEST.exists():raise FileExistsError('preserve slot manifest')
    source_materials();tokenizer=tokenizer_materials();train=train_rows();evaluation=evaluation_rows()
    manifest={'schema':'jity-d-realizer-slots-manifest-v1','runId':RUN,'preparedAt':t.timestamp(),
        'sourceHead':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'authorization':authorization(),'config':CONFIG,'seeds':list(SEEDS),
        'trainSha256':t.digest(train),'evaluationSha256':t.digest(evaluation),
        'sourceFiles':{str(p.relative_to(ROOT)):t.sha256_file(p) for p in (DATA/'candidates.jsonl',DATA/'source-manifest.json',DATA/'training-projection.jsonl')},
        'tokenizerCheckSha256':t.sha256_file(ART/'l3-22-slots-tokenizer-check.json'),
        'protocolSha256':t.sha256_file(PROTOCOL),
        'baselines':{str(seed):baseline_source(seed)[0] for seed in SEEDS},
        'model':tokenizer['modelIdentity'],'environment':t.observe_environment(ROOT),
        'code':{str((t.BASE/name).relative_to(ROOT)):t.sha256_file(t.BASE/name) for name in CODE}}
    if not manifest['model']['allSixFilesFullyRehashedAndVerified'] or not manifest['environment']['registeredVersionsMatch']:raise ValueError('slot model/environment invalid')
    t.exclusive(MANIFEST,manifest)
    for seed in SEEDS:
        run_id=f'{RUN}-s{seed}';pp,rp=t.old.paths(run_id)
        if pp.exists() or rp.exists():raise FileExistsError('preserve original slot plan')
        t.exclusive(pp,{'schema':'jity-d-realizer-slots-plan-v1','runId':run_id,'seed':seed,
            'preparedAt':t.timestamp(),'manifestSha256':t.sha256_file(MANIFEST),
            'environment':manifest['environment'],'config':{**CONFIG,'seed':seed},
            'cases':[{'caseId':'fit-and-paired-expression'}],'arms':['compare'],
            'purpose':'frozen_natural_vs_fresh_controlled_reference_realizer',
            'formalEvaluationAllowed':False,'fullRequestMeasured':False})
    return MANIFEST


def verify(plan,*,historical=False):
    manifest=t.run.read_json(MANIFEST);seed=plan['seed']
    if (manifest['schema']!='jity-d-realizer-slots-manifest-v1' or manifest['authorization']!=authorization()
            or manifest['config']!=CONFIG or manifest['seeds']!=list(SEEDS)
            or manifest['trainSha256']!=t.digest(train_rows()) or manifest['evaluationSha256']!=t.digest(evaluation_rows())):raise ValueError('slot scope/config/data drift')
    if (seed not in SEEDS or plan['runId']!=f'{RUN}-s{seed}' or plan['schema']!='jity-d-realizer-slots-plan-v1'
            or plan['manifestSha256']!=t.sha256_file(MANIFEST) or plan.get('environment')!=manifest['environment']
            or plan['config']!={**CONFIG,'seed':seed} or plan['formalEvaluationAllowed'] is not False
            or plan['fullRequestMeasured'] is not False or plan['purpose']!='frozen_natural_vs_fresh_controlled_reference_realizer'
            or plan['cases']!=[{'caseId':'fit-and-paired-expression'}] or plan['arms']!=['compare']):raise ValueError('slot execution plan drift')
    source_materials();tokenizer_materials()
    if manifest['tokenizerCheckSha256']!=t.sha256_file(ART/'l3-22-slots-tokenizer-check.json'):raise ValueError('slot tokenizer evidence drift')
    for name,h in manifest['sourceFiles'].items():
        if t.sha256_file(ROOT/name)!=h:raise ValueError('slot source file drift')
    for name,h in manifest['code'].items():
        if historical:t.verify_historical_file(ROOT/name,h)
        elif t.sha256_file(ROOT/name)!=h:raise ValueError('slot executed code drift')
    if historical:t.verify_historical_file(PROTOCOL,manifest['protocolSha256'])
    elif t.sha256_file(PROTOCOL)!=manifest['protocolSha256']:raise ValueError('slot protocol drift')
    baseline,_=baseline_source(seed)
    if manifest['baselines'][str(seed)]!=baseline:raise ValueError('slot frozen baseline drift')
    if not historical:
        if t.sha256_file(ROOT/baseline['checkpoint']['path'])!=baseline['checkpoint']['sha256']:raise ValueError('slot baseline weight file drift')
        if manifest['model']!=t.observe_m02(ROOT) or manifest['environment']!=t.observe_environment(ROOT):raise ValueError('slot runtime identity drift')
    return manifest


def expression_units(torch,model,tokenizer,rows,phase,checkpoint,config):
    units=[]
    for row in rows:
        start=time.perf_counter();checkpoint('expression_unit_started',{'phase':phase,'annotationId':row['annotationId']})
        bind_start=time.perf_counter();bound=bindings(row) if phase=='slots' else None;binding_ms=(time.perf_counter()-bind_start)*1000
        prediction=t.generate_expressions(torch,model,tokenizer,[row],phase,checkpoint,config,
            payload_builder=slot_payload if phase=='slots' else None)[0]
        render_start=time.perf_counter()
        result=lexicalize(prediction['raw'],bound) if phase=='slots' else {'status':'natural_model_text_not_semantically_approved','text':prediction['raw'],'problems':[]}
        render_ms=(time.perf_counter()-render_start)*1000
        if not prediction['eos']:result={'status':'rejected','text':None,'problems':['model_incomplete:'+prediction['stopStatus']]}
        unit={'phase':phase,'annotationId':row['annotationId'],'sourceGroup':row['sourceGroup'],
            'cohort':'new_probe' if row['annotationId'].startswith('slots-probe-') else 'old_regression',
            'prediction':prediction,'bindings':bound,'rendering':result,'bindingMs':binding_ms,'renderMs':render_ms,
            'modelOutputCharacters':len(prediction['raw']),'renderedCharacters':len(result['text']) if result['text'] is not None else None}
        checkpoint('expression_unit_result',unit)
        timing={'phase':phase,'annotationId':row['annotationId'],'elapsedThroughResultMs':(time.perf_counter()-start)*1000}
        checkpoint('expression_unit_timing',timing)
        unit.update(timing,elapsedIncludingTelemetryMs=(time.perf_counter()-start)*1000);units.append(unit)
    return units


def worker(path):
    plan=t.run.read_json(path);config=plan['config'];_,out=t.old.paths(plan['runId']);slots=t.run.planned_slots(plan,('compare',))
    report={'schema':'jity-d-realizer-slots-record-v1','runId':plan['runId'],'planSha256':t.sha256_file(path),
        'status':'running','stages':[],'attempts':[],'attemptSlots':slots,'activeAttempt':None,'forwardAttempts':[],
        'formalEvaluationAllowed':False,'fullRequestMeasured':False}
    t.exclusive(out,report);stage=lambda n,f:t.run.record_stage(report,out,n,f)
    try:
        manifest=stage('verify',lambda:verify(plan));train=train_rows();evaluation=evaluation_rows();baseline=manifest['baselines'][str(plan['seed'])]
        import torch
        from transformers import T5ForConditionalGeneration,T5Tokenizer
        torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.manual_seed(plan['seed'])
        directory=ROOT/manifest['model']['directory']
        tokenizer=stage('tokenizer',lambda:T5Tokenizer.from_pretrained(directory,local_files_only=True,extra_ids=0,legacy=True))
        model=stage('source_model',lambda:T5ForConditionalGeneration.from_pretrained(directory,local_files_only=True,weights_only=True).eval())
        source_hash=t.old.tensor_hash(model.state_dict());report['topology']=t.install_lora(torch,model,config['rank'],config['alpha'])
        initial=t.adapter_state(model);phase={'name':'natural'};counts={};encoder_counts={}
        def increment(counter):counter[phase['name']]=counter.get(phase['name'],0)+1
        mh=model.register_forward_pre_hook(lambda *_:increment(counts));eh=model.get_encoder().register_forward_pre_hook(lambda *_:increment(encoder_counts))
        with t.run.AppendJournal(out.with_suffix('.journal.jsonl'),report['planSha256']) as journal:
            journal.append('begin',{'runId':plan['runId'],'slots':slots})
            a={**slots[0],'status':'started','startedMonotonicNs':time.monotonic_ns(),'checkpoints':[]}
            report['activeAttempt']=a;journal.append('attempt_start',a)
            def checkpoint(name,payload):
                value={k:a[k] for k in ('arm','caseId','repeat')};value.update(name=name,payload=payload)
                journal.append('attempt_checkpoint',value);a['checkpoints'].append(copy.deepcopy(value))
            identity=baseline['checkpoint'];t.restore_adapter(model,torch.load(ROOT/identity['path'],map_location='cpu',weights_only=True))
            if t.old.tensor_hash(t.adapter_state(model))!=identity['tensorSha256'] or source_hash!=identity['sourceTensorSha256']:raise ValueError('slot baseline tensor/source mismatch')
            checkpoint('baseline_adapter_loaded',identity)
            a['naturalUnits']=expression_units(torch,model,tokenizer,evaluation,'natural',checkpoint,config)
            t.restore_adapter(model,initial)
            if t.old.tensor_hash(t.adapter_state(model))!=t.old.tensor_hash(initial):raise ValueError('slot fresh initialization mismatch')
            checkpoint('fresh_adapter_restored',{'tensorSha256':t.old.tensor_hash(initial)})
            examples=[t.tokenize_example(tokenizer,row,config,payload_builder=slot_payload,target_text=slot_target(row)) for row in train]
            checkpoint('training_examples_encoded',{'examples':examples,'sourceAnnotationSha256s':[t.digest(row) for row in train]})
            phase['name']='training';a['losses']=t.fit_encoded_adapter(torch,model,examples,tokenizer.pad_token_id,config,checkpoint)
            a['adapter']=t.save_reload_adapter(torch,model,ROOT/'.local/world-components-logic/realizer-adapters'/plan['runId'],source_hash,checkpoint)
            checkpoint('adapter_frozen',a['adapter']);phase['name']='slots'
            a['slotUnits']=expression_units(torch,model,tokenizer,evaluation,'slots',checkpoint,config)
            checkpoint('model_forward_accounting',{'modelTopForwardCallsByPhase':counts,'encoderForwardCallsByPhase':encoder_counts})
            if (t.old.tensor_hash(t.base_state(model))!=source_hash or t.old.tensor_hash(t.adapter_state(model))!=a['adapter']['tensorSha256']
                    or any(p.grad is not None for p in model.parameters() if not p.requires_grad)):raise ValueError('slot run modified frozen source/adapter')
            a.update(status='complete',settledAt=t.timestamp());journal.append('attempt_result',a)
            timing={k:a[k] for k in ('arm','caseId','repeat')};timing.update(resultJournalMs=0.,snapshotEndMs=0.,elapsedThroughResultMs=(time.monotonic_ns()-a['startedMonotonicNs'])/1e6)
            journal.append('attempt_settled',timing);a.update(timing);report['attempts']=[a];report['activeAttempt']=None
        mh.remove();eh.remove()
        report.update(status='diagnostic_completed',sourceWeightsUnchanged=True,sourceFilesUnchanged=t.observe_m02(ROOT)==manifest['model'],unexecutedAttempts=0)
    except Exception as error:report.update(status='failed',error={'type':type(error).__name__,'message':str(error)})
    finally:t.save(out,report)
    return 0 if report['status']=='diagnostic_completed' else 1


def execute(path):return t.run.execute_plan(path,paths=t.old.paths,verify=verify,worker_script=Path(__file__),settle_stages=t.old.settle_stages,arms=('compare',))


def observed(seed):
    pp,rp=t.old.paths(f'{RUN}-s{seed}');plan=t.run.read_json(pp);verify(plan,historical=True)
    record_path=search.available(rp);record=t.run.read_json(record_path);journal=search.available(rp.with_suffix('.journal.jsonl'))
    if record['planSha256']!=t.sha256_file(pp):raise ValueError('slot plan identity drift')
    replay=copy.deepcopy(record);t.run.reconcile_journal(replay,journal,'read_only_slot_check')
    replay['journalRecovery']['sha256']=search.raw_sha(journal)
    if replay['attempts']!=record['attempts'] or replay['journalRecovery']!=record['journalRecovery']:raise ValueError('slot journal reconstruction differs')
    if (record['status']!='diagnostic_completed' or record['supervisor']['exitCode']!=0 or record['supervisor']['stopReason'] is not None
            or record['formalEvaluationAllowed'] is not False or not record['sourceFilesUnchanged'] or not record['sourceWeightsUnchanged']):raise ValueError('slot run incomplete or scope invalid')
    if len(record['attempts'])!=1 or record['attempts']!=record['attemptSlots']:raise ValueError('slot trajectory missing')
    a=record['attempts'][0];events=a['checkpoints'];payloads=lambda name:[e['payload'] for e in events if e['name']==name]
    train=train_rows();evaluation=evaluation_rows();lookup={row['annotationId']:row for row in evaluation}
    starts=payloads('training_step_started');steps=payloads('training_step_settled')
    if [e['step'] for e in starts]!=list(range(1,321)) or [e['step'] for e in steps]!=list(range(1,321)) or a['losses']!=[e['loss'] for e in steps]:raise ValueError('slot training step ledger mismatch')
    allowed={(r['annotationId'],r['sourceGroup']) for r in train}
    for item in starts:
        if len(item['annotationIds'])!=2 or len(item['sourceGroups'])!=2 or any(pair not in allowed for pair in zip(item['annotationIds'],item['sourceGroups'])):raise ValueError('slot development example reached gradient')
    encoded=payloads('training_examples_encoded')[0]
    if encoded['sourceAnnotationSha256s']!=[t.digest(row) for row in train] or len(encoded['examples'])!=30:raise ValueError('slot encoded training coverage drift')
    tokenizer=tokenizer_materials();expected={e['annotationId']:e['slots'] for e in tokenizer['examples']}
    if encoded['examples']!=[expected[row['annotationId']] for row in train]:raise ValueError('slot training target/input differs from frozen tokenizer check')
    outputs=payloads('generation_output');timings=payloads('generation_timing')
    results=payloads('expression_unit_result');unit_timings=payloads('expression_unit_timing');begun=payloads('expression_unit_started')
    if len(outputs)!=84 or len(payloads('generation_started'))!=84 or len(results)!=84 or len(unit_timings)!=84 or len(begun)!=84:raise ValueError('slot generation or pipeline unit omitted')
    units=a['naturalUnits']+a['slotUnits']
    if len(units)!=84 or [(u['phase'],u['annotationId']) for u in units]!=[(phase,row['annotationId']) for phase in ('natural','slots') for row in evaluation]:raise ValueError('slot output source order drift')
    for phase in ('natural','slots'):
        search.validate_generation_snapshot([u['prediction'] for u in units if u['phase']==phase],[p for p in outputs if p['phase']==phase],timings)
    for unit,result,timing,begin in zip(units,results,unit_timings,begun):
        row=lookup[unit['annotationId']];phase=unit['phase'];key=(phase,unit['annotationId'])
        if key!=(result['phase'],result['annotationId']) or key!=(timing['phase'],timing['annotationId']) or key!=(begin['phase'],begin['annotationId']):raise ValueError('slot pipeline event identity mismatch')
        if {k:v for k,v in unit.items() if k not in ('elapsedThroughResultMs','elapsedIncludingTelemetryMs')}!=result:raise ValueError('slot unit snapshot differs')
        if unit['elapsedThroughResultMs']!=timing['elapsedThroughResultMs'] or unit['elapsedIncludingTelemetryMs']<unit['elapsedThroughResultMs'] or unit['elapsedThroughResultMs']<unit['prediction']['elapsedIncludingOutputJournalMs']:raise ValueError('slot full expression timing invalid')
        p=unit['prediction'];payload=slot_payload(row) if phase=='slots' else t.realizer_payload(row)
        if (p['inputText']!=t.payload_text(payload) or p['inputSha256']!=t.digest(payload)
                or p['inputTokenIds']!=next(e['slots' if phase=='slots' else 'natural']['inputIds'] for e in tokenizer['examples'] if e['annotationId']==row['annotationId'])
                or p['sourceGroup']!=row['sourceGroup'] or p['modelTopForwardCalls']!=len(p['tokenIds'])-1 or p['eos']!=(p['tokenIds'][-1]==1)):raise ValueError('slot prediction input/output identity drift')
        bound=bindings(row) if phase=='slots' else None
        rendered=lexicalize(p['raw'],bound) if phase=='slots' else {'status':'natural_model_text_not_semantically_approved','text':p['raw'],'problems':[]}
        if not p['eos']:rendered={'status':'rejected','text':None,'problems':['model_incomplete:'+p['stopStatus']]}
        if unit['bindings']!=bound or unit['rendering']!=rendered:raise ValueError('slot reference restoration differs from original model text')
    counts=payloads('model_forward_accounting')[0]
    if counts['encoderForwardCallsByPhase']!={'natural':42,'training':320,'slots':42} or counts['modelTopForwardCallsByPhase']!={'training':320,**{phase:sum(u['prediction']['modelTopForwardCalls'] for u in units if u['phase']==phase) for phase in ('natural','slots')}}:raise ValueError('slot forward ledger mismatch')
    baseline,previous=baseline_source(seed)
    if payloads('baseline_adapter_loaded')!=[baseline['checkpoint']] or not payloads('fresh_adapter_restored') or payloads('adapter_frozen')!=[a['adapter']]:raise ValueError('slot baseline/reset/freeze checkpoint missing')
    for unit in a['naturalUnits']:
        if unit['annotationId'] in previous:
            p=unit['prediction']
            if {k:p[k] for k in previous[unit['annotationId']]}!=previous[unit['annotationId']]:raise ValueError('natural frozen regression no longer reproduces')
    return {'seed':seed,'runId':plan['runId'],'units':units,'trainingSteps':len(steps),'trainingSampleUses':2*len(starts),
        'generationCalls':len(outputs),'losses':a['losses'],'adapter':a['adapter'],'baseline':baseline,'historicalRegressionOutputsReproduced':18,
        'modelForwardCounts':counts,'supervisor':record['supervisor'],'recordSha256':search.raw_sha(record_path),'journalSha256':search.raw_sha(journal),
        'recordArtifact':str(record_path.relative_to(ART)),'journalArtifact':str(journal.relative_to(ART)),
        'recordArtifactSha256':t.sha256_file(record_path),'journalArtifactSha256':t.sha256_file(journal)}


def review_key(unit):return unit['annotationId'],unit['phase'],t.digest(unit['prediction']['raw']),t.digest(unit['rendering']['text'])


def reviewed_runs():
    runs=[observed(seed) for seed in SEEDS];review=t.run.read_json(REVIEW)
    if (review.get('schema')!='jity-d-slot-assistant-output-review-v1' or review.get('reviewer')!='assistant'
            or review.get('formalEvaluationAllowed') is not False or review.get('recordHashes')!={r['runId']:r['recordSha256'] for r in runs}):raise ValueError('slot review identity/scope drift')
    expected={review_key(u) for r in runs for u in r['units']};decisions={}
    for item in review['decisions']:
        key=(item['annotationId'],item['phase'],item['rawOutputSha256'],item['renderedTextSha256'])
        if key not in expected or key in decisions or item['verdict'] not in ('candidate_correct','fail','uncertain') or not item['reason'].strip():raise ValueError('slot review unknown/changed/duplicate result')
        decisions[key]=item
    if set(decisions)!=expected:raise ValueError('slot saved outputs not fully reviewed')
    for run in runs:
        for unit in run['units']:
            if unit['rendering']['text'] is None and decisions[review_key(unit)]['verdict']!='fail':raise ValueError('rejected reference output cannot be approved')
    return runs,decisions


def quality_and_costs(run,decisions):
    quality={};costs={}
    for phase in ('natural','slots'):
        quality[phase]={};costs[phase]={}
        for cohort in ('new_probe','old_regression'):
            units=[u for u in run['units'] if u['phase']==phase and u['cohort']==cohort];groups={}
            for unit in units:groups.setdefault(unit['sourceGroup'],[]).append(decisions[review_key(unit)]['verdict'])
            values=[v for row in groups.values() for v in row]
            quality[phase][cohort]={**{verdict:values.count(verdict) for verdict in ('candidate_correct','fail','uncertain')},
                'examples':len(units),'groups':len(groups),'allVariantsCorrectGroups':sum(all(v=='candidate_correct' for v in row) for row in groups.values()),
                'referenceRejected':sum(u['rendering']['text'] is None for u in units)}
            costs[phase][cohort]={'count':len(units),'medianFullExpressionMs':statistics.median(u['elapsedIncludingTelemetryMs'] for u in units),
                'maxFullExpressionMs':max(u['elapsedIncludingTelemetryMs'] for u in units),
                'medianModelIncludingRawJournalMs':statistics.median(u['prediction']['elapsedIncludingOutputJournalMs'] for u in units),
                'medianBindingAndRenderMs':statistics.median(u['bindingMs']+u['renderMs'] for u in units),
                'modelEosOutputs':sum(u['prediction']['eos'] for u in units)}
    return quality,costs


def promotion_status(qualities):
    compatible=True;strict=False
    for quality in qualities.values():
        old=quality['natural'];new=quality['slots']
        for metric in ('candidate_correct','allVariantsCorrectGroups'):
            compatible &= new['new_probe'][metric]>=old['new_probe'][metric]
            strict |= new['new_probe'][metric]>old['new_probe'][metric]
        compatible &= new['old_regression']['candidate_correct']>=old['old_regression']['candidate_correct']
    return 'research_candidate_only_not_quality_acceptance' if compatible and strict else 'mixed_or_no_improvement_not_promoted'


def compact_run(run):
    result={k:v for k,v in run.items() if k!='units'};result['units']=[]
    for unit in run['units']:
        value=copy.deepcopy(unit);value['prediction']={k:v for k,v in value['prediction'].items() if k not in ('inputText','inputTokenIds','tokenIds')}
        result['units'].append(value)
    return result


def materials(write=False):
    if write:
        for seed in SEEDS:
            _,rp=t.old.paths(f'{RUN}-s{seed}');search.archive_file(rp);search.archive_file(rp.with_suffix('.journal.jsonl'))
    runs,decisions=reviewed_runs();qualities={};costs={}
    for run in runs:qualities[str(run['seed'])],costs[str(run['seed'])]=quality_and_costs(run,decisions)
    summary={'schema':'jity-d-slot-realizer-summary-v1','date':'2026-11-05','batchId':RUN,
        'stage':'L3-22 controlled reference realization and ID-bound lexicalization','lastModelRun':runs[-1]['runId'],
        'draftSourceGroups':42,'review':{'reviewedGroups':0,'formalEvaluationAllowed':False},
        'formalEvaluationAllowed':False,'semanticQualityApproved':False,'fullRequest500msStatus':'unverified',
        'realizerTrainerImplemented':True,'realizerTrained':True,'plannerModelImplemented':False,
        'trainingSteps':sum(r['trainingSteps'] for r in runs),'trainingSampleUses':sum(r['trainingSampleUses'] for r in runs),
        'generationAttempts':sum(r['generationCalls'] for r in runs),'newExamples':24,'newSourceCandidateGroups':12,
        'newIndependentVerifiedGroups':0,'sourceIndependence':'unverified','labelProvenance':'assistant_checked_draft_not_human_gold',
        'sourceManifest':source_materials(),'qualityCounts':qualities,'costObservations':costs,'promotionStatus':promotion_status(qualities),
        'runs':[compact_run(r) for r in runs],'manifestSha256':t.sha256_file(MANIFEST),'reviewSha256':t.sha256_file(REVIEW)}
    document=render(summary,runs,decisions)
    files={ART/(PAGE+'-summary.json'):(json.dumps(summary,ensure_ascii=False,indent=2)+'\n').encode(),ART/(PAGE+'.html'):document.encode()}
    for path,raw in files.items():
        if path.exists() and path.read_bytes()!=raw:raise ValueError('preserve original slot report')
        if not write and not path.exists():raise ValueError('slot report missing')
    if write:
        for path,raw in files.items():
            if not path.exists():
                with path.open('xb') as stream:stream.write(raw)
    return summary


def render(summary,runs,decisions):
    import html
    e=lambda value:html.escape(str(value));rows={r['annotationId']:r for r in evaluation_rows()}
    document='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>L3-22 引用表达与名称回填</title><style>body{margin:0;background:#f4f6f8;color:#20313e;font:16px/1.7 system-ui}main{max-width:1150px;margin:auto;padding:24px}section{background:white;padding:22px;border-radius:12px;margin:20px 0}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px;border-bottom:1px solid #ddd}pre{white-space:pre-wrap;overflow-wrap:anywhere}.warn{color:#a7352e}.scroll{overflow:auto}</style><main><p>D / L3-22 · 2026-11-05</p><h1>模型写动作，程序按ID填回名称</h1>'''
    document+=f'<section><p>同一77M底座、原30条监督、学习率0.003／衰减0.01／320步。两种子各比较当前最佳自然表达与新引用表达；完整计划／原名／原话全部保留，只有新输出标记由程序核验并填回登记名称。实际训练{summary["trainingSteps"]}步、{summary["generationAttempts"]}次首次生成，无重试。</p><p class="warn">标记齐全不等于动作、人物方向、步骤和顺序正确。语义意见为助手草稿预检，人审0／来源独立性未核；这只验证表达＋引用程序，真实动作规划／反应／共同结果／完整500ms／浏览器生产仍未验。</p><p>按预登记规则的结论：{e(summary["promotionStatus"])}。新24题属12候选组，同组两变体不当独立来源；旧18题只作已曝光回归。新题中{sum(v["abstractReferenceVerbPatternSeenInTraining"] for v in summary["sourceManifest"]["sources"])}/24的去名称引用／动词模式已在训练出现，不能将熟悉结构的换名表现称为新结构泛化。</p><div class="scroll"><table><tr><th>种子</th><th>用途</th><th>方案</th><th>合理／错／含糊</th><th>全组合理／12</th><th>引用拒绝</th><th>完整表达中位／最大ms</th></tr>'
    for seed in SEEDS:
        for cohort,label in (('new_probe','新24题'),('old_regression','旧18回归')):
            for phase,name in (('natural','自然表达'),('slots','引用＋回填')):
                q=summary['qualityCounts'][str(seed)][phase][cohort];c=summary['costObservations'][str(seed)][phase][cohort]
                document+=f'<tr><td>{seed}</td><td>{label}</td><td>{name}</td><td>{q["candidate_correct"]}／{q["fail"]}／{q["uncertain"]}</td><td>{q["allVariantsCorrectGroups"]}</td><td>{q["referenceRejected"]}</td><td>{c["medianFullExpressionMs"]:.2f}／{c["maxFullExpressionMs"]:.2f}</td></tr>'
    document+='</table></div><p>完整表达包含绑定、分词／生成、原文落盘、核验／回填、结果及尾部遥测。拒绝／失败也在分母；每题每臂每seed一次，准备加载／训练／批末汇总在进程总时间，不签正式性能。</p></section>'
    for run in runs:
        document+=f'<section><h2>seed{run["seed"]}运行身份</h2><p>进程{run["supervisor"]["wallMs"]/1000:.2f}秒／RSS{run["supervisor"]["observedPeakResidentMiB"]:.2f}MiB；原18自然表达输入／token／原文复现{run["historicalRegressionOutputsReproduced"]}项。权重仅D忽略目录。</p><p><a href="m01-fitting/{run["runId"]}.plan.json">冻结计划</a> · <a href="{e(run["recordArtifact"])}">完整输入token／原记录（gzip）</a> · <a href="{e(run["journalArtifact"])}">全部事件（gzip）</a></p></section>'
        for row in evaluation_rows():
            document+=f'<section><details><summary>seed{run["seed"]} · {e(row["annotationId"])} · {"新题" if row["annotationId"].startswith("slots-probe-") else "旧回归"}</summary><p>原参考草稿：{e(row["expressionDraft"])}</p><p>按登记全名的引用参照：{e(annotation_projection(row)["canonicalReference"])}</p>'
            for phase,label in (('natural','自然表达'),('slots','引用表达＋回填')):
                unit=next(u for u in run['units'] if u['phase']==phase and u['annotationId']==row['annotationId']);decision=decisions[review_key(unit)]
                document+=f'<h3>{label} · {e(decision["verdict"])}</h3><p>模型原文：{e(unit["prediction"]["raw"])}</p><p>最终候选：{e(unit["rendering"]["text"])}</p><p>程序状态：{e(unit["rendering"]["status"])}；拒绝原因：{e(unit["rendering"]["problems"])}</p><p>助手核对：{e(decision["reason"])}</p><p>完整表达{unit["elapsedIncludingTelemetryMs"]:.2f}ms，绑定／核验回填{unit["bindingMs"]+unit["renderMs"]:.3f}ms。</p>'
            document+='</details></section>'
    document+=f'<section><h2>证据与边界</h2><p>原D监督参考省略了源登记人物名的甲／乙／丙后缀；新监督只将已写的人名跨度绑定到ID，并保留原文跨度记录，程序运行时填回登记全名。没有拿参考句给推理补动作。重复名字／歧义跨度不自动生成训练目标；字段齐全不能验证自由文本中的语义。真正的开放规划器及整条多模型行动链尚未完成。</p><p><a href="{PAGE}-summary.json">全部原文／回填与汇总</a> · <a href="m01-fitting/{RUN}.manifest.json">冻结清单</a> · <a href="m01-fitting/{RUN}.output-review.json">全部输出助手理由</a> · <a href="l3-22-slots-tokenizer-check.json">无神经前向分词核对</a> · <a href="../../experiments/world-components-logic/data/realizer-slots/source-manifest.json">新来源／已见模式登记</a> · <a href="../../experiments/world-components-logic/data/realizer-slots/training-projection.jsonl">训练监督跨度</a></p></section></main></html>'
    return document


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--worker',type=Path);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    if args.worker:raise SystemExit(worker(args.worker))
    if args.check:
        value=materials();print(json.dumps({'trainingSteps':value['trainingSteps'],'generations':value['generationAttempts'],'formalEvaluationAllowed':False}));raise SystemExit(0)
    parser.error('use experiment.py realizer-slots')
