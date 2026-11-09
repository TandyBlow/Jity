"""D short-realizer training implementation, candidate sources and model inspection.

Original inspection/smoke have no business inputs. The separately authorized
exploratory fit uses assistant-checked drafts without claiming human gold.
"""
from __future__ import annotations
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import action_plan as contract
import experiment as run
import m01_probe as old
from generate_dev_drafts import world,actor
from lab import canonical_bytes,sha256_file,guard_case
from run_pilot import digest,exclusive,save,timestamp
from prepare_run_batch import observe_environment,observe_m02

ROOT=contract.ROOT;BASE=Path(__file__).resolve().parent;ART=ROOT/'artifacts/world-components-logic'
DATA=BASE/'data/action-plan-training';BATCH='d-realizer-new12-r1'
AUDIT_BATCH='d-realizer-new12-r2';AUDIT_DATA=DATA/'r2'
FIT_RUN='m02-realizer-fit-20261104-r1'
BUDGET_RUN='m02-realizer-budget320-20261105-r1'
PROTOCOL=ROOT/'design/world-engine-reports/components-logic/realizer-training-protocol.md'
FIT_PROTOCOL=PROTOCOL.with_name('realizer-exploratory-fit-protocol.md')
BUDGET_PROTOCOL=PROTOCOL.with_name('realizer-training-budget-protocol.md')
CODE=('plan_training.py','action_plan.py','experiment.py','m01_probe.py','generate_dev_drafts.py','lab.py','pilot_codec.py','prepare_run_batch.py','run_pilot.py')
MATERIAL_COMMIT='b24767af571a30e73ab1b10b015600e4ebe0dab7'
MATERIAL_AUTHOR_SHA='9c23ab9ac60dd4ecad26f148c8b6268a5012b05b757bf9e21595ff8898720fd3'
SMOKE_PROTOCOL=PROTOCOL.with_name('realizer-training-smoke-protocol.md')
SMOKE_RUN='m02-realizer-smoke-20261104-r1'
CONFIG={'device':'cpu','threads':1,'concurrency':1,'seed':42,'rank':4,'alpha':8,
        'optimizer':'AdamW','learningRate':0.001,'weightDecay':0.01,'maxGradNorm':1.0,
        'steps':80,'batchSize':2,'maxInputTokens':256,'maxTargetTokens':64,
        'maxNewTokens':64,'doSample':False,'numBeams':1,'earlyStopping':False,
        'frozenBackboneEval':True,'processWallSeconds':120,'maxResidentMiB':2048,
        'attemptsPerCase':1,'gradientAccumulation':1,'adapterDropout':0.0}
SMOKE_CONFIG={**CONFIG,'steps':2,'maxInputTokens':16,'maxTargetTokens':8,'maxNewTokens':8}
SYNTHETIC_EXAMPLES=(
    {'sourceGroup':'synthetic-numeric-01','inputIds':[5,11,17,23,29,7,13,19,25,31,9,15,1],'labels':[6,12,18,24,30,8,1]},
    {'sourceGroup':'synthetic-numeric-02','inputIds':[31,25,19,13,7,29,23,17,1],'labels':[9,15,21,27,1]},
)
# Newly authored source candidates; shared schema helpers are not borrowed stories.
# Each train/development row has a distinct world, people and task; semantic
# independence from other sources is still UNVERIFIED, not established by hashes.
SCENES=(
 ('01','train_candidate','object','梁芷','礼成邮务社','封印台','存放格',[('铜印匣','loc_a')],'合好使用完毕的铜印匣。','pending','合上铜印匣。',1,
  [('合上',[('item','item_1')],[],[],[],None)],'梁芷尝试合上铜印匣。'),
 ('02','development_candidate','object','乔音','盐港乐器修整室','修整桌','置物架',[('木笛盒','loc_a')],'打开木笛盒查看收纳情况。','pending','打开木笛盒。',1,
  [('打开',[('item','item_1')],[],[],[],None)],'乔音尝试打开木笛盒。'),
 ('03','train_candidate','tool','林芩','石灰岩样本库','分样台','编号架',[('岩屑托盘','loc_a'),('软毛刷','p2')],'清扫自己负责的岩屑托盘。','consumed','先前的登记请求已处理。',2,
  [('清扫',[('item','item_1')],[('item','item_2')],[],[],None)],'林芩尝试用软毛刷清扫岩屑托盘。'),
 ('04','development_candidate','tool','沈墨','照溪试茶间','试茶桌','焙茶台',[('试茶片','loc_a'),('竹夹','p2')],'夹起试茶片，准备后续核看。','expired','先前的计时询问已过期。',2,
  [('夹起',[('item','item_1')],[('item','item_2')],[],[],None)],'沈墨尝试用竹夹夹起试茶片。'),
 ('05','train_candidate','destination','渠澈','北圩账房','封蜡台','验章桌',[],'前往验章桌继续当班事务。','pending','走到验章桌。',1,
  [('走向',[],[],[('place','loc_b')],[],None)],'渠澈尝试走向验章桌。'),
 ('06','development_candidate','destination','覃漪','青岚星表馆','读表台','资料柜',[],'前往资料柜整理星表。','pending','移步到资料柜。',1,
  [('移步至',[],[],[('place','loc_b')],[],None)],'覃漪尝试移步至资料柜。'),
 ('07','train_candidate','recipient_utterance','季玄','泥金版画作坊','压版台','纸料架',[('压版机','loc_a')],'请当值协作者暂时停下压版机。','pending','请闻简暂时停下压版机。',1,
  [('请求',[],[],[],[('character','p2')],'请暂时停下压版机')],'季玄尝试向闻简提出请求：“请暂时停下压版机。”'),
 ('08','development_candidate','recipient_utterance','安砚','苏芜釉料间','配釉桌','样签架',[('蓝釉样签','loc_a')],'请闻简递来蓝釉样签。','consumed','先前记录釉温的请求已处理。',2,
  [('请求',[],[],[],[('character','p1')],'请把蓝釉样签递给我')],'安砚尝试向闻简提出请求：“请把蓝釉样签递给我。”'),
 ('09','train_candidate','ordered_steps','江蔓','南岸竹器修复所','量尺桌','标定台',[('折尺','loc_a'),('量尺袋','loc_a')],'收纳折尺后把量尺袋放到标定台。','pending','先收纳折尺，再把袋子放到标定台。',1,
  [('收进',[('item','item_1')],[],[('item','item_2')],[],None),('放置',[('item','item_2')],[],[('place','loc_b')],[],None)],'江蔓尝试将折尺收进量尺袋，再把量尺袋放到标定台。'),
 ('10','development_candidate','ordered_steps','夏棠','月堰灯具棚','熄灯检修桌','备件架',[('旧灯芯','loc_a'),('瓷碟','loc_a')],'抽出已熄灭灯具的旧灯芯，并收至瓷碟。','pending','抽出旧灯芯，再放进瓷碟。',1,
  [('抽出',[('item','item_1')],[],[],[],None),('放入',[('item','item_1')],[],[('item','item_2')],[],None)],'夏棠尝试抽出旧灯芯，再把旧灯芯放入瓷碟。'),
 ('11','train_candidate','open_verb_no_entity','楚澜','静峦石刻校录室','听读席','校录桌',[],'回想先前听到的字音。','consumed','先前查找编号的请求已完成。',2,
  [('回想先前听到的字音',[],[],[],[],None)],'楚澜尝试回想先前听到的字音。'),
 ('12','development_candidate','open_verb_no_entity','谷雨','绫州水钟展厅','滴水观察席','水钟架',[],'凝神辨听滴水间隔。','expired','先前报时询问已过期。',2,
  [('凝神辨听滴水间隔',[],[],[],[],None)],'谷雨尝试凝神辨听滴水间隔。'),
)


def candidate_rows():
    rows=[]
    for num,role,coverage,name,setting,here,there,items,task,status,text,index,steps,reference in SCENES:
        people=[actor('闻简','loc_a','维持当班物品的登记顺序。','愿意配合，按眼前情况行动。') for _ in range(2)]
        people[index-1]=actor(name,'loc_a',task,'认真履行自己的职责，不重复过期事务。')
        w=world(setting,here,there,items,people,time='2033-07-12T09:10:00+08:00')
        c={'caseId':'realizer-new-'+num,'sourceGroup':'d-realizer-new-source-'+num,'anchorCase':True,'derivedFrom':None,
           'split':'training_candidate' if role=='train_candidate' else 'development_candidate',
           'purpose':'new_source_annotation_draft_not_model_input','task':'D02',
           'stageCut':'actor_opportunity_before_action_confirmation',
           'input':{'world':w,'actorId':'p'+str(index),'protagonistId':'p1',
                    'advance':{'inputText':text,'intentStatus':status},'confirmedPrefix':[]}}
        if not guard_case(c)['shouldCall']:raise ValueError('invalid authored source')
        proposed=[]
        for verb,objects,tools,destinations,recipients,utterance in steps:
            p={'verb':verb,'utterance':utterance}
            for key,refs in zip(contract.ROLES,(objects,tools,destinations,recipients)):p[key]=[{'kind':k,'id':i} for k,i in refs]
            proposed.append(p)
        plan={'actorId':c['input']['actorId'],'kind':'act','mode':'attempt',
              'basis':['/world/characters/'+str(index-1)+'/tasks/0','/advance/intentStatus'],'steps':proposed}
        contract.validate_candidate(c,plan)
        rows.append({'annotationId':c['caseId'],'sourceGroup':c['sourceGroup'],'role':role,'coverage':coverage,
            'sourceCase':c,'sourceInputSha256':digest(c['input']),'planDraft':plan,'planSha256':digest(plan),
            'expressionDraft':reference,'expressionSha256':digest(reference),
            'author':'assistant','sourceAuthorship':'newly_authored_for_D_from_rules_only_not_a_rewrite_claim',
            'sourceIndependence':'unverified','labelStatus':'draft_pending_human_review','trainingEligible':False})
    if len({r['sourceGroup'] for r in rows})!=len(rows):raise ValueError('source groups overlap')
    return rows


def packet_identity(rows,*,batch_id=BATCH):return digest({'batchId':batch_id,'rows':rows})


def reconcile_reviews(rows,claims=None,*,batch_id=BATCH):
    if claims is None:return {'reviewedGroups':0,'missingReviews':len(rows),'trainingDataReady':False,'formalEvaluationAllowed':False}
    if not isinstance(claims,dict) or set(claims)!={'schema','batchId','packetSha256','reviewer','decisions'}:raise ValueError('new source review packet required')
    if claims['schema']!='jity-d-realizer-training-review-v1' or claims['batchId']!=batch_id or claims['packetSha256']!=packet_identity(rows,batch_id=batch_id):raise ValueError('training review batch drift')
    if not isinstance(claims['reviewer'],str) or not claims['reviewer'].strip() or claims['reviewer'].strip().lower() in ('assistant','model','ai'):raise ValueError('human reviewer claim required')
    expected={r['annotationId']:r for r in rows};seen=set();agreed=0
    if not isinstance(claims['decisions'],list):raise ValueError('review decisions required')
    for d in claims['decisions']:
        if not isinstance(d,dict) or set(d)!={'annotationId','annotationSha256','decision','note'}:raise ValueError('invalid source review')
        key=d['annotationId']
        if key not in expected or key in seen or d['annotationSha256']!=digest(expected[key]):raise ValueError('source review identity drift')
        if d['decision'] not in ('agree','needs_change','uncertain') or not isinstance(d['note'],str):raise ValueError('invalid source verdict')
        if d['decision']!='agree' and not d['note'].strip():raise ValueError('non-agreement requires evidence')
        seen.add(key);agreed+=d['decision']=='agree'
    return {'reviewedGroups':len(seen),'missingReviews':len(rows)-len(seen),'agreedGroups':agreed,
            'trainingDataReady':agreed==len(rows),'formalEvaluationAllowed':False,'reviewClaimsNotAuthenticatedIdentity':True}


def realizer_payload(row):
    c=row['sourceCase'];bound=contract.bind_candidate(c,row['planDraft']);preview=contract.realizer_preview(c,bound)
    if not preview['wouldCallExpression']:raise ValueError('expression training cannot call on skip')
    by_id={(x['kind'],x['id']):x['name'] for x in preview['payload']['lexicon']}
    steps=[]
    for s in row['planDraft']['steps']:
        value={'动作':s['verb'],'拟说内容':s['utterance']}
        for key,label in zip(contract.ROLES,('对象','工具','目的地','接收人')):
            value[label]=[{'种类':r['kind'],'编号':r['id'],'名称':by_id[(r['kind'],r['id'])]} for r in s[key]]
        steps.append(value)
    return {'人物':by_id[('character',c['input']['actorId'])],'语气':'尝试','计划':steps}


def payload_text(payload):return '将动作计划写成一句尝试，不添加成功结果：'+canonical_bytes(payload).decode()


def input_text(row):return payload_text(realizer_payload(row))


def reviewed_data(claims):
    rows=audited_candidate_rows() if isinstance(claims,dict) and claims.get('batchId')==AUDIT_BATCH else candidate_rows()
    batch_id=AUDIT_BATCH if isinstance(claims,dict) and claims.get('batchId')==AUDIT_BATCH else BATCH
    status=reconcile_reviews(rows,claims,batch_id=batch_id)
    if not status['trainingDataReady']:raise ValueError('training labels are not fully reviewed')
    if batch_id!=AUDIT_BATCH:raise ValueError('source revision superseded by r2 context correction; review corrected packet')
    train=[r for r in rows if r['role']=='train_candidate'];dev=[r for r in rows if r['role']=='development_candidate']
    if len(train)!=6 or len(dev)!=6 or {r['sourceGroup'] for r in train}&{r['sourceGroup'] for r in dev}:raise ValueError('registered train/development groups drift')
    return train,dev


def authorized_draft_data(authorization):
    """A recorded user instruction permits one exploratory run, not human gold."""
    keys={'schema','runId','batchId','packetSha256','userInstruction','context','sourceHead','authorizedAt',
          'scope','configSha256','trainGroups','developmentGroups','humanLabelReviews','labelProvenance',
          'sourceIndependence','formalEvaluationAllowed','sourceRisksAcknowledged'}
    if not isinstance(authorization,dict) or set(authorization)!=keys:raise ValueError('explicit draft-run authorization record required')
    import realizer_expansion as expansion
    profile=fit_profile(authorization['runId']);rows=profile['rows']
    train=[r for r in rows if r['role']=='train_candidate'];dev=[r for r in rows if r['role']=='development_candidate']
    if (authorization['schema']!='jity-d-realizer-draft-run-authorization-v1' or authorization['runId'] not in (FIT_RUN,expansion.RUN,BUDGET_RUN)
            or authorization['batchId']!=profile['batchId'] or authorization['packetSha256']!=profile['packetSha256']
            or authorization['userInstruction']!=profile['instruction'] or not isinstance(authorization['context'],str) or not authorization['context'].strip()
            or authorization['sourceHead']!=profile['sourceHead']
            or not isinstance(authorization['authorizedAt'],str) or not authorization['authorizedAt'].strip()
            or authorization['scope']!='one_small_draft_fit_with_all_before_after_outputs_no_formal_claims'
            or authorization['configSha256']!=digest(profile['config'])
            or authorization['humanLabelReviews']!=0 or authorization['labelProvenance']!='assistant_checked_draft_not_human_gold'
            or authorization['sourceIndependence']!='unverified' or authorization['formalEvaluationAllowed'] is not False
            or authorization['sourceRisksAcknowledged']!=['realizer-new-05','realizer-new-06']
            or authorization['trainGroups']!=list(dict.fromkeys(r['sourceGroup'] for r in train))
            or authorization['developmentGroups']!=list(dict.fromkeys(r['sourceGroup'] for r in dev))):raise ValueError('draft-run authorization scope/data drift')
    return train,dev


def fit_profile(run_id):
    import realizer_expansion as expansion
    if run_id in (expansion.RUN,BUDGET_RUN):
        longer=run_id==BUDGET_RUN
        _,old_record=old.paths(expansion.RUN if longer else FIT_RUN);checkpoint=run.read_json(old_record)['attempts'][0]['checkpoint']
        return {'rows':expansion.rows(),'batchId':expansion.BATCH,'packetSha256':expansion.packet(),
            'manifest':expansion.DATA/'source-manifest.json','config':{**CONFIG,'allowGroupedExamples':True,'steps':320 if longer else 80},
            'protocol':BUDGET_PROTOCOL if longer else expansion.PROTOCOL,'instruction':'继续','sourceHead':'5fffdc9c192ea69fb6afceeb0907b29cb78f76b2' if longer else expansion.HEAD,
            'comparison':'previous_frozen_adapter_then_fresh_source_fit_all_48_first_outputs',
            'baseline':{'checkpoint':checkpoint,'recordSha256':sha256_file(old_record)},'stage':'L3-20' if longer else 'L3-18',
            'page':'l3-20-realizer-budget320' if longer else 'l3-18-realizer-expanded','materialCheck':expansion.materials}
    return {'rows':audited_candidate_rows(),'batchId':AUDIT_BATCH,
        'packetSha256':packet_identity(audited_candidate_rows(),batch_id=AUDIT_BATCH),'manifest':AUDIT_DATA/'source-manifest.json',
        'config':CONFIG,'protocol':FIT_PROTOCOL,'instruction':'可以开始吧','sourceHead':'3bb31434e44e58f0e0e513b1468ed4c67217bd36',
        'comparison':'all_twelve_before_fit_and_after_frozen_reload_first_generation_only','baseline':None,
        'stage':'L3-17','page':'l3-17-realizer-fit','materialCheck':label_audit_materials}


def admitted_training_data(plan):
    if plan['purpose']=='user_authorized_draft_plan_to_text_exploratory_adapter_fit':
        if plan.get('reviewClaims') is not None or plan.get('humanLabelReviewedGroups')!=0:raise ValueError('draft authorization cannot fabricate human label review')
        train,dev=authorized_draft_data(plan.get('draftAuthorization'))
        if plan['runId']!=plan['draftAuthorization']['runId']:raise ValueError('authorization belongs to another run')
        if plan.get('exploratoryProtocolSha256')!=sha256_file(fit_profile(plan['runId'])['protocol']):raise ValueError('exploratory protocol drift')
        return train,dev
    if plan['purpose']!='reviewed_candidate_plan_to_text_adapter_fit_not_open_planner':raise ValueError('unknown training admission scope')
    return reviewed_data(plan['reviewClaims'])


def lora_linear(torch,base,rank,alpha):
    if rank<=0 or alpha<=0:raise ValueError('positive rank and scale required')
    class LoRALinear(torch.nn.Module):
        def __init__(self):
            super().__init__();self.base_layer=base
            for p in base.parameters():p.requires_grad_(False)
            self.lora_A=torch.nn.Parameter(torch.empty(rank,base.in_features,device=base.weight.device,dtype=base.weight.dtype))
            self.lora_B=torch.nn.Parameter(torch.zeros(base.out_features,rank,device=base.weight.device,dtype=base.weight.dtype))
            torch.nn.init.kaiming_uniform_(self.lora_A,a=__import__('math').sqrt(5));self.scale=alpha/rank
        def forward(self,x):return self.base_layer(x)+(x@self.lora_A.T@self.lora_B.T)*self.scale
    return LoRALinear()


def install_lora(torch,model,rank=4,alpha=8,expected_modules=48):
    for p in model.parameters():p.requires_grad_(False)
    targets=[(n,m) for n,m in model.named_modules() if isinstance(m,torch.nn.Linear) and n.endswith(('.q','.v')) and any(s in n for s in ('.SelfAttention.','.EncDecAttention.'))]
    if len(targets)!=expected_modules:raise ValueError('T5 attention target coverage mismatch')
    rows=[]
    for name,base in targets:
        parent,_,leaf=name.rpartition('.');setattr(model.get_submodule(parent),leaf,lora_linear(torch,base,rank,alpha))
        rows.append({'name':name,'inputFeatures':base.in_features,'outputFeatures':base.out_features,'rank':rank,'alpha':alpha})
    return rows


def base_state(model):
    return {n.replace('.base_layer.','.'):v for n,v in model.state_dict().items() if not n.endswith(('.lora_A','.lora_B'))}


def adapter_state(model):return {n:p.detach().cpu().clone() for n,p in model.named_parameters() if p.requires_grad}


def restore_adapter(model,state):
    parameters={n:p for n,p in model.named_parameters() if p.requires_grad}
    if set(parameters)!=set(state):raise ValueError('adapter checkpoint names mismatch')
    for n,p in parameters.items():
        if p.shape!=state[n].shape or p.dtype!=state[n].dtype:raise ValueError('adapter checkpoint shape/type mismatch')
    import torch
    with torch.no_grad():
        for n,p in parameters.items():p.copy_(state[n])


def tokenize_example(tokenizer,row,config=CONFIG,*,payload_builder=None,target_text=None):
    # All source names/steps are retained. The target is never placed in input.
    payload=realizer_payload(row) if payload_builder is None else payload_builder(row)
    text=input_text(row) if payload_builder is None else payload_text(payload)
    target=row['expressionDraft'] if target_text is None else target_text
    x=tokenizer.encode(text,add_special_tokens=True,truncation=False)
    y=tokenizer.encode(target,add_special_tokens=True,truncation=False)
    if not x or len(x)>config['maxInputTokens'] or not y or len(y)>config['maxTargetTokens']:raise ValueError('complete expression example exceeds registered token limits')
    if y[-1]!=tokenizer.eos_token_id:raise ValueError('target EOS missing')
    return {'inputIds':x,'labels':y,'sourceGroup':row['sourceGroup'],'annotationId':row['annotationId'],'inputSha256':digest(payload),'targetSha256':row['expressionSha256'] if target_text is None else digest(target)}


def collate(torch,examples,pad_id):
    m=max(len(e['inputIds']) for e in examples);n=max(len(e['labels']) for e in examples)
    ids=torch.full((len(examples),m),pad_id,dtype=torch.long);mask=torch.zeros_like(ids)
    labels=torch.full((len(examples),n),-100,dtype=torch.long)
    for i,e in enumerate(examples):
        ids[i,:len(e['inputIds'])]=torch.tensor(e['inputIds']);mask[i,:len(e['inputIds'])]=1
        labels[i,:len(e['labels'])]=torch.tensor(e['labels'])
    return {'input_ids':ids,'attention_mask':mask,'labels':labels}


def fit_adapter(torch,model,tokenizer,train_rows,config,checkpoint):
    """Actual teacher-forced adapter training; caller must verify review/plan first."""
    examples=[tokenize_example(tokenizer,r,config) for r in train_rows]
    return fit_encoded_adapter(torch,model,examples,tokenizer.pad_token_id,config,checkpoint)


def fit_encoded_adapter(torch,model,examples,pad_id,config,checkpoint):
    """Shared numeric training loop; production callers gate reviewed data first."""
    model.eval()
    if not examples:raise ValueError('empty adapter training batch')
    if config.get('allowGroupedExamples'):
        if any(not e.get('annotationId') for e in examples) or len({e['annotationId'] for e in examples})!=len(examples):raise ValueError('duplicate/missing grouped training annotation')
    elif len({e['sourceGroup'] for e in examples})!=len(examples):raise ValueError('training source duplicate')
    params=[p for p in model.parameters() if p.requires_grad]
    if not params:raise ValueError('no learned adapter parameters')
    optimizer=torch.optim.AdamW(params,lr=config['learningRate'],weight_decay=config['weightDecay'])
    generator=torch.Generator().manual_seed(config['seed']);order=torch.randperm(len(examples),generator=generator).tolist();losses=[]
    schedule=config.get('exampleSchedule')
    if schedule is not None:
        if not config.get('allowGroupedExamples') or len(schedule)!=config['steps']*config['batchSize']:
            raise ValueError('invalid explicit grouped training schedule')
        lookup={e['annotationId']:e for e in examples}
        if any(identity not in lookup for identity in schedule):raise ValueError('unknown scheduled training annotation')
    microbatch=config.get('microbatchSize',config['batchSize'])
    if type(microbatch) is not int or not 1<=microbatch<=config['batchSize']:raise ValueError('invalid training microbatch size')
    checkpointed=config.get('gradientCheckpointing',False);dropouts=[];old_cache=None
    if checkpointed:
        if config.get('gradientCheckpointingReentrant') is not False or config.get('trainingDropout')!=0.0:
            raise ValueError('checkpointed fitting requires non-reentrant gradients and explicitly disabled dropout')
        for name,module in model.named_modules():
            if isinstance(module,torch.nn.Dropout):dropouts.append((module,'p',module.p,name));module.p=0.0
            value=getattr(module,'dropout',None)
            if type(value) in (int,float):dropouts.append((module,'dropout',value,name));module.dropout=0.0
        old_cache=getattr(model.config,'use_cache',None)
        model.config.use_cache=False
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
        model.train()
        checkpoint('gradient_checkpointing_configured',{'useReentrant':False,'modelTraining':model.training,
          'dropout':0.0,'disabledDropoutFields':[{'module':name,'field':field,'original':value} for _,field,value,name in dropouts],
          'microbatchSize':microbatch,'effectiveBatchSize':config['batchSize'],'lossWeighting':'valid_target_tokens'})
    try:
        for step in range(config['steps']):
            batch=([lookup[identity] for identity in schedule[step*config['batchSize']:(step+1)*config['batchSize']]] if schedule is not None else
                   [examples[order[(step*config['batchSize']+j)%len(order)]] for j in range(config['batchSize'])])
            payload={'step':step+1,'sourceGroups':[e['sourceGroup'] for e in batch],'startedMonotonicNs':time.monotonic_ns()}
            started=payload['startedMonotonicNs']
            if config.get('allowGroupedExamples'):payload['annotationIds']=[e['annotationId'] for e in batch]
            checkpoint('training_step_started',payload)
            optimizer.zero_grad(set_to_none=True);value=0.0
            token_count=sum(sum(token!=-100 for token in e['labels']) for e in batch)
            if token_count<=0:raise ValueError('training batch has no supervised target tokens')
            for offset in range(0,len(batch),microbatch):
                part=batch[offset:offset+microbatch]
                fraction=sum(sum(token!=-100 for token in e['labels']) for e in part)/token_count
                if microbatch<len(batch):checkpoint('training_microbatch_started',{'step':step+1,'index':offset//microbatch,
                  'annotationIds':[e.get('annotationId') for e in part],'targetTokenWeight':fraction})
                output=model(**collate(torch,part,pad_id));loss=output.loss*fraction
                if not torch.isfinite(loss):raise ValueError('nonfinite training loss')
                value+=float(loss.detach());loss.backward();del output,loss
            norm=torch.nn.utils.clip_grad_norm_(params,config['maxGradNorm'])
            if not torch.isfinite(norm):raise ValueError('nonfinite adapter gradient')
            optimizer.step();losses.append(value)
            checkpoint('training_step_settled',{'step':step+1,'loss':value,'gradientNorm':float(norm),'elapsedThroughUpdateMs':(time.monotonic_ns()-started)/1e6})
    finally:
        if checkpointed:
            model.gradient_checkpointing_disable()
            for module,field,value,_ in dropouts:setattr(module,field,value)
            if old_cache is not None:model.config.use_cache=old_cache
        model.eval()
    return losses


def save_reload_adapter(torch,model,destination,source_hash,checkpoint):
    """Exercise the same durable adapter-only save/load path in fit and smoke."""
    if old.tensor_hash(base_state(model))!=source_hash:raise ValueError('frozen source weights changed before save')
    weights=adapter_state(model);adapter_hash=old.tensor_hash(weights)
    if not weights:raise ValueError('empty adapter checkpoint')
    destination.mkdir(parents=True,exist_ok=False);path=destination/'adapter.pt'
    checkpoint('adapter_save_started',{'path':str(path.relative_to(ROOT)),'tensorSha256':adapter_hash})
    with path.open('xb') as stream:
        torch.save(weights,stream);stream.flush();os.fsync(stream.fileno())
    identity={'path':str(path.relative_to(ROOT)),'sha256':sha256_file(path),
              'tensorSha256':adapter_hash,'sourceTensorSha256':source_hash}
    checkpoint('adapter_saved',identity)
    with torch.no_grad():
        for p in model.parameters():
            if p.requires_grad:p.zero_()
    if any(torch.count_nonzero(p) for p in model.parameters() if p.requires_grad):raise ValueError('adapter clear failed')
    checkpoint('adapter_cleared',{'tensorSha256':old.tensor_hash(adapter_state(model)),'allTrainableZero':True})
    restore_adapter(model,torch.load(path,map_location='cpu',weights_only=True))
    if old.tensor_hash(adapter_state(model))!=adapter_hash or old.tensor_hash(base_state(model))!=source_hash:raise ValueError('adapter checkpoint reload or base mismatch')
    checkpoint('adapter_reloaded',identity);return identity


def synthetic_gradient_check(torch):
    """Separate numeric fixture, not M02 or any project scenario."""
    torch.manual_seed(42);base=torch.nn.Linear(8,8);base_hash=old.tensor_hash(base.state_dict())
    x=torch.randn(4,8);target=torch.randn(4,8);initial=base(x).detach();layer=lora_linear(torch,base,2,4)
    if not torch.equal(initial,layer(x).detach()):raise ValueError('zero adapter changed synthetic base output')
    optimizer=torch.optim.AdamW([p for p in layer.parameters() if p.requires_grad],lr=.03);losses=[]
    for _ in range(8):
        optimizer.zero_grad();loss=(layer(x)-target).square().mean();loss.backward();optimizer.step();losses.append(float(loss.detach()))
    expected=layer(x).detach();state=adapter_state(layer)
    with torch.no_grad():layer.lora_A.zero_();layer.lora_B.zero_()
    restore_adapter(layer,state)
    if not torch.equal(expected,layer(x).detach()) or old.tensor_hash(base.state_dict())!=base_hash:raise ValueError('synthetic adapter restore/base freeze mismatch')
    if not losses[-1]<losses[0] or not torch.count_nonzero(layer.lora_B):raise ValueError('synthetic adapter did not learn')
    return {'syntheticOptimizerSteps':8,'lossFirst':losses[0],'lossLast':losses[-1],
            'baseUnchanged':True,'checkpointReloadExact':True,'projectModelTrainingSteps':0,'businessInferenceCalls':0}


def inspection_plan(run_id,*,smoke=False):
    pp,rp=old.paths(run_id)
    if pp.exists() or rp.exists():raise FileExistsError('use new inspection id')
    model=observe_m02(ROOT);environment=observe_environment(ROOT)
    if not model['allSixFilesFullyRehashedAndVerified'] or not environment['registeredVersionsMatch']:raise ValueError('M02/environment verification failed')
    plan={'schema':'jity-d-realizer-smoke-plan-v1' if smoke else 'jity-d-realizer-inspection-plan-v1','runId':run_id,'sourceHead':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'preparedAt':timestamp(),'purpose':'real_m02_synthetic_training_save_reload_only' if smoke else 'model_layout_and_synthetic_gradient_only_no_project_forward',
        'config':(SMOKE_CONFIG if smoke else CONFIG).copy(),'cases':[{'caseId':'m02-synthetic-training-smoke' if smoke else 'm02-adapter-layout-only'}],'arms':['smoke' if smoke else 'inspect'],
        'code':{str((BASE/n).relative_to(ROOT)):sha256_file(BASE/n) for n in CODE},
        'protocolSha256':sha256_file(SMOKE_PROTOCOL if smoke else PROTOCOL),'model':model,'environment':environment,
        'candidatePacketSha256':packet_identity(candidate_rows()),'trainingLabelsReviewed':0,
        'formalEvaluationAllowed':False,'businessTrainingSteps':0,'businessInferenceCalls':0,
        'authorization':'用户继续工作；D独立CPU单线程模型装配与合成数字工程检查，不用业务草稿'}
    if smoke:
        plan.update(syntheticExamples=copy.deepcopy(list(SYNTHETIC_EXAMPLES)),syntheticExamplesSha256=digest(list(SYNTHETIC_EXAMPLES)),
                    syntheticOptimizerSteps=2,businessSourceGroups=0,adapterScope='disposable_synthetic_fixture_never_business_inference')
    exclusive(pp,plan);return pp


def verify_inspection(plan):
    smoke=plan['purpose']=='real_m02_synthetic_training_save_reload_only'
    expected_purpose='real_m02_synthetic_training_save_reload_only' if smoke else 'model_layout_and_synthetic_gradient_only_no_project_forward'
    if plan['config']!=(SMOKE_CONFIG if smoke else CONFIG) or plan['purpose']!=expected_purpose or plan['formalEvaluationAllowed'] is not False:raise ValueError('inspection scope drift')
    if plan['protocolSha256']!=sha256_file(SMOKE_PROTOCOL if smoke else PROTOCOL):raise ValueError('inspection protocol drift')
    if smoke and (plan.get('syntheticExamples')!=list(SYNTHETIC_EXAMPLES) or plan.get('syntheticExamplesSha256')!=digest(list(SYNTHETIC_EXAMPLES))
                  or plan.get('syntheticOptimizerSteps')!=2 or plan.get('businessSourceGroups')!=0
                  or plan.get('adapterScope')!='disposable_synthetic_fixture_never_business_inference'
                  or plan.get('businessTrainingSteps')!=0 or plan.get('businessInferenceCalls')!=0
                  or plan.get('schema')!='jity-d-realizer-smoke-plan-v1' or plan.get('arms')!=['smoke']
                  or plan.get('cases')!=[{'caseId':'m02-synthetic-training-smoke'}]):raise ValueError('synthetic fixture scope drift')
    for name,h in plan['code'].items():
        if sha256_file(ROOT/name)!=h:raise ValueError('executed source drift: '+name)
    if plan['model']!=observe_m02(ROOT) or plan['environment']!=observe_environment(ROOT):raise ValueError('inspection model/environment drift')
    if plan['candidatePacketSha256']!=packet_identity(candidate_rows()):raise ValueError('source candidates drift')


def real_model_smoke(torch,model,plan,checkpoint):
    """No scene text, no tokenizer and no semantic labels; actual M02 autograd."""
    examples=copy.deepcopy(plan['syntheticExamples']);config=plan['config']
    if examples!=list(SYNTHETIC_EXAMPLES):raise ValueError('synthetic fixture identity drift')
    for row in examples:
        if any(type(v) is not int or v<=0 or v>=model.config.vocab_size for v in row['inputIds']+row['labels']):raise ValueError('synthetic token outside vocabulary')
        if row['inputIds'][-1]!=model.config.eos_token_id or row['labels'][-1]!=model.config.eos_token_id:raise ValueError('synthetic EOS mismatch')
    batch=collate(torch,examples,model.config.pad_token_id);source_hash=old.tensor_hash(model.state_dict())
    source_parameters=sum(p.numel() for p in model.parameters())
    phase={'name':'source_reference'};forwards=[];active=[]
    def before(module,args,kwargs):
        event={'index':len(forwards),'phase':phase['name'],'gradEnabled':torch.is_grad_enabled(),
               'inputTensorShapes':{n:list(v.shape) for n,v in kwargs.items() if torch.is_tensor(v)},
               'startedMonotonicNs':time.monotonic_ns(),'status':'started'}
        forwards.append(event);active.append(event);checkpoint('model_forward_started',event)
    def after(module,args,kwargs,output):
        event=active.pop();event['status']='complete' if output is not None else 'failed'
        if output is not None:
            event.update(logitsShape=list(output.logits.shape),logitsSha256=old.tensor_hash({'logits':output.logits.detach()}))
            if output.loss is not None:event['loss']=float(output.loss.detach())
        event['elapsedThroughOutputHashMs']=(time.monotonic_ns()-event['startedMonotonicNs'])/1e6
        checkpoint('model_forward_settled',event)
    hooks=[model.register_forward_pre_hook(before,with_kwargs=True),model.register_forward_hook(after,with_kwargs=True,always_call=True)]
    try:
        with torch.inference_mode():source_logits=model(**batch).logits.detach().clone()
        topology=install_lora(torch,model,config['rank'],config['alpha']);initial=adapter_state(model)
        phase['name']='zero_adapter_equivalence'
        with torch.inference_mode():zero_logits=model(**batch).logits.detach().clone()
        if not torch.equal(source_logits,zero_logits):raise ValueError('zero adapter differs from real source model')
        checkpoint('zero_adapter_equivalence',{'exact':True,'logitsSha256':old.tensor_hash({'logits':source_logits})})
        phase['name']='synthetic_optimizer'
        losses=fit_encoded_adapter(torch,model,examples,model.config.pad_token_id,config,checkpoint)
        changed=[n for n,p in adapter_state(model).items() if not torch.equal(initial[n],p)]
        if not changed or not all(p.grad is None for p in model.parameters() if not p.requires_grad):raise ValueError('synthetic adapter update/base gradient mismatch')
        if not all(torch.isfinite(p).all() for p in model.parameters() if p.requires_grad):raise ValueError('nonfinite adapter tensor')
        phase['name']='fitted_teacher_forced'
        with torch.inference_mode():fitted=model(**batch).logits.detach().clone()
        if torch.equal(fitted,source_logits):raise ValueError('actual full-model output did not change')
        def generate(name):
            phase['name']=name;start=time.perf_counter()
            with torch.inference_mode():tokens=model.generate(input_ids=batch['input_ids'],attention_mask=batch['attention_mask'],max_new_tokens=config['maxNewTokens'],do_sample=False,num_beams=1).tolist()
            payload={'tokenIds':tokens,'maxNewTokens':config['maxNewTokens'],'elapsedMs':(time.perf_counter()-start)*1000,'semanticMeaning':'none_synthetic_numeric_fixture'}
            checkpoint(name,payload);return payload
        first=generate('synthetic_generation_before_reload')
        checkpoint_identity=save_reload_adapter(torch,model,ROOT/'.local/world-components-logic/realizer-smoke'/plan['runId'],source_hash,checkpoint)
        phase['name']='reloaded_teacher_forced'
        with torch.inference_mode():reloaded=model(**batch).logits.detach().clone()
        second=generate('synthetic_generation_after_reload')
        if not torch.equal(fitted,reloaded) or first['tokenIds']!=second['tokenIds']:raise ValueError('full-model outputs differ after disk reload')
        if old.tensor_hash(base_state(model))!=source_hash:raise ValueError('source base changed during synthetic training')
        checkpoint('full_model_reload_equivalence',{'logitsExact':True,'generatedTokensExact':True,'sourceBaseUnchanged':True})
        return {'sourceParameters':source_parameters,'trainableAdapterParameters':sum(p.numel() for p in model.parameters() if p.requires_grad),
            'totalInferenceParameters':sum(p.numel() for p in model.parameters()),'adapterModules':len(topology),'targetModules':topology,
            'syntheticOptimizerSteps':len(losses),'syntheticExamples':examples,'losses':losses,'lossTrendIsNotSemanticQuality':True,
            'changedAdapterTensors':changed,'sourceBaseUnchanged':True,'baseGradientsAbsent':True,
            'zeroAdapterLogitsExact':True,'reloadedLogitsExact':True,'reloadedGeneratedTokensExact':True,
            'fittedLogitsSha256':old.tensor_hash({'logits':fitted}),'checkpoint':checkpoint_identity,
            'syntheticGenerations':[first,second],'modelTopForwardCalls':len(forwards),'modelForwards':forwards,
            'businessTrainingSteps':0,'businessInferenceCalls':0,'semanticQualityApproved':False,'fullRequestMeasured':False}
    finally:
        for hook in hooks:hook.remove()


def inspection_worker(path):
    plan=run.read_json(path);_,out=old.paths(plan['runId']);smoke=plan['purpose']=='real_m02_synthetic_training_save_reload_only'
    slots=run.planned_slots(plan,('smoke' if smoke else 'inspect',))
    report={'schema':'jity-d-realizer-smoke-record-v1' if smoke else 'jity-d-realizer-inspection-record-v1','runId':plan['runId'],'planSha256':sha256_file(path),
        'status':'running','stages':[],'attempts':[],'attemptSlots':slots,'activeAttempt':None,'forwardAttempts':[],
        'trainingSteps':0,'businessInferenceCalls':0,'formalEvaluationAllowed':False,'fullRequestMeasured':False}
    exclusive(out,report);stage=lambda n,f:run.record_stage(report,out,n,f)
    try:
        stage('verify',lambda:verify_inspection(plan))
        import torch
        from transformers import T5ForConditionalGeneration
        torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.manual_seed(42)
        model=stage('load_m02',lambda:T5ForConditionalGeneration.from_pretrained(ROOT/plan['model']['directory'],local_files_only=True,weights_only=True).eval())
        forward_calls=[0]
        hook=model.register_forward_pre_hook(lambda *_:forward_calls.__setitem__(0,forward_calls[0]+1))
        source_hash=old.tensor_hash(model.state_dict());source_params=sum(p.numel() for p in model.parameters())
        if source_params!=77440384:raise ValueError('M02 parameter identity mismatch')
        with run.AppendJournal(out.with_suffix('.journal.jsonl'),report['planSha256']) as journal:
            journal.append('begin',{'runId':plan['runId'],'slots':slots})
            a={**slots[0],'status':'started','startedMonotonicNs':time.monotonic_ns(),'checkpoints':[]};report['activeAttempt']=a
            journal.append('attempt_start',a)
            def checkpoint(name,payload):
                e={k:a[k] for k in ('arm','caseId','repeat')};e.update(name=name,payload=payload);journal.append('attempt_checkpoint',e);a['checkpoints'].append(copy.deepcopy(e))
            if smoke:
                a['syntheticFullModelCheck']=real_model_smoke(torch,model,plan,checkpoint)
                if forward_calls[0]!=a['syntheticFullModelCheck']['modelTopForwardCalls']:raise ValueError('synthetic forward accounting mismatch')
            else:
                topology=install_lora(torch,model,CONFIG['rank'],CONFIG['alpha'])
                trainable=sum(p.numel() for p in model.parameters() if p.requires_grad)
                zeros=all(not torch.count_nonzero(p) for n,p in model.named_parameters() if n.endswith('.lora_B'))
                if trainable!=172032 or not zeros or old.tensor_hash(base_state(model))!=source_hash:raise ValueError('adapter/base layout mismatch')
                a['layout']={'sourceParameters':source_params,'trainableAdapterParameters':trainable,
                             'totalInferenceParameters':sum(p.numel() for p in model.parameters()),'targetModules':topology,
                             'initialOutputMatricesZero':True,'sourceBaseUnchanged':True}
                checkpoint('adapter_layout',a['layout']);a['syntheticCheck']=synthetic_gradient_check(torch);checkpoint('synthetic_numeric_check',a['syntheticCheck'])
                if forward_calls[0]!=0:raise ValueError('source model executed during layout inspection')
            if old.tensor_hash(base_state(model))!=source_hash:raise ValueError('source model changed during inspection')
            hook.remove();a['syntheticModelForwardCalls']=forward_calls[0];a['projectForwardCalls']=0;a['status']='complete';a['settledAt']=timestamp()
            t=time.perf_counter();journal.append('attempt_result',a);result_ms=(time.perf_counter()-t)*1000
            timing={k:a[k] for k in ('arm','caseId','repeat')}
            timing.update(resultJournalMs=result_ms,snapshotEndMs=0.,elapsedThroughResultMs=(time.monotonic_ns()-a['startedMonotonicNs'])/1e6)
            t=time.perf_counter();journal.append('attempt_settled',timing);a.update(timing)
            a['telemetryJournalMs']=(time.perf_counter()-t)*1000;a['elapsedIncludingTelemetryMs']=(time.monotonic_ns()-a['startedMonotonicNs'])/1e6
            report['attempts']=[a];report['activeAttempt']=None
        report['sourceFilesUnchanged']=observe_m02(ROOT)==plan['model'];report['status']='diagnostic_completed';report['unexecutedAttempts']=0
    except Exception as error:report.update(status='failed',error={'type':type(error).__name__,'message':str(error)})
    finally:save(out,report)
    return 0 if report['status']=='diagnostic_completed' else 1


def execute_inspection(path):
    plan=run.read_json(path);arms=('smoke',) if plan['purpose']=='real_m02_synthetic_training_save_reload_only' else ('inspect',)
    result=run.execute_plan(path,paths=old.paths,verify=verify_inspection,worker_script=Path(__file__),settle_stages=old.settle_stages,arms=arms)
    if arms==('smoke',):
        _,out=old.paths(plan['runId']);record=run.read_json(out)
        events=[c for a in record.get('attempts',[]) for c in a.get('checkpoints',[])]
        record.update(syntheticTrainingStepAttempts=sum(c['name']=='training_step_started' for c in events),
                      syntheticOptimizerSteps=sum(c['name']=='training_step_settled' for c in events),
                      syntheticForwardAttempts=sum(c['name']=='model_forward_started' for c in events),
                      syntheticForwardsCompleted=sum(c['name']=='model_forward_settled' and c['payload']['status']=='complete' for c in events))
        save(out,record)
    return result

def training_plan(run_id,review_path=None,*,authorization_path=None):
    if (review_path is None)==(authorization_path is None):raise ValueError('choose reviewed labels or explicit draft-run authorization')
    claims=run.read_json(review_path) if review_path is not None else None
    authorization=run.read_json(authorization_path) if authorization_path is not None else None
    train,dev=authorized_draft_data(authorization) if authorization_path is not None else reviewed_data(claims)
    if authorization_path is not None and run_id!=authorization['runId']:raise ValueError('authorization belongs to another run')
    profile=fit_profile(run_id);profile['materialCheck']()
    pp,rp=old.paths(run_id)
    if pp.exists() or rp.exists():raise FileExistsError('use a new training id')
    model=observe_m02(ROOT);environment=observe_environment(ROOT)
    if not model['allSixFilesFullyRehashedAndVerified'] or not environment['registeredVersionsMatch']:raise ValueError('training identity invalid')
    plan={'schema':'jity-d-realizer-training-plan-v1','runId':run_id,'preparedAt':timestamp(),
          'sourceHead':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
          'purpose':'user_authorized_draft_plan_to_text_exploratory_adapter_fit' if authorization_path is not None else 'reviewed_candidate_plan_to_text_adapter_fit_not_open_planner',
          'config':profile['config'].copy(),'cases':[{'caseId':'m02-reviewed-realizer-fit'}],'arms':['fit'],
          'code':{str((BASE/n).relative_to(ROOT)):sha256_file(BASE/n) for n in CODE+(('realizer_expansion.py',) if profile['baseline'] else ())},
          'protocolSha256':sha256_file(PROTOCOL),'model':model,'environment':environment,
          'reviewClaims':claims,'reviewFileSha256':sha256_file(review_path) if review_path is not None else None,
          'candidateBatchId':profile['batchId'],'candidatePacketSha256':profile['packetSha256'],
          'candidateAuditManifestSha256':sha256_file(profile['manifest']),'trainGroups':list(dict.fromkeys(r['sourceGroup'] for r in train)),
          'developmentGroups':list(dict.fromkeys(r['sourceGroup'] for r in dev)),'formalEvaluationAllowed':False,
          'sourceIndependence':'unverified','newIndependentTrainingGroups':0,'fullRequestMeasured':False}
    if authorization_path is not None:
        plan.update(draftAuthorization=authorization,authorizationFileSha256=sha256_file(authorization_path),
                    exploratoryProtocolSha256=sha256_file(profile['protocol']),humanLabelReviewedGroups=0,
                    outputComparison=profile['comparison'])
    if profile['baseline']:plan['baselineAdapter']=profile['baseline']
    exclusive(pp,plan);return pp


def verify_training(plan):
    profile=fit_profile(plan.get('runId',''))
    if (plan['purpose'] not in ('reviewed_candidate_plan_to_text_adapter_fit_not_open_planner','user_authorized_draft_plan_to_text_exploratory_adapter_fit')
            or plan['config']!=profile['config'] or plan['formalEvaluationAllowed'] is not False):raise ValueError('training scope/config drift')
    train,dev=admitted_training_data(plan)
    if plan['purpose'].startswith('user_authorized') and plan.get('outputComparison')!=profile['comparison']:raise ValueError('before/after comparison scope drift')
    profile['materialCheck']()
    if (plan['trainGroups']!=list(dict.fromkeys(r['sourceGroup'] for r in train)) or plan['developmentGroups']!=list(dict.fromkeys(r['sourceGroup'] for r in dev))
            or plan.get('candidateBatchId')!=profile['batchId'] or plan['candidatePacketSha256']!=profile['packetSha256']
            or plan.get('candidateAuditManifestSha256')!=sha256_file(profile['manifest'])):raise ValueError('training source/role drift')
    if profile['baseline']:
        if plan.get('baselineAdapter')!=profile['baseline'] or sha256_file(ROOT/profile['baseline']['checkpoint']['path'])!=profile['baseline']['checkpoint']['sha256']:raise ValueError('frozen baseline adapter drift')
    if plan['protocolSha256']!=sha256_file(PROTOCOL):raise ValueError('training protocol drift')
    for name,h in plan['code'].items():
        if sha256_file(ROOT/name)!=h:raise ValueError('training code drift')
    if plan['model']!=observe_m02(ROOT) or plan['environment']!=observe_environment(ROOT):raise ValueError('training model/environment drift')


def generate_expressions(torch,model,tokenizer,rows,phase,checkpoint,config=CONFIG,*,payload_builder=None):
    from transformers.generation.stopping_criteria import MaxTimeCriteria,StoppingCriteriaList
    predictions=[]
    for row in rows:
        start=time.perf_counter();checkpoint('generation_started',{'annotationId':row['annotationId'],'role':row['role'],'phase':phase})
        payload=realizer_payload(row) if payload_builder is None else payload_builder(row)
        text=input_text(row) if payload_builder is None else payload_text(payload)
        input_ids=tokenizer.encode(text,add_special_tokens=True,truncation=False)
        if not input_ids or len(input_ids)>config['maxInputTokens']:raise ValueError('complete generation input exceeds registered token limit')
        ids=torch.tensor([input_ids]);count=[0];hook=model.register_forward_pre_hook(lambda *_:count.__setitem__(0,count[0]+1))
        try:
            with torch.inference_mode():output=model.generate(input_ids=ids,attention_mask=torch.ones_like(ids),max_new_tokens=config['maxNewTokens'],do_sample=False,num_beams=1,
                stopping_criteria=StoppingCriteriaList([MaxTimeCriteria(max_time=3)]))
        finally:hook.remove()
        tokens=output[0].tolist();raw=tokenizer.decode(tokens,skip_special_tokens=True)
        eos=bool(tokens) and tokens[-1]==tokenizer.eos_token_id
        prediction={'annotationId':row['annotationId'],'sourceGroup':row['sourceGroup'],'role':row['role'],'phase':phase,
            'inputText':text,'inputTokenIds':input_ids,'inputSha256':digest(payload),
            'raw':raw,'tokenIds':tokens,'modelTopForwardCalls':count[0],'eos':eos,
            'stopStatus':'eos' if eos else 'max_new_tokens' if len(tokens)-1>=config['maxNewTokens'] else 'soft_time_or_other_incomplete',
            'semanticReview':'pending_not_approved','scope':'provided_draft_plan_expression_only_not_open_planner',
            'elapsedMs':(time.perf_counter()-start)*1000}
        checkpoint('generation_output',prediction)
        prediction['elapsedIncludingOutputJournalMs']=(time.perf_counter()-start)*1000
        checkpoint('generation_timing',{'annotationId':row['annotationId'],'phase':phase,'elapsedIncludingOutputJournalMs':prediction['elapsedIncludingOutputJournalMs']})
        predictions.append(prediction)
    return predictions


def training_worker(path):
    plan=run.read_json(path);config=plan['config'];_,out=old.paths(plan['runId']);slots=run.planned_slots(plan,('fit',))
    report={'schema':'jity-d-realizer-training-record-v1','runId':plan['runId'],'planSha256':sha256_file(path),
        'status':'running','stages':[],'attempts':[],'attemptSlots':slots,'activeAttempt':None,'forwardAttempts':[],
        'trainingSteps':0,'businessGenerationCalls':0,'formalEvaluationAllowed':False,'semanticQualityApproved':False,'fullRequestMeasured':False}
    exclusive(out,report);stage=lambda n,f:run.record_stage(report,out,n,f)
    try:
        stage('verify_training_admission_and_plan',lambda:verify_training(plan));train,dev=admitted_training_data(plan)
        import torch
        from transformers import T5ForConditionalGeneration,T5Tokenizer
        torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.manual_seed(config['seed'])
        directory=ROOT/plan['model']['directory']
        tokenizer=stage('tokenizer',lambda:T5Tokenizer.from_pretrained(directory,local_files_only=True,extra_ids=0,legacy=True))
        model=stage('source_model',lambda:T5ForConditionalGeneration.from_pretrained(directory,local_files_only=True,weights_only=True).eval())
        source_hash=old.tensor_hash(model.state_dict());report['topology']=install_lora(torch,model,config['rank'],config['alpha'])
        phase={'name':'before_fit'};model_counts={};encoder_counts={}
        def increment(counts):counts[phase['name']]=counts.get(phase['name'],0)+1
        model_hook=model.register_forward_pre_hook(lambda *_:increment(model_counts))
        encoder_hook=model.get_encoder().register_forward_pre_hook(lambda *_:increment(encoder_counts))
        with run.AppendJournal(out.with_suffix('.journal.jsonl'),report['planSha256']) as journal:
            journal.append('begin',{'runId':plan['runId'],'slots':slots})
            a={**slots[0],'status':'started','startedMonotonicNs':time.monotonic_ns(),'checkpoints':[]};report['activeAttempt']=a;journal.append('attempt_start',a)
            def checkpoint(name,payload):
                row={k:a[k] for k in ('arm','caseId','repeat')};row.update(name=name,payload=payload)
                journal.append('attempt_checkpoint',row);a['checkpoints'].append(copy.deepcopy(row))
                if name=='training_step_settled':report['trainingSteps']=payload['step']
                if name=='generation_started':report['businessGenerationCalls']+=1
            # Each phase has its first complete output; no retry/best-output pick.
            initial_adapter=adapter_state(model)
            if plan.get('baselineAdapter'):
                baseline=plan['baselineAdapter']['checkpoint']
                restore_adapter(model,torch.load(ROOT/baseline['path'],map_location='cpu',weights_only=True))
                if old.tensor_hash(adapter_state(model))!=baseline['tensorSha256']:raise ValueError('baseline tensor identity drift')
                checkpoint('baseline_adapter_loaded',baseline)
            if plan['purpose'].startswith('user_authorized'):
                a['beforePredictions']=generate_expressions(torch,model,tokenizer,train+dev,'before_fit',checkpoint,config)
            if plan.get('baselineAdapter'):
                restore_adapter(model,initial_adapter)
                if old.tensor_hash(adapter_state(model))!=old.tensor_hash(initial_adapter):raise ValueError('fresh adapter reset mismatch')
                checkpoint('fresh_adapter_restored',{'tensorSha256':old.tensor_hash(initial_adapter)})
            phase['name']='training'
            a['losses']=fit_adapter(torch,model,tokenizer,train,config,checkpoint)
            if old.tensor_hash(base_state(model))!=source_hash:raise ValueError('frozen source weights changed during fitting')
            a['checkpoint']=save_reload_adapter(torch,model,ROOT/'.local/world-components-logic/realizer-adapters'/plan['runId'],source_hash,checkpoint)
            adapter_hash=a['checkpoint']['tensorSha256']
            checkpoint('adapter_frozen',a['checkpoint']);phase['name']='after_fit'
            a['predictions']=generate_expressions(torch,model,tokenizer,train+dev,'after_fit',checkpoint,config)
            if old.tensor_hash(base_state(model))!=source_hash or old.tensor_hash(adapter_state(model))!=adapter_hash:raise ValueError('inference changed frozen model/adapter')
            model_hook.remove();encoder_hook.remove()
            a['modelTopForwardCallsByPhase']=model_counts;a['encoderForwardCallsByPhase']=encoder_counts
            checkpoint('model_forward_accounting',{'modelTopForwardCallsByPhase':model_counts,'encoderForwardCallsByPhase':encoder_counts})
            a['status']='complete';a['settledAt']=timestamp()
            t=time.perf_counter();journal.append('attempt_result',a);result_ms=(time.perf_counter()-t)*1000
            timing={k:a[k] for k in ('arm','caseId','repeat')}
            timing.update(resultJournalMs=result_ms,snapshotEndMs=0.,elapsedThroughResultMs=(time.monotonic_ns()-a['startedMonotonicNs'])/1e6)
            t=time.perf_counter();journal.append('attempt_settled',timing);a.update(timing)
            a['telemetryJournalMs']=(time.perf_counter()-t)*1000;a['elapsedIncludingTelemetryMs']=(time.monotonic_ns()-a['startedMonotonicNs'])/1e6
            report['attempts']=[a];report['activeAttempt']=None
        report['status']='diagnostic_completed';report['sourceWeightsUnchanged']=True;report['sourceFilesUnchanged']=observe_m02(ROOT)==plan['model'];report['unexecutedAttempts']=0
    except Exception as error:report.update(status='failed',error={'type':type(error).__name__,'message':str(error)})
    finally:save(out,report)
    return 0 if report['status']=='diagnostic_completed' else 1


def execute_training(path):
    result=run.execute_plan(path,paths=old.paths,verify=verify_training,worker_script=Path(__file__),settle_stages=old.settle_stages,arms=('fit',))
    plan=run.read_json(path);_,out=old.paths(plan['runId']);record=run.read_json(out)
    checkpoints=[c for a in record.get('attempts',[]) for c in a.get('checkpoints',[])]
    record['trainingStepAttempts']=sum(c['name']=='training_step_started' for c in checkpoints)
    record['trainingSteps']=sum(c['name']=='training_step_settled' for c in checkpoints)
    record['businessGenerationCalls']=sum(c['name']=='generation_started' for c in checkpoints)
    save(out,record);return result

INSPECTION_RUN='m02-realizer-inspect-20261104-r1'


def observed_inspection():
    pp,rp=old.paths(INSPECTION_RUN)
    if not rp.exists():return {'status':'not_run','sourceModelForwardCalls':None}
    plan=run.read_json(pp);record=run.read_json(rp)
    if record['planSha256']!=sha256_file(pp) or record['status']!='diagnostic_completed' or record['supervisor']['stopReason'] is not None:raise ValueError('inspection record invalid/incomplete')
    for name,h in plan['code'].items():
        if sha256_file(ROOT/name)!=h:
            # Exact historical execution remains verifiable after future edits.
            revisions=subprocess.check_output(['git','log','-30','--format=%H','--',name],cwd=ROOT,text=True).splitlines()
            if not any(__import__('hashlib').sha256(subprocess.check_output(['git','show',r+':'+name],cwd=ROOT)).hexdigest()==h for r in revisions):raise ValueError('inspection executed source unavailable: '+name)
    if plan['protocolSha256']!=sha256_file(PROTOCOL):raise ValueError('inspection protocol changed')
    replay=copy.deepcopy(record);run.reconcile_journal(replay,rp.with_suffix('.journal.jsonl'),'read_only_material_check')
    if replay['attempts']!=record['attempts'] or replay['journalRecovery']!=record['journalRecovery']:raise ValueError('inspection journal reconstruction differs')
    if len(record['attempts'])!=1:raise ValueError('inspection slot count drift')
    a=record['attempts'][0];layout=a['layout'];numeric=a['syntheticCheck']
    if (a['status']!='complete' or a['projectForwardCalls']!=0 or record['trainingSteps']!=0 or not record['sourceFilesUnchanged']
            or layout['sourceParameters']!=77440384 or layout['trainableAdapterParameters']!=172032
            or layout['totalInferenceParameters']!=77612416 or len(layout['targetModules'])!=48
            or not layout['initialOutputMatricesZero'] or not numeric['baseUnchanged'] or not numeric['checkpointReloadExact']):raise ValueError('inspection result identity drift')
    if not numeric['lossLast']<numeric['lossFirst'] or numeric['syntheticOptimizerSteps']!=8:raise ValueError('synthetic numeric check failed')
    return {'status':'layout_and_numeric_checks_passed_no_business_training','runId':INSPECTION_RUN,
        'sourceModelForwardCalls':0,'sourceParameters':layout['sourceParameters'],'trainableAdapterParameters':layout['trainableAdapterParameters'],
        'totalInferenceParameters':layout['totalInferenceParameters'],'adapterModules':len(layout['targetModules']),
        'syntheticNumericCheck':numeric,'supervisor':record['supervisor'],
        'planSha256':sha256_file(pp),'recordSha256':sha256_file(rp),'journalSha256':sha256_file(rp.with_suffix('.journal.jsonl'))}


def build_materials():
    rows=candidate_rows();raw=b''.join(canonical_bytes(r)+b'\n' for r in rows)
    old_inputs=BASE/'data/dev-inputs.jsonl';round_inputs=BASE/'data/round1-inputs/task-inputs.jsonl'
    prior_cases=[json.loads(line) for path in (old_inputs,round_inputs) for line in path.read_text().splitlines() if line.strip()]
    prior_hashes={digest(c['input']) for c in prior_cases if isinstance(c,dict) and 'input' in c}
    own_hashes=[r['sourceInputSha256'] for r in rows]
    if len(set(own_hashes))!=12 or set(own_hashes)&prior_hashes:raise ValueError('exact source duplication detected')
    # Preserve the actual L3-14 authoring version after extending this module.
    original=subprocess.check_output(['git','show',MATERIAL_COMMIT+':'+str(Path(__file__).relative_to(ROOT))],cwd=ROOT)
    if __import__('hashlib').sha256(original).hexdigest()!=MATERIAL_AUTHOR_SHA:raise ValueError('original candidate authoring source unavailable')
    manifest={'schema':'jity-d-realizer-training-source-candidates-v1','batchId':BATCH,'packetSha256':packet_identity(rows),
        'fileSha256':__import__('hashlib').sha256(raw).hexdigest(),'sourceHead':'49189351cf0a04a0cc3fafd15a8eab0248b1a10d',
        'authoringCodeSha256':MATERIAL_AUTHOR_SHA,'protocolSha256':sha256_file(PROTOCOL),
        'sources':[{'annotationId':r['annotationId'],'annotationSha256':digest(r),'sourceGroup':r['sourceGroup'],
                    'role':r['role'],'sourceInputSha256':r['sourceInputSha256'],'coverage':r['coverage']} for r in rows],
        'ownDExactInputOverlap':0,'comparisonSources':{str(p.relative_to(ROOT)):sha256_file(p) for p in (old_inputs,round_inputs)},
        'semanticSourceIndependence':'unverified_exact_hashes_are_not_independence_proof','trainingEligible':False,
        'formalEvaluationAllowed':False,'protectedBCContentRead':False,'newIndependentTrainingGroups':0,'round1TrainingQuota':0}
    inspection=observed_inspection()
    summary={'schema':'jity-d-realizer-training-readiness-summary-v1','date':'2026-11-04','batchId':BATCH,
        'stage':'L3 short-realizer trainer and new source candidates; business training not started',
        'scope':'trainer_implementation_candidate_annotations_and_no_business_model_inspection',
        'draftSourceGroups':12,'trainCandidateGroups':6,'developmentCandidateGroups':6,
        'coverage':sorted({r['coverage'] for r in rows}),'review':reconcile_reviews(rows),
        'realizerTrainerImplemented':True,'plannerModelImplemented':False,'realizerTrained':False,
        'trainingSteps':0,'businessInferenceCalls':0,'newIndependentTrainingGroups':0,'round1TrainingQuota':0,
        'formalEvaluationAllowed':False,'semanticQualityApproved':False,'fullRequest500msStatus':'unverified','local50msHardGate':False,
        'lastModelRun':'action-focus-dev42-20261104-r2','inspection':inspection,
        'missingBeforeBusinessTraining':['new_plan_and_expression_label_review','source_semantic_independence_for_formal_claims','frozen_reviewed_training_instance'],
        'sourceManifest':str((DATA/'source-manifest.json').relative_to(ROOT)),'packetSha256':packet_identity(rows)}
    return summary,{DATA/'candidates.jsonl':raw,DATA/'source-manifest.json':canonical_bytes(manifest)+b'\n',
        ART/'l3-14-realizer-training-readiness-summary.json':(json.dumps(summary,ensure_ascii=False,indent=2)+'\n').encode(),
        ART/'l3-14-realizer-training-readiness.html':render_materials(summary,rows).encode()}


def render_materials(summary,rows):
    import html
    e=lambda v:html.escape(str(v))
    parts=['''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>L3 短表达训练准备与模型装配</title><style>body{margin:0;background:#f4f6f8;color:#20313e;font:16px/1.7 system-ui}main{max-width:1100px;margin:auto;padding:24px}section{background:white;padding:22px;border-radius:12px;margin:20px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}.warn{color:#a7352e}table{width:100%;border-collapse:collapse}td,th{padding:10px;text-align:left;border-bottom:1px solid #ddd}</style><main><p>D / L3 · 2026-11-04</p><h1>短表达训练程序与12组新来源候选</h1><section><h2>程序已补上，业务训练尚未开始</h2><p>实现了冻结原77M模型、只训练新增适配层的程序，包括完整分词/超限拒绝、分组隔离、损失与梯度记录、适配层存档/重载、冻结后输出原文和调用计数。输入是给定动作计划，覆盖物品、工具、目的地、接收人/话语、有序多步和无对象开放动作。</p><p class="warn">12组新写来源、计划和参考表达均是AI未审候选，预分6训练/6开发；可用于训练0组。没有把这些草稿送进模型，没有新的语义成绩或500ms成绩。它们与旧题/90卡分开登记，语义来源独立性仍待核验。</p><p>完整动作规划器仍未实现；即使将来表达器能学习人工计划，也只能证明表达这一步，不能冒充开放行动选择。</p></section>''']
    inspection=summary['inspection']
    parts.append('<section><h2>真实模型做了什么检查？</h2>')
    if inspection['status']=='not_run':parts.append('<p>模型装配检查尚未运行。</p>')
    else:
        parts.append(f'<p>在D本地加载原M02的{inspection["sourceParameters"]:,}参数；实际安装{inspection["adapterModules"]}个适配位置、{inspection["trainableAdapterParameters"]:,}个可训练参数。推理仍需{inspection["totalInferenceParameters"]:,}个总参数，不能说模型只有0.17M。</p><p>业务模型前向0次、业务训练0步。另用独立的8维合成张量模块做8步梯度检查，验证新增参数可更新、原权重不变、存档重载输出相同；这不是项目模型训练，也不说明业务质量或速度。</p>')
        parts.append(f'<details><summary>装配与合成检查原始结果</summary><pre>{e(json.dumps(inspection,ensure_ascii=False,indent=2))}</pre></details><p><a href="m01-fitting/{INSPECTION_RUN}.plan.json">检查计划</a> · <a href="m01-fitting/{INSPECTION_RUN}.record.json">原始检查记录</a> · <a href="m01-fitting/{INSPECTION_RUN}.record.journal.jsonl">完整检查事件</a></p>')
    parts.append('</section><section><h2>下一次业务训练怎么跑？</h2><p>新标签核对齐备后，先冻结新训练实例，再用CPU单线程/并发1、120秒/2048MiB保护执行。预登记rank4/alpha8、AdamW 0.001、80步、每批2条；不靠开发集早停，超长完整输入拒绝、不截断。训练后保存/重载适配层，再把训练/开发全部首次生成原文保留。实际业务路径尚未运行，不能先签能训练成功或模型可用。</p><p>新审核意见须绑定这12组的batch/packet/annotation哈希；旧42题或上一批10计划的意见不能套用。代码只核验意见与数据身份，不认证人或签正式质量；来源核验未完成时仅允许登记有限探索，不能进入正式封存验收。</p></section>')
    for r in rows:
        c=r['sourceCase'];actor_name=contract.lookup(c)[('character',c['input']['actorId'])]['name']
        parts.append(f'<section><h2>{e(r["annotationId"])} · {e(r["role"])} · {e(r["coverage"])}</h2><p><strong>AI未审候选／不可训练。</strong> 场景：{e(c["input"]["world"]["places"][0]["name"])}；当前人物：{e(actor_name)}。</p><p>短表达参考草稿：{e(r["expressionDraft"])}</p><details><summary>完整场景、计划和表达器输入（均未投模型）</summary><pre>{e(json.dumps({"sourceCase":c,"planDraft":r["planDraft"],"expressionInput":realizer_payload(r)},ensure_ascii=False,indent=2))}</pre></details><p>来源SHA：{e(r["sourceInputSha256"])}</p></section>')
    parts.append(f'<section><details><summary>准备状态与待补项</summary><pre>{e(json.dumps(summary,ensure_ascii=False,indent=2))}</pre></details><p><a href="l3-14-realizer-training-readiness-summary.json">机器状态</a> · <a href="../../experiments/world-components-logic/data/action-plan-training/candidates.jsonl">12组全部候选</a> · <a href="../../experiments/world-components-logic/data/action-plan-training/source-manifest.json">来源与哈希</a> · <a href="l3-13-action-plan-preparation.html">上一批旧题计划草稿</a> · <a href="https://arxiv.org/abs/2106.09685">LoRA原论文</a></p></section></main></html>')
    return ''.join(parts)


def prepare_materials(write=False):
    summary,files=build_materials()
    for path,raw in files.items():
        if path.exists() and path.read_bytes()!=raw:raise ValueError('preserve delivered materials; new batch required: '+str(path))
        if not write and not path.exists():raise ValueError('training material missing: '+str(path))
    if write:
        for path,raw in files.items():
            path.parent.mkdir(parents=True,exist_ok=True)
            if not path.exists():
                with path.open('xb') as f:f.write(raw)
    return summary


def verify_historical_file(path,expected):
    if path.exists() and sha256_file(path)==expected:return
    name=str(path.relative_to(ROOT))
    revisions=subprocess.check_output(['git','log','-30','--format=%H','--',name],cwd=ROOT,text=True).splitlines()
    for revision in revisions:
        raw=subprocess.check_output(['git','show',revision+':'+name],cwd=ROOT)
        if __import__('hashlib').sha256(raw).hexdigest()==expected:return
    raise ValueError('executed source/protocol unavailable: '+name)


def observed_smoke():
    pp,rp=old.paths(SMOKE_RUN);plan=run.read_json(pp);record=run.read_json(rp)
    if (record['planSha256']!=sha256_file(pp) or record['status']!='diagnostic_completed'
            or record['supervisor']['stopReason'] is not None or record['supervisor']['exitCode']!=0):raise ValueError('synthetic smoke incomplete')
    if (plan['purpose']!='real_m02_synthetic_training_save_reload_only' or plan['config']!=SMOKE_CONFIG
            or plan['syntheticExamples']!=list(SYNTHETIC_EXAMPLES) or plan['syntheticExamplesSha256']!=digest(list(SYNTHETIC_EXAMPLES))
            or plan['businessTrainingSteps']!=0 or plan['businessInferenceCalls']!=0 or plan['businessSourceGroups']!=0
            or plan['formalEvaluationAllowed'] is not False):raise ValueError('synthetic recorded scope drift')
    for name,h in plan['code'].items():verify_historical_file(ROOT/name,h)
    verify_historical_file(SMOKE_PROTOCOL,plan['protocolSha256'])
    replay=copy.deepcopy(record);run.reconcile_journal(replay,rp.with_suffix('.journal.jsonl'),'read_only_material_check')
    if replay['attempts']!=record['attempts'] or replay['journalRecovery']!=record['journalRecovery']:raise ValueError('synthetic journal reconstruction differs')
    if len(record['attempts'])!=1:raise ValueError('synthetic slot count drift')
    a=record['attempts'][0];check=a['syntheticFullModelCheck'];events=a['checkpoints'];forwards=check['modelForwards']
    if (a['status']!='complete' or a['projectForwardCalls']!=0 or check['sourceParameters']!=77440384
            or check['trainableAdapterParameters']!=172032 or check['totalInferenceParameters']!=77612416 or check['adapterModules']!=48
            or check['syntheticExamples']!=list(SYNTHETIC_EXAMPLES) or check['syntheticOptimizerSteps']!=2
            or len(check['losses'])!=2 or not check['changedAdapterTensors']
            or any(not check[k] for k in ('sourceBaseUnchanged','baseGradientsAbsent','zeroAdapterLogitsExact','reloadedLogitsExact','reloadedGeneratedTokensExact'))
            or check['businessTrainingSteps']!=0 or check['businessInferenceCalls']!=0
            or check['semanticQualityApproved'] is not False or check['fullRequestMeasured'] is not False
            or record['trainingSteps']!=0 or not record['sourceFilesUnchanged']):raise ValueError('synthetic result identity drift')
    starts=[c['payload'] for c in events if c['name']=='training_step_started'];settled=[c['payload'] for c in events if c['name']=='training_step_settled']
    if ([c['step'] for c in starts]!=[1,2] or [c['step'] for c in settled]!=[1,2]
            or [c['loss'] for c in settled]!=check['losses'] or record['syntheticTrainingStepAttempts']!=2 or record['syntheticOptimizerSteps']!=2):raise ValueError('synthetic step ledger mismatch')
    for row in starts:
        if set(row['sourceGroups'])!={e['sourceGroup'] for e in SYNTHETIC_EXAMPLES}:raise ValueError('synthetic training batch drift')
    expected_phases={'source_reference':1,'zero_adapter_equivalence':1,'synthetic_optimizer':2,'fitted_teacher_forced':1,'reloaded_teacher_forced':1}
    phases={p:sum(f['phase']==p for f in forwards) for p in sorted({f['phase'] for f in forwards})}
    for phase,count in expected_phases.items():
        if phases.get(phase)!=count:raise ValueError('synthetic forward phase count drift')
    for phase in ('synthetic_generation_before_reload','synthetic_generation_after_reload'):
        if not 1<=phases.get(phase,0)<=SMOKE_CONFIG['maxNewTokens']:raise ValueError('synthetic generation count drift')
    if set(phases)!=set(expected_phases)|{'synthetic_generation_before_reload','synthetic_generation_after_reload'}:raise ValueError('unexpected model forward phase')
    if any(f['index']!=i or f['status']!='complete' or f['gradEnabled']!=(f['phase']=='synthetic_optimizer') for i,f in enumerate(forwards)):raise ValueError('synthetic forward gradient/status drift')
    forward_events=[c['payload'] for c in events if c['name']=='model_forward_settled']
    if (forward_events!=forwards or len(forwards)!=check['modelTopForwardCalls'] or a['syntheticModelForwardCalls']!=len(forwards)
            or record['syntheticForwardAttempts']!=len(forwards) or record['syntheticForwardsCompleted']!=len(forwards)):raise ValueError('synthetic forward ledger mismatch')
    names=[c['name'] for c in events]
    if not names.index('adapter_save_started')<names.index('adapter_saved')<names.index('adapter_cleared')<names.index('adapter_reloaded')<names.index('full_model_reload_equivalence'):raise ValueError('synthetic checkpoint order drift')
    if not next(c['payload'] for c in events if c['name']=='adapter_cleared')['allTrainableZero']:raise ValueError('synthetic adapter was not cleared')
    before,after=check['syntheticGenerations']
    if before['tokenIds']!=after['tokenIds'] or before['maxNewTokens']!=8 or after['maxNewTokens']!=8:raise ValueError('synthetic generated tokens differ')
    return {'schema':'jity-d-realizer-synthetic-training-summary-v1','date':'2026-11-04','batchId':SMOKE_RUN,
        'stage':'L3-15 real M02 synthetic training and disk reload check; no business training',
        'scope':'engineering_numeric_fixture_not_action_training_or_latency_evaluation','lastModelRun':'action-focus-dev42-20261104-r2',
        'draftSourceGroups':12,'review':reconcile_reviews(candidate_rows()),'realizerTrainerImplemented':True,
        'plannerModelImplemented':False,'realizerTrained':False,'businessTrainingSteps':0,'businessInferenceCalls':0,
        'formalEvaluationAllowed':False,'semanticQualityApproved':False,'fullRequest500msStatus':'unverified',
        'realModelSyntheticCheck':check,'forwardPhaseCounts':phases,'supervisor':record['supervisor'],
        'planSha256':sha256_file(pp),'recordSha256':sha256_file(rp),'journalSha256':sha256_file(rp.with_suffix('.journal.jsonl'))}


def smoke_materials(write=False):
    import html
    summary=observed_smoke();check=summary['realModelSyntheticCheck'];e=lambda v:html.escape(str(v))
    document='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>L3-15 真实模型训练通路检查</title><style>body{margin:0;background:#f4f6f8;color:#20313e;font:16px/1.7 system-ui}main{max-width:1000px;margin:auto;padding:24px}section{background:white;padding:24px;border-radius:12px;margin:20px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}table{border-collapse:collapse;width:100%}td,th{padding:10px;text-align:left;border-bottom:1px solid #ddd}.warn{color:#a7352e}</style><main><p>D / L3-15 · 2026-11-04</p><h1>真实77M模型的训练、存档和重载已跑通</h1><section><h2>本次解决了什么？</h2><p>上次实际77M模型只做了装配，训练更新在8维小模拟层上检查。这次用真实原模型和两行合成数字输入，实际走完前向、反向更新、写入磁盘、清空适配参数、重载和生成对照。训练和存档函数与将来的业务训练共用。</p><p class="warn">这是数值工程检查。没有使用游戏场景或新增未审标签，也没有训练业务模型；12组新标签仍待核对，动作规划器仍未实现，质量与完整500ms尚未通过。</p></section>'''
    document+=f'<section><h2>实际检查结果</h2><table><tr><th>项目</th><th>结果</th></tr><tr><td>原模型参数 / 新增可训练参数</td><td>{check["sourceParameters"]:,} / {check["trainableAdapterParameters"]:,}；总推理仍{check["totalInferenceParameters"]:,}</td></tr><tr><td>实际合成优化步数</td><td>{check["syntheticOptimizerSteps"]}步；业务训练0步</td></tr><tr><td>零适配层与原模型</td><td>完整logits逐值相同</td></tr><tr><td>底座是否保持不变</td><td>张量SHA与源文件均不变，无底座梯度</td></tr><tr><td>磁盘重载后</td><td>适配张量、完整logits、生成token逐值相同</td></tr><tr><td>实际顶层模型前向</td><td>{check["modelTopForwardCalls"]}次，含两个优化步骤和全部生成解码</td></tr><tr><td>监督进程总耗时 / RSS</td><td>{summary["supervisor"]["wallMs"]/1000:.2f}秒 / {summary["supervisor"]["observedPeakResidentMiB"]:.2f}MiB，CPU单线程</td></tr></table><p>原始合成损失：{e(check["losses"])}。损失变化只说明数值计算发生，不能表示模型理解了行动。这里的耗时包括准备和工程核查，不是游戏性能成绩。</p></section>'
    document+='<section><h2>下一步</h2><p>新标签/来源核对齐备后固定真实小批训练实例，训练短表达器，再验证真实动作规划与协作链；不能把“给好计划再成句”当成模型自主选择行动。</p></section>'
    document+=f'<section><details><summary>全部原始数字、调用和检查结果</summary><pre>{e(json.dumps(summary,ensure_ascii=False,indent=2))}</pre></details><p><a href="l3-15-realizer-smoke-summary.json">机器汇总</a> · <a href="m01-fitting/{SMOKE_RUN}.plan.json">冻结计划</a> · <a href="m01-fitting/{SMOKE_RUN}.record.json">原始记录</a> · <a href="m01-fitting/{SMOKE_RUN}.record.journal.jsonl">完整事件</a> · <a href="l3-14-realizer-training-readiness.html">12组候选和上批准备</a> · <a href="../../design/world-engine-reports/components-logic/realizer-training-smoke-protocol.md">本批协议</a></p></section></main></html>'
    files={ART/'l3-15-realizer-smoke-summary.json':(json.dumps(summary,ensure_ascii=False,indent=2)+'\n').encode(),ART/'l3-15-realizer-smoke.html':document.encode()}
    for path,raw in files.items():
        if path.exists() and path.read_bytes()!=raw:raise ValueError('preserve delivered synthetic result: '+str(path))
        if not write and not path.exists():raise ValueError('synthetic result material missing')
    if write:
        for path,raw in files.items():
            if not path.exists():
                with path.open('xb') as stream:stream.write(raw)
    return summary


# These are authored assistant judgments, not a semantic rule engine or a human
# review receipt. The checks below only guard their source/version identities.
AUDIT_NOTES={
 '01':'主角pending输入与当前任务均要求合上铜印匣；计划引用已有item_1，表达只说尝试，没有宣布匣子已合好。',
 '02':'主角pending输入要求打开木笛盒；计划只先尝试打开，没有擅自写成已经查看完收纳情况。',
 '03':'当前NPC是林芩p2，软毛刷在p2身上，托盘在同一位置；清扫依据自己的待办任务，未重做consumed登记请求。',
 '04':'当前NPC沈墨p2使用自己持有的竹夹夹试茶片，表达保留工具/对象；expired计时询问没有被重新执行。',
 '05':'渠澈p1从封蜡台走向已登记的验章桌，只表达移动尝试，没有提前完成当班事务。与06为相近移动题型，独立性待核。',
 '06':'覃漪p1的pending输入和任务均支持走向资料柜；未宣告已完成星表整理。与05为相近移动题型，独立性待核。',
 '07':'季玄p1向另一人物闻简p2提出停机请求；压版机已登记，原话保留，没有写成闻简已服从或机器已停止。',
 '08':'安砚p2基于自身任务向闻简p1请求样签，人物方向正确；consumed釉温请求未重做，也未把样签转移写成既成事实。',
 '09':'先尝试把折尺放进量尺袋，再尝试把袋子放到标定台；对象/容器/地点及顺序保留，没有新增人物或物品。',
 '10':'原任务涉及从已熄灭灯具抽出旧灯芯，但灯具未登记，灯芯却直接在桌面。r2补item_3灯具及灯芯嵌套位置和可抽出条件；计划/表达的动作及次序不改。',
 '11':'楚澜p2按自己的待办任务尝试回想字音；开放动词无需伪造物品ID，未重做consumed编号请求，未宣告已经想起。',
 '12':'谷雨p2按待办任务尝试辨听滴水间隔；expired报时询问不作为新命令，未新增数值答案或宣告辨听成功。',
}
AUDIT_BASE_COMMIT='bbf930cd21e9f47a0c69e80a4c1f1b06a5b69a02'


def audited_candidate_rows():
    rows=copy.deepcopy(candidate_rows());row=next(r for r in rows if r['annotationId']=='realizer-new-10')
    original_sha=digest(row);w=row['sourceCase']['input']['world']
    w['items'].append({'id':'item_3','name':'已熄灭灯具','position':{'containerId':'loc_a','slot':'可见位置'},
                       'appearance':'已熄灭并冷却，灯芯座已松开，可徒手取出旧灯芯。'})
    w['items'][0]['position']={'containerId':'item_3','slot':'已松开的灯芯座'}
    row['planDraft']['basis']+=['/world/items/0','/world/items/2']
    row.update(sourceInputSha256=digest(row['sourceCase']['input']),planSha256=digest(row['planDraft']),
               revisionOfAnnotationSha256=original_sha)
    for r in rows:
        contract.validate_candidate(r['sourceCase'],r['planDraft'])
        if r['sourceInputSha256']!=digest(r['sourceCase']['input']) or r['planSha256']!=digest(r['planDraft']):raise ValueError('audited source/plan hash drift')
    return rows


def label_audit_materials(write=False):
    import html
    e=lambda v:html.escape(str(v));original=candidate_rows();revised=audited_candidate_rows()
    saved=[json.loads(line) for line in (DATA/'candidates.jsonl').read_text().splitlines() if line.strip()]
    if saved!=original:raise ValueError('preserve original r1 candidates')
    entries=[]
    for a,b in zip(original,revised):
        if any(a[k]!=b[k] for k in ('annotationId','sourceGroup','role','coverage','expressionDraft','expressionSha256')):raise ValueError('audit changed labels or source roles')
        if input_text(a)!=input_text(b):raise ValueError('audit changed expression input')
        key=a['annotationId'][-2:]
        entries.append({'annotationId':a['annotationId'],'sourceGroup':a['sourceGroup'],'role':a['role'],'coverage':a['coverage'],
            'originalAnnotationSha256':digest(a),'revisedAnnotationSha256':digest(b),
            'verdict':'context_gap_corrected' if key=='10' else 'no_blocking_contradiction_found',
            'assistantReason':AUDIT_NOTES[key],'humanReviewPerformed':False})
    raw=b''.join(canonical_bytes(r)+b'\n' for r in revised)
    manifest={'schema':'jity-d-realizer-candidate-revision-v1','batchId':AUDIT_BATCH,'supersedes':BATCH,
        'sourceHead':AUDIT_BASE_COMMIT,'originalDataSha256':sha256_file(DATA/'candidates.jsonl'),
        'originalManifestSha256':sha256_file(DATA/'source-manifest.json'),
        'originalPacketSha256':packet_identity(original),'packetSha256':packet_identity(revised,batch_id=AUDIT_BATCH),
        'fileSha256':__import__('hashlib').sha256(raw).hexdigest(),'auditKind':'assistant_precheck_not_human_label_approval',
        'sources':[{k:r[k] for k in ('annotationId','sourceGroup','role','sourceInputSha256','planSha256','expressionSha256')}|{'annotationSha256':digest(r)} for r in revised],
        'sourceGroupsPreserved':True,'newIndependentTrainingGroups':0,'semanticSourceIndependence':'unverified',
        'trainingEligible':False,'formalEvaluationAllowed':False}
    summary={'schema':'jity-d-realizer-assistant-label-audit-v1','date':'2026-11-04','batchId':AUDIT_BATCH,
        'stage':'L3-16 twelve candidate labels audited by assistant; one source context repaired',
        'reviewKind':'assistant_precheck_not_human_label_approval','auditAuthor':'assistant',
        'auditSpecificationSha256':digest(AUDIT_NOTES),'checkedAnnotations':12,'originalWithoutBlockingFinding':11,
        'correctedSourceInputs':1,'changedExpressionTargets':0,'changedRealizerInputs':0,
        'originalDataSha256':manifest['originalDataSha256'],'originalPacketSha256':manifest['originalPacketSha256'],
        'packetSha256':manifest['packetSha256'],'draftSourceGroups':12,'trainCandidateGroups':6,'developmentCandidateGroups':6,
        'review':reconcile_reviews(revised,batch_id=AUDIT_BATCH),'entries':entries,
        'sourceRisks':[{'caseIds':['realizer-new-05','realizer-new-06'],'risk':'similar_movement_to_workstation_family_cross_split',
            'note':'两题均从工作台走向另一工作点，不能只用换名/哈希不同证明独立；保留原角色，不签独立泛化，正式比较前需同源复核。'}],
        'coverageLimits':['all_12_are_act_expression_examples_not_act_skip_training','no_wrong_plan_negatives',
                          'no_open_planner_reaction_or_joint_outcome_validation','only_one_candidate_per_split_per_coverage'],
        'namePolicy':'甲/乙为schema helper附加的显示后缀；参考句省略后缀，各场景基础姓名唯一，无人物方向混淆；不要求参考句逐字唯一。',
        'realizerTrainerImplemented':True,'plannerModelImplemented':False,'realizerTrained':False,
        'formalEvaluationAllowed':False,'semanticQualityApproved':False,'fullRequest500msStatus':'unverified',
        'businessTrainingSteps':0,'businessInferenceCalls':0,'lastModelRun':'action-focus-dev42-20261104-r2',
        'trainingPacketSupersedes':BATCH,'sourceIndependence':'unverified','newIndependentTrainingGroups':0}
    document='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>L3-16 十二组标签核对</title><style>body{margin:0;background:#f4f6f8;color:#20313e;font:16px/1.7 system-ui}main{max-width:1100px;margin:auto;padding:24px}section{background:#fff;padding:22px;border-radius:12px;margin:20px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}.warn{color:#a7352e}table{width:100%;border-collapse:collapse}td,th{padding:10px;text-align:left;border-bottom:1px solid #ddd}</style><main><p>D / L3-16 · 2026-11-04</p><h1>12组已逐条核对，修正1处场景缺口</h1><section><p>逐条核对人物及任务、pending/consumed/expired处理、动作引用、工具/对象/目的地/接收人、步骤次序和“只描述尝试”。其余11项未发现阻断矛盾，第10项已保存修订2；12条表达输入和参考句保持原文。</p><p>本页是助手的数据预检记录，人工复核数量仍为0，不生成或冒充人工回执；本次没有运行模型或训练。</p></section><section><h2>修正了什么？</h2><p>第10题要求从灯具抽出旧灯芯，原场景却没有灯具，且灯芯直接在桌面。修订2在初始场景补登记item_3已熄灭灯具，明确冷却/灯芯座已松开，灯芯位置指向灯具，并将两项证据加入计划basis。动作仍是“抽出灯芯，再放入瓷碟”，没有改答案迎合模型；这属于实验初态补全，运行中不会由程序新增实体。</p><p>原版文件和组名保留；修订版不会被算作额外12个独立来源，旧批次回执也不能直接套用。</p></section><section><h2>另外发现的范围限制</h2><p class="warn">第5/6题是相近的移动工作点题型，需继续核对来源关系；哈希不同不能证明语义独立。本批全部是act后的表达样本，不能用来证明行动/不行动判断、开放动作规划、反应或共同结果能力。每类每边只有1组，不签泛化或完整500ms。</p></section>'''
    for item,row in zip(entries,revised):
        c=row['sourceCase'];person=contract.lookup(c)[('character',c['input']['actorId'])]
        document+=f'<section><h2>{e(row["annotationId"])} · {e(row["coverage"])} · {e(row["role"])}</h2><p><strong>{"已补齐场景缺口" if item["verdict"]=="context_gap_corrected" else "预检未发现阻断矛盾"}</strong></p><p>当前人物：{e(person["name"])}；任务：{e(person["tasks"][0]["text"])}。</p><p>玩家输入（{e(c["input"]["advance"]["intentStatus"])}）：{e(c["input"]["advance"]["inputText"])}</p><p>参考表达：{e(row["expressionDraft"])}</p><p>核对依据：{e(item["assistantReason"])}</p><details><summary>完整修订场景与计划</summary><pre>{e(json.dumps(row,ensure_ascii=False,indent=2))}</pre></details></section>'
    document+='<section><p><a href="l3-16-label-audit-summary.json">核对记录</a> · <a href="../../experiments/world-components-logic/data/action-plan-training/r2/candidates.jsonl">修订2数据</a> · <a href="../../experiments/world-components-logic/data/action-plan-training/r2/source-manifest.json">修订身份与来源</a> · <a href="l3-14-realizer-training-readiness.html">原始12组</a></p></section></main></html>'
    files={AUDIT_DATA/'candidates.jsonl':raw,AUDIT_DATA/'source-manifest.json':canonical_bytes(manifest)+b'\n',
        ART/'l3-16-label-audit-summary.json':(json.dumps(summary,ensure_ascii=False,indent=2)+'\n').encode(),
        ART/'l3-16-label-audit.html':document.encode()}
    for path,raw in files.items():
        if path.exists() and path.read_bytes()!=raw:raise ValueError('preserve delivered label audit: '+str(path))
        if not write and not path.exists():raise ValueError('label audit material missing: '+str(path))
    if write:
        for path,raw in files.items():
            path.parent.mkdir(parents=True,exist_ok=True)
            if not path.exists():
                with path.open('xb') as stream:stream.write(raw)
    return summary


def observed_fit(run_id=FIT_RUN):
    """Read-only evidence reconstruction; no weight load and no semantic judge."""
    import math
    import statistics
    profile=fit_profile(run_id);expected_steps=profile['config']['steps'];pp,rp=old.paths(run_id);plan=run.read_json(pp);record=run.read_json(rp)
    if record['planSha256']!=sha256_file(pp):raise ValueError('fit plan identity drift')
    if plan['purpose']!='user_authorized_draft_plan_to_text_exploratory_adapter_fit' or plan['config']!=profile['config'] or plan['formalEvaluationAllowed'] is not False:raise ValueError('fit scope drift')
    train,dev=admitted_training_data(plan);rows=train+dev
    authorization_path=ART/'m01-fitting'/f'{run_id}.authorization.json'
    if sha256_file(authorization_path)!=plan['authorizationFileSha256'] or run.read_json(authorization_path)!=plan['draftAuthorization']:raise ValueError('fit authorization evidence drift')
    if (plan['candidatePacketSha256']!=profile['packetSha256'] or plan['candidateAuditManifestSha256']!=sha256_file(profile['manifest'])):raise ValueError('fit source revision drift')
    for name,h in plan['code'].items():verify_historical_file(ROOT/name,h)
    verify_historical_file(PROTOCOL,plan['protocolSha256']);verify_historical_file(profile['protocol'],plan['exploratoryProtocolSha256'])
    replay=copy.deepcopy(record);journal=rp.with_suffix('.journal.jsonl')
    if journal.exists():
        run.reconcile_journal(replay,journal,'read_only_result_check')
        if replay['attempts']!=record['attempts'] or replay['journalRecovery']!=record['journalRecovery']:raise ValueError('fit journal reconstruction differs')
    events=[c for a in record.get('attempts',[]) for c in a.get('checkpoints',[])]
    starts=[c['payload'] for c in events if c['name']=='training_step_started'];steps=[c['payload'] for c in events if c['name']=='training_step_settled']
    if ([s['step'] for s in starts]!=list(range(1,len(starts)+1)) or [s['step'] for s in steps]!=list(range(1,len(steps)+1))
            or len(starts)>expected_steps or len(steps)>len(starts) or record['trainingSteps']!=len(steps)
            or record['trainingStepAttempts']!=len(starts)):raise ValueError('fit optimizer ledger mismatch')
    train_groups={r['sourceGroup'] for r in train};exposures={r['sourceGroup']:0 for r in train}
    for step in starts:
        if len(step['sourceGroups'])!=2 or not set(step['sourceGroups'])<=train_groups:raise ValueError('development or unknown group used for gradient')
        if profile['baseline'] and (len(step.get('annotationIds',[]))!=2 or any((a,g) not in {(r['annotationId'],r['sourceGroup']) for r in train} for a,g in zip(step['annotationIds'],step['sourceGroups']))):raise ValueError('wrong grouped example used for gradient')
        for group in step['sourceGroups']:exposures[group]+=1
    if any(not math.isfinite(s['loss']) or not math.isfinite(s['gradientNorm']) or s['elapsedThroughUpdateMs']<0 for s in steps):raise ValueError('invalid recorded training cost/loss')
    generations=[c['payload'] for c in events if c['name']=='generation_output'];begun=[c['payload'] for c in events if c['name']=='generation_started']
    if record['businessGenerationCalls']!=len(begun):raise ValueError('fit generation attempt count mismatch')
    lookup={r['annotationId']:r for r in rows};seen=set();by_phase={'before_fit':[],'after_fit':[]}
    for p in generations:
        key=(p['phase'],p['annotationId']);row=lookup.get(p['annotationId'])
        if key in seen or p['phase'] not in by_phase or row is None:raise ValueError('duplicate/unknown fit prediction')
        if (p['sourceGroup']!=row['sourceGroup'] or p['role']!=row['role'] or p['inputText']!=input_text(row)
                or p['inputSha256']!=digest(realizer_payload(row)) or p['semanticReview']!='pending_not_approved'
                or not p['inputTokenIds'] or len(p['inputTokenIds'])>CONFIG['maxInputTokens']
                or p['modelTopForwardCalls']!=len(p['tokenIds'])-1
                or p['eos']!=(p['tokenIds'][-1]==1)):raise ValueError('fit input/output identity drift')
        timing=next((c['payload'] for c in events if c['name']=='generation_timing' and c['payload']['phase']==p['phase'] and c['payload']['annotationId']==p['annotationId']),None)
        if timing is None or timing['elapsedIncludingOutputJournalMs']<p['elapsedMs']:raise ValueError('fit generation timing missing')
        seen.add(key);by_phase[p['phase']].append({**p,'elapsedIncludingOutputJournalMs':timing['elapsedIncludingOutputJournalMs']})
    complete=record['status']=='diagnostic_completed'
    checkpoint=next((c['payload'] for c in events if c['name']=='adapter_frozen'),None)
    counts=None
    if complete:
        if (len(starts)!=expected_steps or len(steps)!=expected_steps or len(generations)!=2*len(rows) or len(begun)!=2*len(rows)
                or checkpoint is None or not record['sourceWeightsUnchanged'] or not record['sourceFilesUnchanged']
                or record['supervisor']['stopReason'] is not None or record['supervisor']['exitCode']!=0):raise ValueError('completed fit missing required work')
        for phase,items in by_phase.items():
            if [p['annotationId'] for p in items]!=[r['annotationId'] for r in rows]:raise ValueError('fit phase omitted/reordered a source')
        counts=next(c['payload'] for c in events if c['name']=='model_forward_accounting')
        if counts['modelTopForwardCallsByPhase']!={'training':expected_steps,**{phase:sum(p['modelTopForwardCalls'] for p in items) for phase,items in by_phase.items()}}:raise ValueError('fit top forward count differs')
        if counts['encoderForwardCallsByPhase']!={'training':expected_steps,'before_fit':len(rows),'after_fit':len(rows)}:raise ValueError('fit encoder forward count differs')
        if record['attempts'][0]['losses']!=[s['loss'] for s in steps]:raise ValueError('fit loss snapshots differ')
        if profile['baseline']:
            baseline=next(c['payload'] for c in events if c['name']=='baseline_adapter_loaded')
            if plan.get('baselineAdapter')!=profile['baseline'] or baseline!=profile['baseline']['checkpoint']:raise ValueError('fit comparison baseline drift')
            if not any(c['name']=='fresh_adapter_restored' for c in events):raise ValueError('new fit did not reset source adapter')
    comparisons=[]
    for row in rows:
        pair={phase:next((p for p in items if p['annotationId']==row['annotationId']),None) for phase,items in by_phase.items()}
        comparisons.append({'annotationId':row['annotationId'],'sourceGroup':row['sourceGroup'],'role':row['role'],'coverage':row['coverage'],
                            'referenceDraft':row['expressionDraft'],**pair})
    costs={phase:{role:{'count':len(items:=[p for p in predictions if p['role']==role]),
        'medianMs':statistics.median(p['elapsedIncludingOutputJournalMs'] for p in items) if items else None,
        'maxMs':max((p['elapsedIncludingOutputJournalMs'] for p in items),default=None),
        'eosOutputs':sum(p['eos'] for p in items),'exactReferenceStrings':sum(p['raw']==lookup[p['annotationId']]['expressionDraft'] for p in items)}
        for role in ('train_candidate','development_candidate')} for phase,predictions in by_phase.items()}
    summary={'schema':'jity-d-realizer-exploratory-fit-summary-v1','date':'2026-11-04','batchId':run_id,
        'stage':'L3-17 first user-authorized short-realizer draft fit and before/after outputs','runStatus':record['status'],
        'lastModelRun':run_id,'draftSourceGroups':len({r['sourceGroup'] for r in rows}),'review':reconcile_reviews(audited_candidate_rows(),batch_id=AUDIT_BATCH) if not profile['baseline'] else {'reviewedGroups':0,'missingReviews':len(rows),'trainingDataReady':False,'formalEvaluationAllowed':False},
        'labelProvenance':'assistant_checked_draft_not_human_gold','userAuthorizedExploratoryFit':True,
        'trainingStepAttempts':len(starts),'trainingSteps':len(steps),'generationAttempts':len(begun),'generationsWithSavedOutputs':len(generations),
        'trainGroupExposures':exposures,'losses':[s['loss'] for s in steps],'trainingCosts':steps,
        'modelForwardCounts':counts,'checkpoint':checkpoint,'comparisons':comparisons,'costObservations':costs,
        'realizerTrainerImplemented':True,'plannerModelImplemented':False,'realizerTrained':len(steps)==expected_steps and checkpoint is not None,
        'formalEvaluationAllowed':False,'semanticQualityApproved':False,'fullRequest500msStatus':'unverified',
        'sourceIndependence':'unverified','sourceRisks':['realizer-new-05','realizer-new-06'],'newIndependentTrainingGroups':0,
        'semanticReviewStatus':'assistant_output_review_separate_not_formal_approval',
        'supervisor':record['supervisor'],'preparationStages':record['stages'],
        'planSha256':sha256_file(pp),'recordSha256':sha256_file(rp),'journalSha256':sha256_file(journal) if journal.exists() else None}
    if profile['baseline']:
        summary.update(stage='L3-18 expanded draft data versus frozen first-fit adapter',baselineAdapter=profile['baseline'],
                       trainingExamples=len(train),developmentExamples=len(dev),newSourceCandidateGroups=18,newExamples=36)
        for p in comparisons:p['cohort']='new_training' if p['annotationId'].startswith('expanded-') and p['role']=='train_candidate' else 'new_development' if p['annotationId'].startswith('expanded-') else 'old_training' if p['role']=='train_candidate' else 'old_development_regression'
    if run_id==BUDGET_RUN:
        import realizer_expansion as expansion
        parent=observed_fit(expansion.RUN)
        summary.update(date='2026-11-05',stage='L3-20 fixed 80 versus 320 training-step budget comparison',
            newSourceCandidateGroups=0,newExamples=0,retainedExpansionExamples=36,
            trainingBudgetComparison=budget_controls(summary,parent))
    return summary


def budget_controls(current,parent):
    """Report control checks without turning numerical fit into a quality judge."""
    previous={p['annotationId']:p['after_fit'] for p in parent['comparisons']}
    saved=[p for p in current['comparisons'] if p['before_fit'] is not None]
    for p in saved:
        before=p['before_fit'];old_prediction=previous[p['annotationId']]
        if any(before[key]!=old_prediction[key] for key in ('inputTokenIds','tokenIds','raw')):
            raise ValueError('80-step baseline no longer reproduces parent model')
    compared=current['losses'][:80];differences=[abs(a-b) for a,b in zip(compared,parent['losses'])]
    return {'baselineSteps':80,'newSteps':fit_profile(BUDGET_RUN)['config']['steps'],
        'baselineRecordSha256':parent['recordSha256'],'baselineOutputsReproduced':len(saved),
        'first80LossMaxAbsoluteDifference':max(differences,default=None),
        'first80LossesExact':compared==parent['losses'],'preRegisteredLossTolerance':1e-6,
        'first80WithinTolerance':len(differences)==80 and max(differences)<=1e-6}


def budget_document(summary,verdicts):
    import html
    e=lambda value:html.escape(str(value))
    labels={'old_training':'原训练6题','new_training':'新增训练24题',
            'old_development_regression':'原开发回归6题','new_development':'新开发12题／6组'}
    document='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>L3-20 80步与320步训练对照</title><style>body{margin:0;background:#f4f6f8;color:#20313e;font:16px/1.7 system-ui}main{max-width:1100px;margin:auto;padding:24px}section{background:#fff;padding:22px;border-radius:12px;margin:20px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}.warn{color:#a7352e}table{width:100%;border-collapse:collapse}td,th{padding:10px;text-align:left;border-bottom:1px solid #ddd}article{border-top:1px solid #ddd;padding-top:12px}</style><main><p>D / L3-20 · 2026-11-05</p><h1>同一批数据，多训练一些有没有帮助？</h1>'''
    document+=f'<section><h2>这轮只改变训练步数</h2><p>同一77M底座、同一适配层结构、30条训练与18条开发、相同初始化与其他参数。已有80步模型作基线；新模型从原底座重新训练320步，没有接着旧模型续训，开发题不参与梯度。实际完成{summary["trainingSteps"]}/320步，保存{summary["generationsWithSavedOutputs"]}/96条首次输出，无重试或择优。</p><p class="warn">所有标签仍为助手核对草稿，人审0，来源独立性未核实。下列合理／错误／含糊均为助手预检，不是正式质量验收。只测试给定动作计划的表达；开放规划、反应、共同结果、完整500ms、浏览器与生产仍未通过。</p><p>整批进程{summary["supervisor"]["wallMs"]/1000:.2f}秒，峰值RSS {summary["supervisor"]["observedPeakResidentMiB"]:.2f}MiB。这包括训练、准备及96次生成，不是单次游戏等待。</p><table><thead><tr><th>用途</th><th>80步：合理／错误／含糊</th><th>320步：合理／错误／含糊</th></tr></thead><tbody>'
    for cohort,label in labels.items():
        cells=[]
        for phase in ('before_fit','after_fit'):
            counts=summary['cohortQualityCounts'][phase][cohort]
            cells.append('／'.join(str(counts[k]) for k in ('candidate_correct','fail','uncertain')))
        document+=f'<tr><td>{label}</td><td>{cells[0]}</td><td>{cells[1]}</td></tr>'
    groups=summary['newDevelopmentGroupsAllVariantsCorrect']
    document+=f'</tbody></table><p>新开发6组中，两变体都合理的组数：{groups["before_fit"]} → {groups["after_fit"]}。相关变体不当作独立来源，已曝光开发题也不转封存。</p><details><summary>控制检查与局部完整生成耗时</summary><pre>{e(json.dumps({"controls":summary["trainingBudgetComparison"],"cost":summary["costObservations"]},ensure_ascii=False,indent=2))}</pre><p>局部计时包含完整分词、生成及原文落盘；尾部计时事件与批末汇总在进程总时间。每题每模型仅一次，质量不同时不能据此签提速或完整500ms。</p></details></section>'
    for item in summary['comparisons']:
        document+=f'<section><h2>{e(item["annotationId"])} · {labels[item["cohort"]]}</h2><p>参考草稿：{e(item["referenceDraft"])}</p>'
        for phase,label in (('before_fit','80步模型'),('after_fit','320步模型')):
            prediction=item[phase]
            if prediction is None:
                document+=f'<p>{label}：未保存输出，不补写或重采样。</p>';continue
            decision=verdicts[(item['annotationId'],phase)]
            document+=f'<article><h3>{label} · {e(decision["verdict"])}</h3><p>{e(prediction["raw"])}</p><p>助手核对：{e(decision["reason"])}</p><p>{prediction["elapsedIncludingOutputJournalMs"]:.2f}ms · {e(prediction["stopStatus"])} · 顶层前向{prediction["modelTopForwardCalls"]}次</p></article>'
        document+='</section>'
    document+=f'<section><h2>全部证据</h2><p><a href="l3-20-realizer-budget320-summary.json">完整汇总与所有输入/token/逐步损失</a> · <a href="m01-fitting/{BUDGET_RUN}.authorization.json">运行授权记录</a> · <a href="m01-fitting/{BUDGET_RUN}.plan.json">冻结计划</a> · <a href="m01-fitting/{BUDGET_RUN}.record.json">原始记录</a> · <a href="m01-fitting/{BUDGET_RUN}.record.journal.jsonl">全部事件</a> · <a href="m01-fitting/{BUDGET_RUN}.output-review.json">助手逐项核对</a> · <a href="l3-18-realizer-expanded.html">80步原始结果</a></p></section></main></html>'
    return document


def fit_materials(write=False,run_id=FIT_RUN):
    import html
    profile=fit_profile(run_id);e=lambda v:html.escape(str(v));summary=observed_fit(run_id)
    review_path=ART/'m01-fitting'/f'{run_id}.output-review.json'
    review=run.read_json(review_path)
    if (review.get('schema')!='jity-d-realizer-assistant-output-review-v1' or review.get('recordSha256')!=summary['recordSha256']
            or review.get('reviewer')!='assistant' or review.get('formalEvaluationAllowed') is not False):raise ValueError('output review identity/scope mismatch')
    expected={(p['annotationId'],phase):p[phase] for p in summary['comparisons'] for phase in ('before_fit','after_fit') if p[phase] is not None}
    verdicts={}
    for row in review.get('decisions',[]):
        key=(row['annotationId'],row['phase']);p=expected.get(key)
        if key in verdicts or p is None or row['rawOutputSha256']!=digest(p['raw']) or row['verdict'] not in ('candidate_correct','fail','uncertain') or not row['reason'].strip():raise ValueError('output review missing/changed/duplicate prediction')
        verdicts[key]=row
    if set(verdicts)!=set(expected):raise ValueError('not all saved outputs reviewed')
    summary['assistantOutputReview']=review;summary['assistantOutputReviewSha256']=sha256_file(review_path)
    summary['assistantQualityCounts']={phase:{role:{v:sum(verdicts[(p['annotationId'],phase)]['verdict']==v for p in summary['comparisons'] if p['role']==role and p[phase] is not None)
        for v in ('candidate_correct','fail','uncertain')} for role in ('train_candidate','development_candidate')} for phase in ('before_fit','after_fit')}
    if profile['baseline']:
        summary['cohortQualityCounts']={phase:{cohort:{v:sum(verdicts[(p['annotationId'],phase)]['verdict']==v for p in summary['comparisons'] if p['cohort']==cohort) for v in ('candidate_correct','fail','uncertain')} for cohort in ('old_training','new_training','old_development_regression','new_development')} for phase in ('before_fit','after_fit')}
        new_dev=[p for p in summary['comparisons'] if p['cohort']=='new_development']
        summary['newDevelopmentGroupsAllVariantsCorrect']={phase:sum(all(verdicts[(p['annotationId'],phase)]['verdict']=='candidate_correct' for p in new_dev if p['sourceGroup']==g) for g in sorted({p['sourceGroup'] for p in new_dev})) for phase in ('before_fit','after_fit')}
    if run_id==BUDGET_RUN:
        document=budget_document(summary,verdicts)
    else:
        document='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>L3-17 首批真实短表达训练</title><style>body{margin:0;background:#f4f6f8;color:#20313e;font:16px/1.7 system-ui}main{max-width:1100px;margin:auto;padding:24px}section{background:#fff;padding:22px;border-radius:12px;margin:20px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}.warn{color:#a7352e}table{width:100%;border-collapse:collapse}td,th{padding:10px;text-align:left;border-bottom:1px solid #ddd}</style><main><p>D / L3-17 · 2026-11-04</p><h1>首批真实短表达训练：全部前后输出</h1>'''
        document+=f'<section><h2>实际做了什么</h2><p>按用户“可以开始吧”授权，以修订2的6条助手核对草稿训练、6条作开发检查。原77M底座冻结，只训练172,032个适配参数；实际完成{summary["trainingSteps"]}/80步，保存{summary["generationsWithSavedOutputs"]}/24次前后首次生成。状态：{e(summary["runStatus"])}。</p><p class="warn">标签仍为助手草稿，人工已审0；以下语义意见为助手预检。每侧仅6题，05/06同题型来源风险保留，不签独立泛化、开放规划或完整500ms。训练后能写句子也不等于能自主选择行动。</p><p>进程总耗时{summary["supervisor"]["wallMs"]/1000:.2f}秒，RSS{summary["supervisor"]["observedPeakResidentMiB"]:.2f}MiB；这是整批训练/准备/生成的成本，不是单次游戏响应时间。</p><details><summary>两阶段质量观察与完整局部耗时</summary><pre>{e(json.dumps({"assistant":summary["assistantQualityCounts"],"cost":summary["costObservations"]},ensure_ascii=False,indent=2))}</pre></details></section>'
        for item in summary['comparisons']:
            document+=f'<section><h2>{e(item["annotationId"])} · {e(item["role"])} · {e(item["coverage"])}</h2><p>参考草稿：{e(item["referenceDraft"])}</p>'
            for phase,label in (('before_fit','训练前'),('after_fit','训练后')):
                p=item[phase]
                if p is None:document+=f'<p>{label}：没有已保存输出，未补写或重采样。</p>';continue
                v=verdicts[(item['annotationId'],phase)]
                document+=f'<h3>{label} · {e(v["verdict"])}</h3><p>{e(p["raw"])}</p><p>助手核对：{e(v["reason"])}</p><p>{p["elapsedIncludingOutputJournalMs"]:.2f}ms · {e(p["stopStatus"])} · 顶层前向{p["modelTopForwardCalls"]}次</p><details><summary>完整实际输入与原始token/计时</summary><pre>{e(json.dumps(p,ensure_ascii=False,indent=2))}</pre></details>'
            document+='</section>'
        document+=f'<section><details><summary>原始汇总、每步损失与运行身份</summary><pre>{e(json.dumps(summary,ensure_ascii=False,indent=2))}</pre></details><p><a href="l3-17-realizer-fit-summary.json">机器汇总</a> · <a href="m01-fitting/{FIT_RUN}.authorization.json">用户运行授权记录</a> · <a href="m01-fitting/{FIT_RUN}.plan.json">冻结计划</a> · <a href="m01-fitting/{FIT_RUN}.record.json">原始记录</a> · <a href="m01-fitting/{FIT_RUN}.record.journal.jsonl">全部事件</a> · <a href="m01-fitting/{FIT_RUN}.output-review.json">助手逐项输出核对</a> · <a href="l3-16-label-audit.html">原数据核对</a></p></section></main></html>'
        if profile['baseline']:
            document=document.replace('L3-17','L3-18').replace('首批真实短表达训练','扩充样本训练对照').replace(FIT_RUN,run_id).replace('l3-17-realizer-fit',profile['page'])
            document=document.replace('按用户“可以开始吧”授权，以修订2的6条助手核对草稿训练、6条作开发检查。','按用户“继续”授权，新增18组36条相关变体。30条训练、12条新开发、6条旧开发回归；旧开发不进训练。前阶段为上批冻结适配层，后阶段为从相同原底座重新初始化、训练80步的新适配层。')
            document=document.replace('/24次前后首次生成','/96次两臂首次生成').replace('每侧仅6题','相关变体按组不跨边，来源未核')
            document=document.replace('训练前 ·','旧模型 ·').replace('训练后 ·','扩充训练模型 ·')
            document=document.replace('</h1>','</h1><section><h2>新旧开发分开观察</h2><pre>'+e(json.dumps({'cohorts':summary['cohortQualityCounts'],'newGroupsBothCorrect':summary['newDevelopmentGroupsAllVariantsCorrect']},ensure_ascii=False,indent=2))+'</pre><p>新开发12条属于6组，两个变体都对才计该组一致；这些仍是助手草稿预检，不签独立泛化或500ms。</p></section>',1)
    files={ART/(profile['page']+'-summary.json'):(json.dumps(summary,ensure_ascii=False,indent=2)+'\n').encode(),ART/(profile['page']+'.html'):document.encode()}
    for path,raw in files.items():
        if path.exists() and path.read_bytes()!=raw:raise ValueError('preserve original fit report: '+str(path))
        if not write and not path.exists():raise ValueError('fit report missing')
    if write:
        for path,raw in files.items():
            if not path.exists():
                with path.open('xb') as stream:stream.write(raw)
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--worker',type=Path);p.add_argument('--numeric-check',action='store_true');p.add_argument('--check-materials',action='store_true');p.add_argument('--check-smoke',action='store_true');p.add_argument('--check-audit',action='store_true');p.add_argument('--check-fit',action='store_true');p.add_argument('--check-expanded',action='store_true');p.add_argument('--check-budget',action='store_true');a=p.parse_args()
    if a.check_budget:
        s=fit_materials(run_id=BUDGET_RUN);print(json.dumps({'trainingSteps':s['trainingSteps'],'generationAttempts':s['generationAttempts'],'formalEvaluationAllowed':False}));raise SystemExit(0)
    if a.check_expanded:
        import realizer_expansion as expansion
        expansion.materials();s=fit_materials(run_id=expansion.RUN);print(json.dumps({'trainingSteps':s['trainingSteps'],'generationAttempts':s['generationAttempts'],'formalEvaluationAllowed':False}));raise SystemExit(0)
    if a.check_fit:
        s=fit_materials();print(json.dumps({'trainingSteps':s['trainingSteps'],'generationAttempts':s['generationAttempts'],'formalEvaluationAllowed':False}));raise SystemExit(0)
    if a.check_audit:
        s=label_audit_materials();print(json.dumps({'checkedAnnotations':s['checkedAnnotations'],'correctedSourceInputs':1,'businessTrainingSteps':0}));raise SystemExit(0)
    if a.check_smoke:
        s=smoke_materials();print(json.dumps({'batchId':s['batchId'],'businessTrainingSteps':0,'syntheticOptimizerSteps':s['realModelSyntheticCheck']['syntheticOptimizerSteps']}));raise SystemExit(0)
    if a.check_materials:
        s=prepare_materials();print(json.dumps({'batchId':s['batchId'],'trainingSteps':0,'businessInferenceCalls':0,'formalEvaluationAllowed':False}));raise SystemExit(0)
    if a.numeric_check:
        import torch
        torch.set_num_threads(1);print(json.dumps(synthetic_gradient_check(torch)));raise SystemExit(0)
    if a.worker:
        plan=run.read_json(a.worker)
        raise SystemExit(training_worker(a.worker) if plan['schema']=='jity-d-realizer-training-plan-v1' else inspection_worker(a.worker))
    p.error('use experiment.py for current commands')
