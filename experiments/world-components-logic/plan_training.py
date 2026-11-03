"""D short-realizer training implementation, candidate sources and model inspection.

No draft is used for neural training. Inspection loads M02 without a forward;
numeric gradient checks use a separate tiny synthetic tensor module only.
"""
from __future__ import annotations
import argparse
import copy
import json
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
PROTOCOL=ROOT/'design/world-engine-reports/components-logic/realizer-training-protocol.md'
CODE=('plan_training.py','action_plan.py','experiment.py','m01_probe.py','generate_dev_drafts.py','lab.py','pilot_codec.py','prepare_run_batch.py','run_pilot.py')
CONFIG={'device':'cpu','threads':1,'concurrency':1,'seed':42,'rank':4,'alpha':8,
        'optimizer':'AdamW','learningRate':0.001,'weightDecay':0.01,'maxGradNorm':1.0,
        'steps':80,'batchSize':2,'maxInputTokens':256,'maxTargetTokens':64,
        'maxNewTokens':64,'doSample':False,'numBeams':1,'earlyStopping':False,
        'frozenBackboneEval':True,'processWallSeconds':120,'maxResidentMiB':2048,
        'attemptsPerCase':1,'gradientAccumulation':1,'adapterDropout':0.0}
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


def packet_identity(rows):return digest({'batchId':BATCH,'rows':rows})


def reconcile_reviews(rows,claims=None):
    if claims is None:return {'reviewedGroups':0,'missingReviews':len(rows),'trainingDataReady':False,'formalEvaluationAllowed':False}
    if not isinstance(claims,dict) or set(claims)!={'schema','batchId','packetSha256','reviewer','decisions'}:raise ValueError('new source review packet required')
    if claims['schema']!='jity-d-realizer-training-review-v1' or claims['batchId']!=BATCH or claims['packetSha256']!=packet_identity(rows):raise ValueError('training review batch drift')
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


def input_text(row):return '将动作计划写成一句尝试，不添加成功结果：'+canonical_bytes(realizer_payload(row)).decode()


def reviewed_data(claims):
    rows=candidate_rows();status=reconcile_reviews(rows,claims)
    if not status['trainingDataReady']:raise ValueError('training labels are not fully reviewed')
    train=[r for r in rows if r['role']=='train_candidate'];dev=[r for r in rows if r['role']=='development_candidate']
    if len(train)!=6 or len(dev)!=6 or {r['sourceGroup'] for r in train}&{r['sourceGroup'] for r in dev}:raise ValueError('registered train/development groups drift')
    return train,dev


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


def tokenize_example(tokenizer,row,config=CONFIG):
    # All source names/steps are retained. The target is never placed in input.
    x=tokenizer.encode(input_text(row),add_special_tokens=True,truncation=False)
    y=tokenizer.encode(row['expressionDraft'],add_special_tokens=True,truncation=False)
    if not x or len(x)>config['maxInputTokens'] or not y or len(y)>config['maxTargetTokens']:raise ValueError('complete expression example exceeds registered token limits')
    if y[-1]!=tokenizer.eos_token_id:raise ValueError('target EOS missing')
    return {'inputIds':x,'labels':y,'sourceGroup':row['sourceGroup'],'inputSha256':digest(realizer_payload(row)),'targetSha256':row['expressionSha256']}


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
    model.eval();examples=[tokenize_example(tokenizer,r,config) for r in train_rows]
    if len({e['sourceGroup'] for e in examples})!=len(examples):raise ValueError('training source duplicate')
    params=[p for p in model.parameters() if p.requires_grad]
    if not params:raise ValueError('no learned adapter parameters')
    optimizer=torch.optim.AdamW(params,lr=config['learningRate'],weight_decay=config['weightDecay'])
    generator=torch.Generator().manual_seed(config['seed']);order=torch.randperm(len(examples),generator=generator).tolist();losses=[]
    for step in range(config['steps']):
        batch=[examples[order[(step*config['batchSize']+j)%len(order)]] for j in range(config['batchSize'])]
        checkpoint('training_step_started',{'step':step+1,'sourceGroups':[e['sourceGroup'] for e in batch]})
        optimizer.zero_grad(set_to_none=True);output=model(**collate(torch,batch,tokenizer.pad_token_id));loss=output.loss
        if not torch.isfinite(loss):raise ValueError('nonfinite training loss')
        loss.backward();norm=torch.nn.utils.clip_grad_norm_(params,config['maxGradNorm'])
        if not torch.isfinite(norm):raise ValueError('nonfinite adapter gradient')
        optimizer.step();value=float(loss.detach());losses.append(value)
        checkpoint('training_step_settled',{'step':step+1,'loss':value,'gradientNorm':float(norm)})
    return losses


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


def inspection_plan(run_id):
    pp,rp=old.paths(run_id)
    if pp.exists() or rp.exists():raise FileExistsError('use new inspection id')
    model=observe_m02(ROOT);environment=observe_environment(ROOT)
    if not model['allSixFilesFullyRehashedAndVerified'] or not environment['registeredVersionsMatch']:raise ValueError('M02/environment verification failed')
    plan={'schema':'jity-d-realizer-inspection-plan-v1','runId':run_id,'sourceHead':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'preparedAt':timestamp(),'purpose':'model_layout_and_synthetic_gradient_only_no_project_forward',
        'config':CONFIG.copy(),'cases':[{'caseId':'m02-adapter-layout-only'}],'arms':['inspect'],
        'code':{str((BASE/n).relative_to(ROOT)):sha256_file(BASE/n) for n in CODE},
        'protocolSha256':sha256_file(PROTOCOL),'model':model,'environment':environment,
        'candidatePacketSha256':packet_identity(candidate_rows()),'trainingLabelsReviewed':0,
        'formalEvaluationAllowed':False,'businessTrainingSteps':0,'businessInferenceCalls':0,
        'authorization':'用户继续工作；D独立CPU单线程模型装配与合成张量工程检查，不用业务草稿'}
    exclusive(pp,plan);return pp


def verify_inspection(plan):
    if plan['config']!=CONFIG or plan['purpose']!='model_layout_and_synthetic_gradient_only_no_project_forward' or plan['formalEvaluationAllowed'] is not False:raise ValueError('inspection scope drift')
    if plan['protocolSha256']!=sha256_file(PROTOCOL):raise ValueError('inspection protocol drift')
    for name,h in plan['code'].items():
        if sha256_file(ROOT/name)!=h:raise ValueError('executed source drift: '+name)
    if plan['model']!=observe_m02(ROOT) or plan['environment']!=observe_environment(ROOT):raise ValueError('inspection model/environment drift')
    if plan['candidatePacketSha256']!=packet_identity(candidate_rows()):raise ValueError('source candidates drift')


def inspection_worker(path):
    plan=run.read_json(path);_,out=old.paths(plan['runId']);slots=run.planned_slots(plan,('inspect',))
    report={'schema':'jity-d-realizer-inspection-record-v1','runId':plan['runId'],'planSha256':sha256_file(path),
        'status':'running','stages':[],'attempts':[],'attemptSlots':slots,'activeAttempt':None,'forwardAttempts':[],
        'trainingSteps':0,'businessInferenceCalls':0,'formalEvaluationAllowed':False,'fullRequestMeasured':False}
    exclusive(out,report);stage=lambda n,f:run.record_stage(report,out,n,f)
    try:
        stage('verify',lambda:verify_inspection(plan))
        import torch
        from transformers import T5ForConditionalGeneration
        torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.manual_seed(42)
        model=stage('load_m02_no_forward',lambda:T5ForConditionalGeneration.from_pretrained(ROOT/plan['model']['directory'],local_files_only=True,weights_only=True).eval())
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
            topology=install_lora(torch,model,CONFIG['rank'],CONFIG['alpha'])
            trainable=sum(p.numel() for p in model.parameters() if p.requires_grad)
            zeros=all(not torch.count_nonzero(p) for n,p in model.named_parameters() if n.endswith('.lora_B'))
            if trainable!=172032 or not zeros or old.tensor_hash(base_state(model))!=source_hash:raise ValueError('adapter/base layout mismatch')
            a['layout']={'sourceParameters':source_params,'trainableAdapterParameters':trainable,
                         'totalInferenceParameters':sum(p.numel() for p in model.parameters()),'targetModules':topology,
                         'initialOutputMatricesZero':True,'sourceBaseUnchanged':True}
            checkpoint('adapter_layout',a['layout']);a['syntheticCheck']=synthetic_gradient_check(torch);checkpoint('synthetic_numeric_check',a['syntheticCheck'])
            if forward_calls[0]!=0 or old.tensor_hash(base_state(model))!=source_hash:raise ValueError('source model executed or changed during inspection')
            hook.remove();a['projectForwardCalls']=forward_calls[0];a['status']='complete';a['settledAt']=timestamp()
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
    return run.execute_plan(path,paths=old.paths,verify=verify_inspection,worker_script=Path(__file__),settle_stages=old.settle_stages,arms=('inspect',))

def training_plan(run_id,review_path):
    claims=run.read_json(review_path)
    train,dev=reviewed_data(claims)  # Before any artifact/model import or load.
    pp,rp=old.paths(run_id)
    if pp.exists() or rp.exists():raise FileExistsError('use a new training id')
    model=observe_m02(ROOT);environment=observe_environment(ROOT)
    if not model['allSixFilesFullyRehashedAndVerified'] or not environment['registeredVersionsMatch']:raise ValueError('training identity invalid')
    plan={'schema':'jity-d-realizer-training-plan-v1','runId':run_id,'preparedAt':timestamp(),
          'sourceHead':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
          'purpose':'reviewed_candidate_plan_to_text_adapter_fit_not_open_planner',
          'config':CONFIG.copy(),'cases':[{'caseId':'m02-reviewed-realizer-fit'}],'arms':['fit'],
          'code':{str((BASE/n).relative_to(ROOT)):sha256_file(BASE/n) for n in CODE},
          'protocolSha256':sha256_file(PROTOCOL),'model':model,'environment':environment,
          'reviewClaims':claims,'reviewFileSha256':sha256_file(review_path),
          'candidatePacketSha256':packet_identity(candidate_rows()),'trainGroups':[r['sourceGroup'] for r in train],
          'developmentGroups':[r['sourceGroup'] for r in dev],'formalEvaluationAllowed':False,
          'sourceIndependence':'unverified','newIndependentTrainingGroups':0,'fullRequestMeasured':False}
    exclusive(pp,plan);return pp


def verify_training(plan):
    if (plan['purpose']!='reviewed_candidate_plan_to_text_adapter_fit_not_open_planner'
            or plan['config']!=CONFIG or plan['formalEvaluationAllowed'] is not False):raise ValueError('training scope/config drift')
    train,dev=reviewed_data(plan['reviewClaims'])
    if (plan['trainGroups']!=[r['sourceGroup'] for r in train] or plan['developmentGroups']!=[r['sourceGroup'] for r in dev]
            or plan['candidatePacketSha256']!=packet_identity(candidate_rows())):raise ValueError('training source/role drift')
    if plan['protocolSha256']!=sha256_file(PROTOCOL):raise ValueError('training protocol drift')
    for name,h in plan['code'].items():
        if sha256_file(ROOT/name)!=h:raise ValueError('training code drift')
    if plan['model']!=observe_m02(ROOT) or plan['environment']!=observe_environment(ROOT):raise ValueError('training model/environment drift')


def training_worker(path):
    plan=run.read_json(path);_,out=old.paths(plan['runId']);slots=run.planned_slots(plan,('fit',))
    report={'schema':'jity-d-realizer-training-record-v1','runId':plan['runId'],'planSha256':sha256_file(path),
        'status':'running','stages':[],'attempts':[],'attemptSlots':slots,'activeAttempt':None,'forwardAttempts':[],
        'trainingSteps':0,'businessGenerationCalls':0,'formalEvaluationAllowed':False,'semanticQualityApproved':False,'fullRequestMeasured':False}
    exclusive(out,report);stage=lambda n,f:run.record_stage(report,out,n,f)
    try:
        stage('verify_reviewed_training_plan',lambda:verify_training(plan));train,dev=reviewed_data(plan['reviewClaims'])
        import torch
        from transformers import T5ForConditionalGeneration,T5Tokenizer
        from transformers.generation.stopping_criteria import MaxTimeCriteria,StoppingCriteriaList
        torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.manual_seed(CONFIG['seed'])
        directory=ROOT/plan['model']['directory']
        tokenizer=stage('tokenizer',lambda:T5Tokenizer.from_pretrained(directory,local_files_only=True,extra_ids=0,legacy=True))
        model=stage('source_model',lambda:T5ForConditionalGeneration.from_pretrained(directory,local_files_only=True,weights_only=True).eval())
        source_hash=old.tensor_hash(model.state_dict());report['topology']=install_lora(torch,model,CONFIG['rank'],CONFIG['alpha'])
        with run.AppendJournal(out.with_suffix('.journal.jsonl'),report['planSha256']) as journal:
            journal.append('begin',{'runId':plan['runId'],'slots':slots})
            a={**slots[0],'status':'started','startedMonotonicNs':time.monotonic_ns(),'checkpoints':[]};report['activeAttempt']=a;journal.append('attempt_start',a)
            def checkpoint(name,payload):
                row={k:a[k] for k in ('arm','caseId','repeat')};row.update(name=name,payload=payload)
                journal.append('attempt_checkpoint',row);a['checkpoints'].append(copy.deepcopy(row))
                if name=='training_step_settled':report['trainingSteps']=payload['step']
                if name=='generation_started':report['businessGenerationCalls']+=1
            a['losses']=fit_adapter(torch,model,tokenizer,train,CONFIG,checkpoint)
            if old.tensor_hash(base_state(model))!=source_hash:raise ValueError('frozen source weights changed during fitting')
            weights=adapter_state(model);adapter_hash=old.tensor_hash(weights)
            destination=ROOT/'.local/world-components-logic/realizer-adapters'/plan['runId'];destination.mkdir(parents=True,exist_ok=False)
            checkpoint_path=destination/'adapter.pt'
            with checkpoint_path.open('xb') as stream:torch.save(weights,stream)
            with torch.no_grad():
                for p in model.parameters():
                    if p.requires_grad:p.zero_()
            reloaded=torch.load(checkpoint_path,map_location='cpu',weights_only=True);restore_adapter(model,reloaded)
            if old.tensor_hash(adapter_state(model))!=adapter_hash:raise ValueError('adapter checkpoint reload mismatch')
            a['checkpoint']={'path':str(checkpoint_path.relative_to(ROOT)),'sha256':sha256_file(checkpoint_path),'tensorSha256':adapter_hash,'sourceTensorSha256':source_hash}
            checkpoint('adapter_frozen',a['checkpoint']);a['predictions']=[]
            # No labels enter generation; both train and dev first outputs retained.
            for row in train+dev:
                start=time.perf_counter();checkpoint('generation_started',{'annotationId':row['annotationId'],'role':row['role']})
                encoded=tokenize_example(tokenizer,row);ids=torch.tensor([encoded['inputIds']]);count=[0]
                hook=model.register_forward_pre_hook(lambda *_:count.__setitem__(0,count[0]+1))
                try:
                    with torch.inference_mode():output=model.generate(input_ids=ids,attention_mask=torch.ones_like(ids),max_new_tokens=CONFIG['maxNewTokens'],do_sample=False,num_beams=1,
                        stopping_criteria=StoppingCriteriaList([MaxTimeCriteria(max_time=3)]))
                finally:hook.remove()
                tokens=output[0].tolist();text=tokenizer.decode(tokens,skip_special_tokens=True)
                prediction={'annotationId':row['annotationId'],'sourceGroup':row['sourceGroup'],'role':row['role'],
                    'inputSha256':encoded['inputSha256'],'raw':text,'tokenIds':tokens,'modelTopForwardCalls':count[0],
                    'eos':bool(tokens) and tokens[-1]==model.generation_config.eos_token_id,'semanticReview':'pending_not_approved',
                    'scope':'human_provided_plan_expression_only_not_open_planner','elapsedMs':(time.perf_counter()-start)*1000}
                checkpoint('generation_output',prediction)
                prediction['elapsedIncludingOutputJournalMs']=(time.perf_counter()-start)*1000
                checkpoint('generation_timing',{'annotationId':row['annotationId'],'elapsedIncludingOutputJournalMs':prediction['elapsedIncludingOutputJournalMs']})
                a['predictions'].append(prediction)
            if old.tensor_hash(base_state(model))!=source_hash or old.tensor_hash(adapter_state(model))!=adapter_hash:raise ValueError('inference changed frozen model/adapter')
            a['status']='complete';a['settledAt']=timestamp()
            t=time.perf_counter();journal.append('attempt_result',a);result_ms=(time.perf_counter()-t)*1000
            timing={k:a[k] for k in ('arm','caseId','repeat')}
            timing.update(resultJournalMs=result_ms,snapshotEndMs=0.,elapsedThroughResultMs=(time.monotonic_ns()-a['startedMonotonicNs'])/1e6)
            t=time.perf_counter();journal.append('attempt_settled',timing);a.update(timing)
            a['telemetryJournalMs']=(time.perf_counter()-t)*1000;a['elapsedIncludingTelemetryMs']=(time.monotonic_ns()-a['startedMonotonicNs'])/1e6
            report['attempts']=[a];report['activeAttempt']=None
        report['status']='diagnostic_completed';report['sourceWeightsUnchanged']=True;report['unexecutedAttempts']=0
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
    manifest={'schema':'jity-d-realizer-training-source-candidates-v1','batchId':BATCH,'packetSha256':packet_identity(rows),
        'fileSha256':__import__('hashlib').sha256(raw).hexdigest(),'sourceHead':'49189351cf0a04a0cc3fafd15a8eab0248b1a10d',
        'authoringCodeSha256':sha256_file(Path(__file__)),'protocolSha256':sha256_file(PROTOCOL),
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

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--worker',type=Path);p.add_argument('--numeric-check',action='store_true');p.add_argument('--check-materials',action='store_true');a=p.parse_args()
    if a.check_materials:
        s=prepare_materials();print(json.dumps({'batchId':s['batchId'],'trainingSteps':0,'businessInferenceCalls':0,'formalEvaluationAllowed':False}));raise SystemExit(0)
    if a.numeric_check:
        import torch
        torch.set_num_threads(1);print(json.dumps(synthetic_gradient_check(torch)));raise SystemExit(0)
    if a.worker:
        plan=run.read_json(a.worker)
        raise SystemExit(training_worker(a.worker) if plan['purpose']=='reviewed_candidate_plan_to_text_adapter_fit_not_open_planner' else inspection_worker(a.worker))
    p.error('use experiment.py for current commands')
