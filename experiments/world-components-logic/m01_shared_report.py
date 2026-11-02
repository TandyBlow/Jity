"""Evidence-bound comparison report, without loading model/checkpoint weights."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import json
import math
from pathlib import Path
import statistics
import subprocess

from fact_windows import restore
from lab import canonical_bytes,sha256_file
import m01_shared as shared

ROOT=shared.ROOT
ART=ROOT/'artifacts/world-components-logic'
DATA=shared.ART
PREFIX='m01-shared-dev42-20261102-'
EXECUTED_COMMIT='d3b21a53eb901fdfded100ae41a3201d7bbb05b5'


def read_archive(path):return json.loads(gzip.decompress(path.read_bytes()))


def executed_source(name,expected_sha,version):
    """Verify exact historical bytes; never require current code to stay frozen."""
    source=DATA/'code/m01_shared-r2.py' if version=='r2' and name.endswith('/m01_shared.py') else ROOT/name
    if source.exists() and sha256_file(source)==expected_sha:return
    try:
        raw=subprocess.check_output(['git','show',EXECUTED_COMMIT+':'+name],cwd=ROOT,stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as error:
        raise ValueError('historical source unavailable; local Git history must include '+EXECUTED_COMMIT) from error
    if hashlib.sha256(raw).hexdigest()!=expected_sha:raise ValueError('executed code identity mismatch: '+name)


def same(task,label,decoded):
    return decoded['kind']==label if task=='D02' else {x['targetId'] for x in decoded['targets']}==set(label)


def quality(rows):
    result={}
    for task in ('D02','D03'):
        result[task]={}
        for role in ('fit','retained_development'):
            selected=[r for r in rows if r['task']==task and r['role']==role]
            item={'matched':sum(same(task,r['label'],r['decoded']) for r in selected),'groups':len(selected)}
            if task=='D03':
                item.update(requiredTargets=sum(len(r['label']) for r in selected),
                    missedTargets=sum(len(set(r['label'])-{x['targetId'] for x in r['decoded']['targets']}) for r in selected),
                    extraTargets=sum(len({x['targetId'] for x in r['decoded']['targets']}-set(r['label'])) for r in selected))
            result[task][role]=item
    return result


def statistics_by_case(attempts):
    rows=[]
    for arm in ('legacy','shared'):
        for cid in sorted({a['caseId'] for a in attempts}):
            selected=[a for a in attempts if a['arm']==arm and a['caseId']==cid]
            times=sorted(a['elapsedMs'] for a in selected);coverage=selected[0]['coverage']
            covs=[coverage] if arm=='shared' else coverage
            rows.append({'arm':arm,'caseId':cid,'observations':len(selected),'p50Ms':statistics.median(times),
                'p95Ms':times[math.ceil(.95*len(times))-1],'maxMs':max(times),
                'windows':sum(len(c['windows']) for c in covs),
                'maxWindowTokens':max(w['totalTokens'] for c in covs for w in c['windows']),
                'local50ms':'fail' if max(times)>50 else 'unverified_insufficient_observations',
                'predicted':selected[0]['decoded'],'probabilities':selected[0]['probabilities'],
                'headMedianMs':statistics.median(a['headMs'] for a in selected)})
    return rows


def validate_coverage(case,coverage,arm):
    covs=[coverage] if arm=='shared' else coverage
    expected=([case['input']['actorId']] if case['task']=='D02' else case['input']['candidateIds'])
    if arm=='shared':
        if coverage['targets']!=expected:raise ValueError('shared candidate coverage mismatch')
        ids,anchor,pools=shared.pool_indices(case,coverage['factRecords'])
        if coverage['anchorFactIds']!=anchor or coverage['candidateFactIds']!=pools:raise ValueError('identity pools mismatch')
    elif [c['targetId'] for c in covs]!=( [None] if case['task']=='D02' else expected):raise ValueError('legacy roster incomplete')
    for cov in covs:
        if not cov['fullFactsRestored'] or canonical_bytes(restore(cov['factRecords']))!=canonical_bytes(case['input']):raise ValueError('incomplete original facts')
        if shared.digest(cov['factRecords'])!=cov['factSha256']:raise ValueError('fact digest mismatch')
        if [i for w in cov['windows'] for i in w['factIds']]!=list(range(len(cov['factRecords']))):raise ValueError('incomplete encoded facts')
        for w in cov['windows']:
            if not (w['totalTokens']==len(w['inputIds'])==len(w['tokenTypeIds'])<=512):raise ValueError('window token mismatch/overflow')
            if arm=='shared':
                spans=w['factSpans'];cursor=spans[0]['start']
                if [s['factIndex'] for s in spans]!=w['factIds']:raise ValueError('fact span IDs mismatch')
                for s in spans:
                    if s['start']!=cursor or s['end']<=s['start']:raise ValueError('fact span gap/overlap')
                    cursor=s['end']
                if cursor!=len(w['inputIds'])-1 or cursor-spans[0]['start']!=w['payloadTokens']:raise ValueError('payload span mismatch')


def validate_run(plan,record,events,baseline):
    if record['status']!='diagnostic_completed' or record['supervisor']['exitCode']!=0 or record['supervisor']['stopReason'] is not None:
        raise ValueError('incomplete diagnostic')
    if not record['encoderUnchanged'] or record['unexecutedAttempts'] or record.get('windowEventMalformedLines'):raise ValueError('incomplete training/trace')
    if plan['formalEvaluationAllowed'] is not False or plan['round1TrainingQuota'] or plan['newIndependentTrainingGroups']:
        raise ValueError('formal scope incorrectly promoted')
    if plan['retainedDevelopmentPreviouslyObserved'] is not True:raise ValueError('exposed development status missing')
    cases={c['caseId']:c for c in plan['cases']};labels={r['case']['caseId']:r for r in plan['dataset']}
    if len(labels)!=20 or plan['datasetSha256']!=shared.digest(plan['dataset']):raise ValueError('dataset identity mismatch')
    if set(cases)!={k for k,r in labels.items() if r['role']=='retained_development'}:raise ValueError('retained case substitution')
    if plan['datasetSha256']!=plan['baseline']['datasetSha256'] or plan['model']!=plan['baseline']['model']:raise ValueError('baseline dataset/model mismatch')
    if plan['baseline']['trainedHeadSha256']!=baseline['trainedHeadSha256'] or plan['baseline']['checkpoint']!=baseline['checkpoint']:
        raise ValueError('legacy checkpoint identity mismatch')
    expected={(arm,cid,i) for arm in ('legacy','shared') for cid in cases for i in range(5)}
    actual=[(a['arm'],a['caseId'],a['repeat']) for a in record['attempts']]
    if len(actual)!=40 or set(actual)!=expected or len(record['attemptSlots'])!=40:raise ValueError('attempt identity/count mismatch')
    trace=[]
    for row in record['featureCoverage']:
        case=labels[row['caseId']]['case'];cov=row['coverage'];validate_coverage(case,cov,'shared')
        for i,w in enumerate(cov['windows']):trace.append(('feature_fit','shared',row['caseId'],None,None,i,w))
    if len(record['featureCoverage'])!=20 or len({r['caseId'] for r in record['featureCoverage']})!=20:raise ValueError('fitting feature coverage mismatch')
    fitted={r['caseId']:r for r in record['fitAndDevelopmentPredictions']}
    if set(fitted)!=set(labels):raise ValueError('fitting prediction coverage mismatch')
    for cid,r in fitted.items():
        if r['label']!=labels[cid]['label'] or r['role']!=labels[cid]['role'] or r['task']!=labels[cid]['case']['task']:raise ValueError('fitting label/split mismatch')
    legacy_predictions={r['caseId']:r for r in baseline['fitAndDevelopmentPredictions']}
    for a in record['attempts']:
        if a['status']!='complete' or a['featureCacheUsed'] is not False or a['fullRequestMeasured'] is not False:raise ValueError('incomplete/cached inference')
        case=cases[a['caseId']]
        if a['inputSha256']!=shared.digest(case['input']):raise ValueError('attempt input mismatch')
        validate_coverage(case,a['coverage'],a['arm'])
        reference=fitted[a['caseId']] if a['arm']=='shared' else legacy_predictions[a['caseId']]
        if a['decoded']!=reference['decoded'] or a['probabilities']!=reference['probabilities']:raise ValueError('fixed checkpoint prediction changed')
        covs=[a['coverage']] if a['arm']=='shared' else a['coverage']
        for cov in covs:
            for i,w in enumerate(cov['windows']):trace.append(('inference',a['arm'],a['caseId'],a['repeat'],None if a['arm']=='shared' else cov['targetId'],i,w))
    starts={e['eventId']:e for e in events if e['status']=='running'}
    ends={e['eventId']:e for e in events if e['status']!='running'}
    if len(events)!=2*len(trace) or set(starts)!=set(range(len(trace))) or set(ends)!=set(starts):raise ValueError('unpaired/duplicate forward events')
    for index,(phase,arm,cid,repeat,target,wi,w) in enumerate(trace):
        for event in (starts[index],ends[index]):
            if (event['phase'],event['arm'],event['caseId'],event.get('repeat'),event['targetId'],event['windowIndex'])!=(phase,arm,cid,repeat,target,wi):raise ValueError('forward scope mismatch')
            for key in ('inputIds','tokenTypeIds','factIds','payloadTokens','totalTokens'):
                if event[key]!=w[key]:raise ValueError('forward payload mismatch')
            if arm=='shared' and event['factSpans']!=w['factSpans']:raise ValueError('forward spans mismatch')
        if ends[index]['status']!='complete':raise ValueError('failed forward included as success')
    return len(trace)


def build():
    baseline=read_archive(shared.OLD_RECORD);old_plan=json.loads(shared.OLD_PLAN.read_bytes())
    runs=[];archives=[];details={}
    for version in ('r2','r3'):
        run_id=PREFIX+version;pp=DATA/(run_id+'.plan.json');rp=DATA/(run_id+'.record.json.gz');ep=DATA/(run_id+'.record.windows.jsonl.gz')
        plan=json.loads(pp.read_bytes());record=read_archive(rp);event_raw=gzip.decompress(ep.read_bytes())
        events=[json.loads(line) for line in event_raw.splitlines() if line.strip()]
        if record['planSha256']!=sha256_file(pp) or record['windowEventsSha256']!=hashlib.sha256(event_raw).hexdigest():raise ValueError('plan/record/events identity mismatch')
        if plan['baseline']['planSha256']!=sha256_file(shared.OLD_PLAN) or plan['baseline']['recordSha256']!=sha256_file(shared.OLD_RECORD):raise ValueError('original baseline evidence changed')
        if plan['dataset']!=old_plan['dataset']:raise ValueError('original split/labels changed')
        for name,h in plan['code'].items():
            executed_source(name,h,version)
        protocol=ROOT/plan.get('protocolPath','design/world-engine-reports/components-logic/m01-shared-probe.md')
        if sha256_file(protocol)!=plan['protocolSha256']:raise ValueError('protocol changed')
        if version=='r3' and sha256_file(protocol.with_name('m01-shared-probe.md'))!=plan['inheritedProtocolSha256']:raise ValueError('inherited protocol changed')
        forwards=validate_run(plan,record,events,baseline)
        for path in (rp,ep):
            raw=gzip.decompress(path.read_bytes());archives.append({'path':str(path.relative_to(ROOT)),
                'gzipSha256':sha256_file(path),'rawSha256':hashlib.sha256(raw).hexdigest(),'rawBytes':len(raw)})
        runs.append({'runId':run_id,'planSha256':sha256_file(pp),'learningRate':plan['config']['learningRate'],
            'encoderParameters':record['encoderParameters'],'headParameters':record['headParameters'],
            'checkpoint':record['checkpoint'],'encoderUnchanged':record['encoderUnchanged'],
            'quality':quality(record['fitAndDevelopmentPredictions']),'timing':statistics_by_case(record['attempts']),
            'forwardWindowsIncludingFitFeatures':forwards,'timedInferenceItems':len(record['attempts']),
            'supervisor':record['supervisor'],'fitLossFirstLast':{t:[v[0],v[-1]] for t,v in record['fitLosses'].items()}})
        details[version]=(plan,record)
    first=shared.read_json(DATA/(PREFIX+'r1.record.json'))
    if first['attempts'] or first['supervisor']['stopReason']!='supervisor_failure':raise ValueError('first failure evidence changed')
    if sha256_file(DATA/'code/m01_shared-r1.py')!=shared.read_json(DATA/(PREFIX+'r1.plan.json'))['code']['experiments/world-components-logic/m01_shared.py']:raise ValueError('first source snapshot mismatch')
    summary={'schema':'jity-d-m01-shared-summary-v1','date':'2026-11-02','scope':'exposed_old_development_probe_only',
       'oldDevelopmentGroups':20,'fitGroups':16,'retainedPreviouslyObservedGroups':4,'newIndependentTrainingGroups':0,
       'round1TrainingQuota':0,'formalEvaluationAllowed':False,'semanticQualityApproved':False,'fullRequest500msStatus':'unverified',
       'baselineQuality':quality(baseline['fitAndDevelopmentPredictions']),'runs':runs,'archives':archives,
       'firstStartFailure':{'runId':PREFIX+'r1','reason':first['supervisor']['error'],'businessCalls':0,
            'plannedUnstartedItems':40,'historicalSupervisorOmittedSlots':True}}
    encoded=(json.dumps(summary,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    return summary,{ART/'l3-6-m01-shared-summary.json':encoded,
                    ART/'l3-6-m01-shared-results.html':render(summary,details).encode('utf-8')}


def render(summary,details):
    e=lambda x:html.escape(str(x));latest=summary['runs'][-1]
    parts=['''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>L3 完整场景共享读取实测</title><style>body{margin:0;background:#f4f6f8;color:#20313e;font:16px/1.7 system-ui,sans-serif}main{max-width:1100px;margin:auto;padding:24px 18px}article{background:white;padding:22px;margin:18px 0;border:1px solid #dce3e8;border-radius:12px}table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:10px;text-align:left;border-bottom:1px solid #dde4e8}.scroll{overflow:auto}.bad{color:#a7352e}.muted{color:#667784}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f6f8;padding:12px;font-size:13px}h1{font-size:28px}h2{font-size:21px}</style><main><p class="muted">D / 2026-11-02 · 已公开旧开发题的探索试验</p><h1>完整场景共享读取：速度与漏判分别看</h1><p>同一个约1028万参数的冻结编码器，旧方案为每个候选重复读取场景，新方案只读取一次，再用学习到的人物融合头判断。两套头和表示不同，本页比较工程候选，不声称输出数值等价。</p>''']
    parts.append(f'<article><h2>本次实际做了什么</h2><p>新判断头共 {latest["headParameters"]:,} 参数；16来源组拟合，4个已在前批公开的开发场景用于观察，每个臂每题重复5次。新90组完全未使用，仍需独立训练数据和正式校准。本批不生成行动正文、反应或共同结果，也未测完整500毫秒计算。</p><p>原子事实和完整候选保留，每窗≤512；人物身份池按输入字段/ID建立，语义是/否由学习头判断。事实送入模型不等于模型已理解全部跨窗关系。</p></article>')
    parts.append('<article><h2>先看结论</h2><p>纠正训练后的r3：目标分析从每个候选重读场景的12窗降为共享4窗，完整单项中位耗时约0.49–0.50秒降至0.20–0.21秒；行动判断约0.19秒，略慢于同批旧方案。两项仍未达到50毫秒局部预算。</p><p class="bad">原来漏掉两人的开闸题现在选对，但原来没有目标的系鞋带题又误选p2、p3，完整目标集合仍只命中1/2。行动保留题2/2。新表示能拟合8/8训练场景，不代表能可靠处理新场景；不能晋升为可用组件。</p></article>')
    for run in summary['runs']:
        version=run['runId'][-2:];plan,record=details[version]
        parts.append(f'<article><h2>{e(version)}：学习率 {run["learningRate"]}</h2><p>{"原学习率的融合头趋向常量分数，拟合失败，完整保留。" if version=="r2" else "依据拟合损失失败登记一次较小学习率纠正；不改阈值、题目、训练步数或保留组。"}</p><div class="scroll"><table><tr><th>新共享头</th><th>拟合题整题命中</th><th>已公开保留开发题命中</th><th>保留目标漏选/错选</th></tr>')
        for task in ('D02','D03'):
            q=run['quality'][task];a=q['fit'];b=q['retained_development']
            missed=f'{b["missedTargets"]}/{b["extraTargets"]}' if task=='D03' else '不适用'
            parts.append(f'<tr><td>{task}</td><td>{a["matched"]}/{a["groups"]}</td><td>{b["matched"]}/{b["groups"]}</td><td>{missed}</td></tr>')
        parts.append('</table></div><div class="scroll"><table><tr><th>题目</th><th>旧方案中位/最大ms</th><th>共享方案中位/最大ms</th><th>读取窗口：旧→新</th><th>局部50ms</th></tr>')
        for cid in sorted({r['caseId'] for r in run['timing']}):
            a=next(r for r in run['timing'] if r['arm']=='legacy' and r['caseId']==cid);b=next(r for r in run['timing'] if r['arm']=='shared' and r['caseId']==cid)
            parts.append(f'<tr><td>{e(cid)}</td><td>{a["p50Ms"]:.2f}/{a["maxMs"]:.2f}</td><td>{b["p50Ms"]:.2f}/{b["maxMs"]:.2f}</td><td>{a["windows"]}→{b["windows"]}</td><td class="bad">{e(b["local50ms"])}</td></tr>')
        parts.append('</table></div><p>同一进程、CPU单线程、交替顺序；每次重新分词/完整编码，包含逐窗日志和头计算，不使用计时特征缓存。每题只有5次观测，不能签正式性能；完整500ms未测。</p>')
        for c in plan['cases']:
            cid=c['caseId'];label=next(r['label'] for r in plan['dataset'] if r['case']['caseId']==cid)
            observations=[{k:a[k] for k in ('arm','caseId','repeat','elapsedMs','probabilities','decoded','headMs')} for a in record['attempts'] if a['caseId']==cid]
            parts.append(f'<details><summary>{e(cid)} · 原判据 {e(label)} · 查看所有预测/耗时</summary><pre>{e(json.dumps(observations,ensure_ascii=False,indent=2))}</pre><p>完整原输入</p><pre>{e(json.dumps(c["input"],ensure_ascii=False,indent=2))}</pre></details>')
        parts.append(f'<p><a href="m01-fitting/{run["runId"]}.plan.json">本批冻结计划</a> · <a href="m01-fitting/{run["runId"]}.record.json.gz">完整记录</a> · <a href="m01-fitting/{run["runId"]}.record.windows.jsonl.gz">逐窗事件</a></p></article>')
    parts.append('<article><h2>边界与下一步</h2><p class="bad">共享读取减少了重复计算，不代表新判断头质量通过；按本页逐项实际成绩判断。50ms局部预算与500ms完整目标不变，浏览器、生产接线、反应/共同结果协同、来源独立和正式泛化仍未通过。</p><p>首次r1在资源监测权限处停止，0业务调用，40项计划任务未启动；旧监督记录漏列这些slot，保留原件并在汇总中注明，后续代码与回归已纠正。r2/r3在可监测资源的方式下执行，均保留时间/RSS上限。权重仅在D本地忽略目录，训练和推理大记录gzip无损归档。</p><p><a href="l3-6-m01-shared-summary.json">汇总、哈希与全部运行信息</a> · <a href="l3-5-m01-results.html">前批结果</a></p></article></main></html>')
    return ''.join(parts)


EVENT_RUN='m01-event-dev42-20261102-r1'
EVENT_ARMS=('baseline','event','event2')
EVENT_BASELINE_PLAN=DATA/(PREFIX+'r3.plan.json')
EVENT_BASELINE_RECORD=DATA/(PREFIX+'r3.record.json.gz')


def validate_event_run(plan,record,events,baseline):
    if (record['status']!='diagnostic_completed' or record['supervisor']['exitCode']!=0
            or record['supervisor']['stopReason'] is not None or record['unexecutedAttempts']
            or record.get('windowEventMalformedLines') or not record['encoderUnchanged']):
        raise ValueError('incomplete event-depth run')
    if (plan['formalEvaluationAllowed'] is not False or plan['round1TrainingQuota']!=0
            or plan['newIndependentTrainingGroups']!=0 or not plan['retainedDevelopmentPreviouslyObserved']):
        raise ValueError('formal scope changed')
    if (plan['configSha256']!=shared.digest(plan['config']) or plan['config']['reducedEncoderLayerIndices']!=[0,1]
            or plan['config']['threshold']!=.5 or plan['config']['stepsPerHead']!=200
            or plan['config']['seed']!=42 or plan['config']['learningRate']!=.0003):raise ValueError('event configuration drift')
    if (record['formalEvaluationAllowed'] is not False or record['semanticQualityApproved'] is not False
            or record['fullRequestMeasured'] is not False):raise ValueError('record scope promoted')
    runtime=record['actualRuntime']
    if runtime['device']!='cpu' or runtime['threads']!=1 or runtime['interopThreads']!=1:raise ValueError('runtime resource drift')
    if set(record['fitLosses'])!=set(EVENT_ARMS[1:]):raise ValueError('fitting arm coverage changed')
    for tasks in record['fitLosses'].values():
        if set(tasks)!={'D02','D03'} or any(len(v)!=200 or any(not math.isfinite(x) for x in v) for v in tasks.values()):
            raise ValueError('fitting loss/step coverage changed')
    original=json.loads(EVENT_BASELINE_PLAN.read_bytes())
    if plan['dataset']!=original['dataset'] or plan['cases']!=original['cases'] or plan['datasetSha256']!=shared.digest(plan['dataset']):
        raise ValueError('source groups/labels changed')
    if (plan['model']!=original['model'] or plan['baseline']['checkpoint']!=baseline['checkpoint']
            or plan['baseline']['trainedHeadSha256']!=baseline['trainedHeadSha256']):raise ValueError('baseline identity changed')
    if record['encoderVariants']['event']['tensorSha256']!=baseline['encoderTensorSha256']:raise ValueError('full encoder changed')
    if {a:v['layers'] for a,v in record['encoderVariants'].items()}!={'baseline':6,'event':6,'event2':2}:raise ValueError('encoder layer count changed')
    if record['encoderVariants']['baseline']!=record['encoderVariants']['event']:raise ValueError('baseline encoder mismatch')
    if record['trainedHeadSha256']['baseline']!=baseline['trainedHeadSha256']:raise ValueError('baseline head mismatch')
    cases={r['case']['caseId']:r for r in plan['dataset']}
    observed={c['caseId'] for c in plan['cases']}
    expected={(arm,cid,i) for arm in EVENT_ARMS for cid in observed for i in range(5)}
    for field in ('attempts','attemptSlots'):
        rows=record[field]
        if len(rows)!=60 or {(a['arm'],a['caseId'],a['repeat']) for a in rows}!=expected:raise ValueError('attempt coverage changed')
        if any(a['status']!='complete' for a in rows):raise ValueError('incomplete attempt')
    trace=[]
    def coverage(row,phase):
        cid=row['caseId'];c=cases[cid]['case'];cov=row['coverage'];validate_coverage(c,cov,'shared')
        expected_anchor=shared.event_indices(c,cov['factRecords']) if row['arm']!='baseline' else None
        if cov['eventAnchorFactIds']!=expected_anchor:raise ValueError('action anchor changed')
        for i,w in enumerate(cov['windows']):trace.append((phase,row['arm'],cid,row.get('repeat'),i,w))
    feature_ids={(r['arm'],r['caseId']) for r in record['featureCoverage']}
    if len(record['featureCoverage'])!=40 or feature_ids!={(a,c) for a in EVENT_ARMS[1:] for c in cases}:raise ValueError('fit feature coverage changed')
    for row in record['featureCoverage']:coverage(row,'feature_fit')
    fitted={(r['arm'],r['caseId']):r for r in record['fitAndDevelopmentPredictions']}
    if len(record['fitAndDevelopmentPredictions'])!=40 or set(fitted)!=feature_ids:raise ValueError('fit prediction coverage changed')
    for (_,cid),r in fitted.items():
        if any(r[k]!=cases[cid][k] for k in ('role','label')) or r['task']!=cases[cid]['case']['task']:raise ValueError('fit label changed')
    baseline_predictions={r['caseId']:r for r in baseline['fitAndDevelopmentPredictions']}
    for a in record['attempts']:
        coverage(a,'inference')
        if a['featureCacheUsed'] or a['inputSha256']!=shared.digest(cases[a['caseId']]['case']['input']):raise ValueError('cached/changed input')
        ref=baseline_predictions[a['caseId']] if a['arm']=='baseline' else fitted[(a['arm'],a['caseId'])]
        if a['probabilities']!=ref['probabilities'] or a['decoded']!=ref['decoded']:raise ValueError('checkpoint prediction drift')
        c=cases[a['caseId']]['case'];values=a['probabilities'];targets=a['coverage']['targets']
        if len(values)!=len(targets) or any(not math.isfinite(v) or not 0<=v<=1 for v in values):raise ValueError('invalid probability vector')
        decoded=({'kind':'act' if values[0]>=.5 else 'skip'} if c['task']=='D02' else
                 {'targets':[{'targetId':t} for t,p in zip(targets,values) if p>=.5]})
        if a['decoded']!=decoded:raise ValueError('decision threshold drift')
        parts=list(a['coverage']['timing'].values())+[a[k] for k in ('startJournalMs','endJournalMs','headMs')]
        total=a['elapsedIncludingEndJournalMs']
        if (any(not math.isfinite(x) or x<0 for x in parts+[total,a['elapsedMs']])
                or total<a['elapsedMs']+a['endJournalMs'] or total+0.001<sum(parts)):
            raise ValueError('invalid inclusive timing')
    starts={e['eventId']:e for e in events if e['status']=='running'}
    ends={e['eventId']:e for e in events if e['status']=='complete'}
    if len(events)!=2*len(trace) or set(starts)!=set(range(len(trace))) or set(ends)!=set(starts):raise ValueError('window event count changed')
    for i,(phase,arm,cid,repeat,index,w) in enumerate(trace):
        for event in (starts[i],ends[i]):
            if (event['phase'],event['arm'],event['caseId'],event.get('repeat'),event['windowIndex'])!=(phase,arm,cid,repeat,index):raise ValueError('window event identity changed')
            for key in ('inputIds','tokenTypeIds','factIds','payloadTokens','totalTokens','factSpans'):
                if event[key]!=w[key]:raise ValueError('window payload changed')
    return len(trace)


def verify_event_source(name,expected):
    if (ROOT/name).exists() and sha256_file(ROOT/name)==expected:return
    # Future maintenance can still verify the exact executed bytes from local history.
    revisions=subprocess.check_output(['git','log','-30','--format=%H','--',name],cwd=ROOT,text=True).splitlines()
    for revision in revisions:
        raw=subprocess.check_output(['git','show',revision+':'+name],cwd=ROOT)
        if hashlib.sha256(raw).hexdigest()==expected:return
    raise ValueError('executed event source unavailable in local Git: '+name)


def build_event():
    pp=DATA/(EVENT_RUN+'.plan.json');rp=DATA/(EVENT_RUN+'.record.json.gz');ep=DATA/(EVENT_RUN+'.record.windows.jsonl.gz')
    plan=json.loads(pp.read_bytes());record=read_archive(rp);raw=gzip.decompress(ep.read_bytes())
    events=[json.loads(line) for line in raw.splitlines() if line.strip()];baseline=read_archive(EVENT_BASELINE_RECORD)
    if record['planSha256']!=sha256_file(pp) or record['windowEventsSha256']!=hashlib.sha256(raw).hexdigest():raise ValueError('event evidence digest changed')
    if plan['baseline']['recordSha256']!=sha256_file(EVENT_BASELINE_RECORD) or plan['baseline']['planSha256']!=sha256_file(EVENT_BASELINE_PLAN):raise ValueError('baseline files changed')
    for name,h in plan['code'].items():verify_event_source(name,h)
    if sha256_file(ROOT/plan['protocolPath'])!=plan['protocolSha256']:raise ValueError('event protocol changed')
    forwards=validate_event_run(plan,record,events,baseline)
    scores={'baseline':quality(baseline['fitAndDevelopmentPredictions'])}
    scores.update({a:quality([r for r in record['fitAndDevelopmentPredictions'] if r['arm']==a]) for a in EVENT_ARMS[1:]})
    timing=[]
    for arm in EVENT_ARMS:
        for case in plan['cases']:
            rows=[a for a in record['attempts'] if a['arm']==arm and a['caseId']==case['caseId']]
            elapsed=[a['elapsedIncludingEndJournalMs'] for a in rows]
            components={key:statistics.mean(a['coverage']['timing'][key] for a in rows) for key in rows[0]['coverage']['timing']}
            components.update({k:statistics.mean(a[k] for a in rows) for k in ('headMs','startJournalMs','endJournalMs')})
            components['otherMs']=statistics.mean(elapsed)-sum(components.values())
            timing.append({'arm':arm,'caseId':case['caseId'],'observations':len(rows),'p50Ms':statistics.median(elapsed),'maxMs':max(elapsed),
                'meanMs':statistics.mean(elapsed),'componentsMeanMs':components,'windows':len(rows[0]['coverage']['windows']),
                'predicted':rows[0]['decoded'],'probabilities':rows[0]['probabilities'],
                'local50ms':'fail' if max(elapsed)>50 else 'unverified_insufficient_observations'})
    run={'runId':EVENT_RUN,'quality':scores,'timing':timing,'encoderVariants':record['encoderVariants'],
         'headParametersPerArm':record['headParametersPerArm'],'checkpoint':record['checkpoint'],'supervisor':record['supervisor'],
         'forwardWindowsIncludingFitFeatures':forwards,'timedInferenceItems':len(record['attempts']),
         'fitLossFirstLast':{a:{t:[v[0],v[-1]] for t,v in tasks.items()} for a,tasks in record['fitLosses'].items()}}
    summary={'schema':'jity-d-event-depth-summary-v1','date':'2026-11-02','scope':'exposed_old_development_probe_only',
             'oldDevelopmentGroups':20,'fitGroups':16,'retainedPreviouslyObservedGroups':4,'newIndependentTrainingGroups':0,
             'round1TrainingQuota':0,'formalEvaluationAllowed':False,'semanticQualityApproved':False,'fullRequest500msStatus':'unverified',
             'timingDefinition':'fresh input through per-attempt end journal; batch setup/finalization separate','runs':[run],
             'archives':[{'path':str(p.relative_to(ROOT)),'gzipSha256':sha256_file(p),
                          'rawSha256':hashlib.sha256(gzip.decompress(p.read_bytes())).hexdigest()} for p in (rp,ep)]}
    return summary,{ART/'l3-7-m01-event-summary.json':(json.dumps(summary,ensure_ascii=False,indent=2)+'\n').encode(),
                    ART/'l3-7-m01-event-results.html':render_event(summary,plan,record).encode()}


def render_event(summary,plan,record):
    e=lambda x:html.escape(str(x));run=summary['runs'][0]
    names={'baseline':'上一版：6层、混合动作表示','event':'独立动作表示、6层','event2':'独立动作表示、2层'}
    parts=['''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>L3 动作判断与更小编码器</title><style>body{background:#f4f6f8;color:#20313e;font:16px/1.7 system-ui;margin:0}main{max-width:1150px;margin:auto;padding:24px}section{background:white;border-radius:12px;padding:20px;margin:20px 0}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;font-size:14px}th,td{padding:9px;text-align:left;border-bottom:1px solid #ddd}pre{white-space:pre-wrap;overflow-wrap:anywhere}.bad{color:#a7352e}h1{font-size:28px}</style><main><p>D / L3 · 2026-11-02 · 开发探索</p><h1>动作单独看，编码器缩小后会怎样？</h1><p>三种方案同机、同题、相同训练设置；旧版直接加载原检查点，两个新版本重新拟合小判断头。完整资料与全部人物均保留，不靠关键词规则决定目标。</p><section><h2>这次结果能说明什么</h2><p>只有4个反复看过的开发场景，每方案每题重复5次，共60次推理；重复不等于新题。拟合使用16组，另4组不参与梯度。新90组未使用，来源核验和独立新题训练仍待。</p><p class="bad">这是开发诊断，不能据此宣布泛化或组件可用。D02仅判断做/不做，没有生成行动；反应、共同结果及完整500毫秒流程仍未测试。</p></section><section><h2>判断是否正确</h2><div class="scroll"><table><tr><th>方案</th><th>任务</th><th>拟合题命中</th><th>已公开开发题命中</th><th>目标漏选 / 多选</th></tr>''']
    for arm in EVENT_ARMS:
        for task in ('D02','D03'):
            q=run['quality'][arm][task];f=q['fit'];r=q['retained_development']
            extra=f'{r["missedTargets"]} / {r["extraTargets"]}' if task=='D03' else '—'
            parts.append(f'<tr><td>{names[arm]}</td><td>{task}</td><td>{f["matched"]}/{f["groups"]}</td><td>{r["matched"]}/{r["groups"]}</td><td>{extra}</td></tr>')
    parts.append('</table></div></section><section><h2>速度：每次从输入到结束存档</h2><p>本批完整单项耗时包含开始和结束存档，旧页未包含结束存档，不能直接拿两页数字比较。以下均为本批同条件数字。窗口仍≤512，未缓存输入特征。</p><div class="scroll"><table><tr><th>方案 / 题目</th><th>中位 / 最大毫秒</th><th>编码器平均</th><th>输入平均</th><th>两次快照存档平均</th><th>局部50毫秒</th></tr>')
    for t in run['timing']:
        c=t['componentsMeanMs']
        parts.append(f'<tr><td>{names[t["arm"]]}<br>{e(t["caseId"])}</td><td>{t["p50Ms"]:.2f} / {t["maxMs"]:.2f}</td><td>{c["encoderMs"]:.2f}</td><td>{c["packMs"]:.2f}</td><td>{c["startJournalMs"]+c["endJournalMs"]:.2f}</td><td>{e(t["local50ms"])}</td></tr>')
    parts.append('</table></div><p>判断头、张量、池化/哈希、逐窗日志及其他开销见下方完整明细，所有分项使用平均数，合计等于平均总耗时。小批观测不能签正式性能通过。</p></section>')
    for case in plan['cases']:
        rows=[{k:a[k] for k in ('arm','caseId','repeat','decoded','probabilities','elapsedMs','elapsedIncludingEndJournalMs')} for a in record['attempts'] if a['caseId']==case['caseId']]
        label=next(r['label'] for r in plan['dataset'] if r['case']['caseId']==case['caseId'])
        parts.append(f'<section><details><summary>{e(case["caseId"])} · 原判据 {e(label)} · 展开每次预测</summary><pre>{e(json.dumps(rows,ensure_ascii=False,indent=2))}</pre></details></section>')
    parts.append(f'<section><h2>更小模型的边界</h2><p>两层版从同一M01保留前两层与全部嵌入，未做蒸馏、未重新训练编码器，不保证语义等价。实际参数和逐项耗时如下。CPU单线程、并发1、120秒/2048MiB监督上限。</p><details><summary>全部汇总和耗时分项</summary><pre>{e(json.dumps(run,ensure_ascii=False,indent=2))}</pre></details><p><a href="m01-fitting/{EVENT_RUN}.plan.json">冻结计划</a> · <a href="m01-fitting/{EVENT_RUN}.record.json.gz">完整记录</a> · <a href="m01-fitting/{EVENT_RUN}.record.windows.jsonl.gz">窗口事件</a> · <a href="l3-7-m01-event-summary.json">机器汇总</a> · <a href="l3-6-m01-shared-results.html">上一批</a></p></section></main></html>')
    return ''.join(parts)



def main():
    p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group(required=True)
    m.add_argument('--check',action='store_true');m.add_argument('--write-new',action='store_true')
    p.add_argument('--event',action='store_true');a=p.parse_args()
    summary,files=build_event() if a.event else build()
    for path,raw in files.items():
        if path.exists() and path.read_bytes()!=raw:raise ValueError('report differs; preserve earlier version')
        if a.check and not path.exists():raise ValueError('report missing')
    if a.write_new:
        for path,raw in files.items():
            if not path.exists():
                with path.open('xb') as f:f.write(raw)
    print(json.dumps({k:summary[k] for k in ('scope','formalEvaluationAllowed','fullRequest500msStatus')},ensure_ascii=False))


if __name__=='__main__':main()
