"""Offline one-step expression projection and frozen-model diagnostic.

Only an existing plan is partitioned; no action, role or text is synthesized by
the program. Inference, bounded supervision and journals reuse the D helpers.
"""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import statistics
import subprocess
import time
import plan_training as t
import realizer_expansion as x

ROOT=t.ROOT;ART=t.ART;RUN='m02-realizer-steps-20261104-r1';ARMS=('whole','steps')
PROTOCOL=ROOT/'design/world-engine-reports/components-logic/realizer-step-protocol.md'
CONFIG={**t.CONFIG,'steps':0,'attemptsPerCase':3,'trainingSteps':0}
CODE=tuple(dict.fromkeys((*t.CODE,'realizer_expansion.py','realizer_steps.py')))


def rows():
    return [r for r in (json.loads(line) for line in (x.DATA/'candidates.jsonl').read_text().splitlines()) if r['role']=='development_candidate']


def project(row,arm):
    t.contract.validate_candidate(row['sourceCase'],row['planDraft'])
    if arm not in ARMS or row['planDraft']['kind']!='act':raise ValueError('explicit act plan and known expression arm required')
    if arm=='whole':return [copy.deepcopy(row)]
    result=[]
    for i,step in enumerate(row['planDraft']['steps']):
        fragment=copy.deepcopy(row);fragment['annotationId']=row['annotationId']+f'.step-{i+1}'
        fragment['planDraft']['steps']=[copy.deepcopy(step)];fragment['planSha256']=t.digest(fragment['planDraft'])
        t.contract.validate_candidate(fragment['sourceCase'],fragment['planDraft']);result.append(fragment)
    if [p['planDraft']['steps'][0] for p in result]!=row['planDraft']['steps']:raise ValueError('step coverage/order lost')
    return result


def assemble(parts):
    if not parts or any(p['partIndex']!=i+1 or not isinstance(p['raw'],str) for i,p in enumerate(parts)):raise ValueError('incomplete/out-of-order expression parts')
    return '\n'.join(p['raw'] for p in parts)


def identity():
    _,record=t.old.paths(x.RUN);checkpoint=t.run.read_json(record)['attempts'][0]['checkpoint']
    return {'checkpoint':checkpoint,'sourceRecordSha256':t.sha256_file(record)}


def prepare(run_id):
    if run_id!=RUN:raise ValueError('this diagnostic is registered under its own run id')
    pp,rp=t.old.paths(run_id)
    if pp.exists() or rp.exists():raise FileExistsError('preserve prior plan/record')
    x.materials();data=rows()
    if len(data)!=18:raise ValueError('expected all eighteen exposed development examples')
    plan={'schema':'jity-d-realizer-step-plan-v1','runId':run_id,'preparedAt':t.timestamp(),
        'sourceHead':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'purpose':'frozen_realizer_whole_versus_complete_ordered_single_step_calls',
        'userAuthorization':{'instruction':'继续','scope':'one_frozen_model_diagnostic_no_training_no_formal_claims'},
        'config':CONFIG,'cases':[{'caseId':r['annotationId']} for r in data],'arms':list(ARMS),
        'dataSha256':t.digest(data),'sourceManifestSha256':t.sha256_file(x.DATA/'source-manifest.json'),
        'code':{str((t.BASE/n).relative_to(ROOT)):t.sha256_file(t.BASE/n) for n in CODE},
        'protocolSha256':t.sha256_file(PROTOCOL),'model':t.observe_m02(ROOT),'environment':t.observe_environment(ROOT),
        'adapter':identity(),'trainingSteps':0,'formalEvaluationAllowed':False,'fullRequestMeasured':False}
    t.exclusive(pp,plan);return pp


def verify(plan):
    data=rows()
    if (plan['runId']!=RUN or plan['config']!=CONFIG or plan['arms']!=list(ARMS) or plan['trainingSteps']!=0
            or plan['formalEvaluationAllowed'] is not False or plan['purpose']!='frozen_realizer_whole_versus_complete_ordered_single_step_calls'
            or plan['userAuthorization']!={'instruction':'继续','scope':'one_frozen_model_diagnostic_no_training_no_formal_claims'}):raise ValueError('step diagnostic scope drift')
    if (plan['dataSha256']!=t.digest(data) or plan['cases']!=[{'caseId':r['annotationId']} for r in data]
            or plan['sourceManifestSha256']!=t.sha256_file(x.DATA/'source-manifest.json')):raise ValueError('step diagnostic data drift')
    if plan['protocolSha256']!=t.sha256_file(PROTOCOL):raise ValueError('step protocol drift')
    for name,h in plan['code'].items():
        if t.sha256_file(ROOT/name)!=h:raise ValueError('step executed code drift')
    if (plan['model']!=t.observe_m02(ROOT) or plan['environment']!=t.observe_environment(ROOT)
            or plan['adapter']!=identity() or t.sha256_file(ROOT/plan['adapter']['checkpoint']['path'])!=plan['adapter']['checkpoint']['sha256']):raise ValueError('step model/adapter drift')


def worker(path):
    plan=t.run.read_json(path);_,out=t.old.paths(plan['runId']);slots=t.run.planned_slots(plan,ARMS)
    report={'schema':'jity-d-realizer-step-record-v1','runId':RUN,'planSha256':t.sha256_file(path),'status':'running',
        'stages':[],'attempts':[],'attemptSlots':slots,'activeAttempt':None,'forwardAttempts':[],
        'trainingSteps':0,'formalEvaluationAllowed':False,'fullRequestMeasured':False}
    t.exclusive(out,report);stage=lambda n,f:t.run.record_stage(report,out,n,f)
    try:
        stage('verify',lambda:verify(plan))
        import torch
        from transformers import T5ForConditionalGeneration,T5Tokenizer
        torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.manual_seed(CONFIG['seed'])
        directory=ROOT/plan['model']['directory']
        tokenizer=stage('tokenizer',lambda:T5Tokenizer.from_pretrained(directory,local_files_only=True,extra_ids=0,legacy=True))
        model=stage('source_model',lambda:T5ForConditionalGeneration.from_pretrained(directory,local_files_only=True,weights_only=True).eval())
        source_hash=t.old.tensor_hash(model.state_dict());t.install_lora(torch,model,CONFIG['rank'],CONFIG['alpha'])
        checkpoint_identity=plan['adapter']['checkpoint']
        stage('frozen_adapter',lambda:t.restore_adapter(model,torch.load(ROOT/checkpoint_identity['path'],map_location='cpu',weights_only=True)))
        model.eval()
        if t.old.tensor_hash(t.adapter_state(model))!=checkpoint_identity['tensorSha256']:raise ValueError('frozen tensor mismatch')
        lookup={r['annotationId']:r for r in rows()};encoder_count=[0]
        encoder_hook=model.get_encoder().register_forward_pre_hook(lambda *_:encoder_count.__setitem__(0,encoder_count[0]+1))
        with t.run.AppendJournal(out.with_suffix('.journal.jsonl'),report['planSha256']) as journal:
            journal.append('begin',{'runId':RUN,'slots':slots})
            for slot in slots:
                a={**slot,'status':'started','startedMonotonicNs':time.monotonic_ns(),'checkpoints':[]}
                report['activeAttempt']=a;journal.append('attempt_start',a);start_encoder=encoder_count[0]
                def checkpoint(name,payload):
                    value={k:a[k] for k in ('arm','caseId','repeat')};value.update(name=name,payload=payload)
                    journal.append('attempt_checkpoint',value);a['checkpoints'].append(copy.deepcopy(value))
                start=time.perf_counter();row=lookup[a['caseId']];projections=project(row,a['arm'])
                a['projectionMs']=(time.perf_counter()-start)*1000
                a['parts']=[]
                for index,p in enumerate(projections,1):
                    prediction=t.generate_expressions(torch,model,tokenizer,[p],a['arm'],checkpoint,CONFIG)[0]
                    prediction.update(partIndex=index,planSha256=p['planSha256'],stepSha256s=[t.digest(s) for s in p['planDraft']['steps']])
                    a['parts'].append(prediction)
                start=time.perf_counter();a['combinedRaw']=assemble(a['parts']);a['assemblyMs']=(time.perf_counter()-start)*1000
                a['outputComplete']=all(p['eos'] for p in a['parts']);a['encoderForwardCalls']=encoder_count[0]-start_encoder
                a['modelTopForwardCalls']=sum(p['modelTopForwardCalls'] for p in a['parts'])
                checkpoint('ordered_expression_result',{'combinedRaw':a['combinedRaw'],'partPlanSha256s':[p['planSha256'] for p in a['parts']],
                    'originalPlanSha256':row['planSha256'],'outputComplete':a['outputComplete']})
                a['status']='complete';a['settledAt']=t.timestamp()
                start=time.perf_counter();journal.append('attempt_result',a);result_ms=(time.perf_counter()-start)*1000
                timing={k:a[k] for k in ('arm','caseId','repeat')};timing.update(resultJournalMs=result_ms,snapshotEndMs=0.,elapsedThroughResultMs=(time.monotonic_ns()-a['startedMonotonicNs'])/1e6)
                start=time.perf_counter();journal.append('attempt_settled',timing);a.update(timing)
                a['telemetryJournalMs']=(time.perf_counter()-start)*1000;a['elapsedIncludingTelemetryMs']=(time.monotonic_ns()-a['startedMonotonicNs'])/1e6
                report['attempts'].append(a);report['activeAttempt']=None
        encoder_hook.remove()
        if t.old.tensor_hash(t.base_state(model))!=source_hash or t.old.tensor_hash(t.adapter_state(model))!=checkpoint_identity['tensorSha256']:raise ValueError('inference modified frozen weights')
        report.update(status='diagnostic_completed',sourceWeightsUnchanged=True,adapterUnchanged=True,
                      sourceFilesUnchanged=t.observe_m02(ROOT)==plan['model'],encoderForwardCalls=encoder_count[0],unexecutedAttempts=0)
    except Exception as error:report.update(status='failed',error={'type':type(error).__name__,'message':str(error)})
    finally:t.save(out,report)
    return 0 if report['status']=='diagnostic_completed' else 1


def execute(path):return t.run.execute_plan(path,paths=t.old.paths,verify=verify,worker_script=Path(__file__),settle_stages=t.old.settle_stages,arms=ARMS)


def observed():
    pp,rp=t.old.paths(RUN);plan=t.run.read_json(pp);record=t.run.read_json(rp);data=rows();lookup={r['annotationId']:r for r in data}
    if record['planSha256']!=t.sha256_file(pp) or plan['config']!=CONFIG or plan['dataSha256']!=t.digest(data):raise ValueError('step recorded identity drift')
    for name,h in plan['code'].items():t.verify_historical_file(ROOT/name,h)
    t.verify_historical_file(PROTOCOL,plan['protocolSha256'])
    replay=copy.deepcopy(record);t.run.reconcile_journal(replay,rp.with_suffix('.journal.jsonl'),'read_only_result_check')
    if replay['attempts']!=record['attempts'] or replay['journalRecovery']!=record['journalRecovery']:raise ValueError('step journal reconstruction differs')
    if (record['status']!='diagnostic_completed' or record['supervisor']['stopReason'] is not None or record['supervisor']['exitCode']!=0
            or not record['sourceWeightsUnchanged'] or not record['adapterUnchanged'] or not record['sourceFilesUnchanged']
            or record['trainingSteps']!=0 or record['formalEvaluationAllowed'] is not False):raise ValueError('step incomplete/invalid scope')
    if record['attemptSlots']!=record['attempts'] or len(record['attempts'])!=108:raise ValueError('step attempts/slots missing')
    parent=t.observed_fit(x.RUN);previous={p['annotationId']:p['after_fit']['raw'] for p in parent['comparisons']}
    calls=0;forwards=0;seen=set()
    for a in record['attempts']:
        key=(a['arm'],a['caseId'],a['repeat'])
        if key in seen or a['repeat'] not in range(3) or a['arm'] not in ARMS:raise ValueError('step duplicate/unregistered attempt')
        seen.add(key);row=lookup[a['caseId']];projections=project(row,a['arm'])
        if len(a['parts'])!=len(projections) or a['combinedRaw']!=assemble(a['parts']):raise ValueError('step result lost/rewrote parts')
        for part,p in zip(a['parts'],projections):
            if (part['inputText']!=t.input_text(p) or part['inputSha256']!=t.digest(t.realizer_payload(p))
                    or part['planSha256']!=p['planSha256'] or part['stepSha256s']!=[t.digest(s) for s in p['planDraft']['steps']]
                    or part['modelTopForwardCalls']!=len(part['tokenIds'])-1):raise ValueError('step projected content/forward mismatch')
        if a['encoderForwardCalls']!=len(projections) or a['modelTopForwardCalls']!=sum(p['modelTopForwardCalls'] for p in a['parts']):raise ValueError('step neural call count differs')
        if a['elapsedIncludingTelemetryMs']<a['elapsedThroughResultMs'] or a['elapsedThroughResultMs']<sum(p['elapsedMs'] for p in a['parts']):raise ValueError('step complete timing excludes work')
        if a['arm']=='whole' and a['combinedRaw']!=previous[a['caseId']]:raise ValueError('whole control no longer reproduces parent model')
        calls+=len(projections);forwards+=a['modelTopForwardCalls']
    controls=[]
    for row in data:
        if len(row['planDraft']['steps'])!=1:continue
        for repeat in range(3):
            pair=[a for a in record['attempts'] if a['caseId']==row['annotationId'] and a['repeat']==repeat]
            if pair[0]['parts'][0]['inputText']!=pair[1]['parts'][0]['inputText'] or pair[0]['combinedRaw']!=pair[1]['combinedRaw']:raise ValueError('single-step control changed')
        controls.append(row['annotationId'])
    if calls!=123 or record['encoderForwardCalls']!=calls:raise ValueError('step expected calls missing')
    return {'schema':'jity-d-realizer-step-summary-v1','date':'2026-11-04','batchId':RUN,
        'stage':'L3-19 frozen realizer whole versus ordered single-step expressions','lastModelRun':RUN,
        'attempts':record['attempts'],'attemptCount':108,'generationCalls':calls,'modelTopForwardCalls':forwards,
        'singleStepControls':controls,'developmentExamples':18,'multiStepExamples':5,'repeatsPerCase':3,
        'trainingSteps':0,'realizerTrainerImplemented':True,'realizerTrained':True,'plannerModelImplemented':False,
        'draftSourceGroups':12,'review':{'reviewedGroups':0,'formalEvaluationAllowed':False},
        'formalEvaluationAllowed':False,'semanticQualityApproved':False,'fullRequest500msStatus':'unverified',
        'supervisor':record['supervisor'],'planSha256':t.sha256_file(pp),'recordSha256':t.sha256_file(rp),
        'journalSha256':t.sha256_file(rp.with_suffix('.journal.jsonl')),'dataSha256':plan['dataSha256']}


def materials(write=False):
    import html
    e=lambda v:html.escape(str(v));summary=observed();review_path=ART/'m01-fitting'/f'{RUN}.output-review.json';review=t.run.read_json(review_path)
    if (review['schema']!='jity-d-realizer-step-assistant-review-v1' or review['recordSha256']!=summary['recordSha256']
            or review['reviewer']!='assistant' or review['formalEvaluationAllowed'] is not False):raise ValueError('step output review scope/identity mismatch')
    verdicts={};lookup={(a['arm'],a['caseId'],a['repeat']):a for a in summary['attempts']}
    for d in review['decisions']:
        key=(d['arm'],d['caseId'],d['repeat']);a=lookup.get(key)
        if (key in verdicts or a is None or d['rawSha256']!=t.digest(a['combinedRaw']) or d['verdict'] not in ('candidate_correct','fail','uncertain')
                or not d['reason'].strip() or (d['verdict']=='candidate_correct' and not a['outputComplete'])):raise ValueError('step output decision drift')
        verdicts[key]=d
    if set(verdicts)!=set(lookup):raise ValueError('not all step attempts reviewed')
    comparisons=[]
    for row in rows():
        item={'annotationId':row['annotationId'],'sourceGroup':row['sourceGroup'],'cohort':'new_development' if row['annotationId'].startswith('expanded-') else 'old_development_regression','stepCount':len(row['planDraft']['steps']),'referenceDraft':row['expressionDraft']}
        for arm in ARMS:
            attempts=[a for a in summary['attempts'] if a['caseId']==row['annotationId'] and a['arm']==arm]
            vs=[verdicts[(arm,a['caseId'],a['repeat'])] for a in attempts]
            verdict='fail' if any(v['verdict']=='fail' for v in vs) else 'uncertain' if any(v['verdict']=='uncertain' for v in vs) else 'candidate_correct'
            item[arm]={'verdict':verdict,'rawByRepeat':[a['combinedRaw'] for a in attempts],
                'partsByRepeat':[[p['raw'] for p in a['parts']] for a in attempts],
                'allThreeOutputsIdentical':len({a['combinedRaw'] for a in attempts})==1,
                'medianMs':statistics.median(a['elapsedIncludingTelemetryMs'] for a in attempts),
                'maxMs':max(a['elapsedIncludingTelemetryMs'] for a in attempts),'reason':vs[0]['reason']}
        comparisons.append(item)
    summary['comparisons']=comparisons;summary['assistantReviewSha256']=t.sha256_file(review_path)
    summary['qualityCounts']={arm:{cohort:{v:sum(p[arm]['verdict']==v for p in comparisons if p['cohort']==cohort) for v in ('candidate_correct','fail','uncertain')} for cohort in ('old_development_regression','new_development')} for arm in ARMS}
    summary['multiStepQuality']={arm:{v:sum(p[arm]['verdict']==v for p in comparisons if p['stepCount']>1) for v in ('candidate_correct','fail','uncertain')} for arm in ARMS}
    doc='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>L3-19 整段与逐步表达对照</title><style>body{margin:0;background:#f4f6f8;color:#20313e;font:16px/1.7 system-ui}main{max-width:1100px;margin:auto;padding:24px}section{background:white;padding:22px;border-radius:12px;margin:20px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}table{border-collapse:collapse;width:100%}td,th{padding:10px;text-align:left;border-bottom:1px solid #ddd}</style><main><h1>整段表达与逐步表达：同一冻结模型对照</h1><section><p>保持上批模型/权重不变，18条已曝光开发题×2方案×3次，108次尝试、123次真实生成。整段方案一次表达全部计划；逐步方案每步由同一模型独立表达，程序只保留原序及原始文字，以换行展示，不补写动作或结果。单步题作为输入/输出完全相同的控制。</p><p>没有新训练或人工标签签字；给定计划表达的局部诊断不代表开放规划、正式泛化或完整500ms。</p></section>'''
    labels={'whole':'整段一次表达','steps':'每步分别表达'};vl={'candidate_correct':'助手预检合理','fail':'有明确错误','uncertain':'含糊，暂不计合理'}
    doc+='<section><h2>同一批题的结果</h2><table><tr><th>范围</th><th>方案</th><th>合理</th><th>错误</th><th>含糊</th></tr>'
    for cohort,label in (('old_development_regression','旧开发6条'),('new_development','新开发12条')):
        for arm in ARMS:
            c=summary['qualityCounts'][arm][cohort];doc+=f'<tr><td>{label}</td><td>{labels[arm]}</td><td>{c["candidate_correct"]}</td><td>{c["fail"]}</td><td>{c["uncertain"]}</td></tr>'
    doc+=f'</table><p>计分按18个题目；3次重复不增加样本量。进程总耗时{summary["supervisor"]["wallMs"]/1000:.2f}秒、RSS{summary["supervisor"]["observedPeakResidentMiB"]:.2f}MiB，不能当单次游戏响应。</p></section>'
    for p in comparisons:
        doc+=f'<section><h2>{e(p["annotationId"])} · {p["stepCount"]}步</h2><p>参考草稿：{e(p["referenceDraft"])}</p>'
        for arm in ARMS:
            a=p[arm];doc+=f'<h3>{labels[arm]} · {vl[a["verdict"]]}</h3><pre>{e(a["rawByRepeat"][0])}</pre><p>{e(a["reason"])}</p><p>完整表达交接耗时中位{a["medianMs"]:.2f}ms，最大{a["maxMs"]:.2f}ms（每题仅3次，非正式性能验收）。</p>'
        doc+='</section>'
    doc+=f'<section><details><summary>全部重复、原输入/token、调用及计时</summary><pre>{e(json.dumps(summary,ensure_ascii=False,indent=2))}</pre></details><p><a href="l3-19-realizer-steps-summary.json">完整汇总</a> · <a href="m01-fitting/{RUN}.plan.json">冻结计划</a> · <a href="m01-fitting/{RUN}.record.json">原记录</a> · <a href="m01-fitting/{RUN}.record.journal.jsonl">全部事件</a> · <a href="m01-fitting/{RUN}.output-review.json">逐项助手预检</a> · <a href="l3-18-realizer-expanded.html">上批对照</a></p></section></main></html>'
    files={ART/'l3-19-realizer-steps-summary.json':(json.dumps(summary,ensure_ascii=False,indent=2)+'\n').encode(),ART/'l3-19-realizer-steps.html':doc.encode()}
    for path,raw in files.items():
        if path.exists() and path.read_bytes()!=raw:raise ValueError('preserve delivered step report')
        if not write and not path.exists():raise ValueError('step report missing')
    if write:
        for path,raw in files.items():
            if not path.exists():path.write_bytes(raw)
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--worker',type=Path);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    if args.worker:raise SystemExit(worker(args.worker))
    if args.check:
        s=materials();print(json.dumps({'attempts':s['attemptCount'],'generationCalls':s['generationCalls'],'trainingSteps':0}));raise SystemExit(0)
    parser.error('use experiment.py steps commands')
