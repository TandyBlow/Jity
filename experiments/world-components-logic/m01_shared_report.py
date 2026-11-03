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



JOURNAL_RUN='m01-journal-dev42-20261103-r1'
JOURNAL_ARMS=('snapshot','append')
JOURNAL_BASE_PLAN=DATA/(EVENT_RUN+'.plan.json')
JOURNAL_BASE_RECORD=DATA/(EVENT_RUN+'.record.json.gz')


def validate_journal_run(plan,record,journal_path,baseline,*,arms=JOURNAL_ARMS,allow_probability_drift=False,attempts_per_case=5):
    import copy
    import experiment
    if (record['status']!='diagnostic_completed' or record['supervisor']['exitCode']!=0 or record['supervisor']['stopReason'] is not None
            or record['unexecutedAttempts'] or record.get('journalRecoveryError') or record['journalRecovery']['partialTailBytes']):raise ValueError('incomplete journal run')
    if (record['trainingSteps']!=0 or not record['encoderUnchanged'] or not record['headsUnchanged']
            or plan['config']['trainingSteps']!=0 or plan['configSha256']!=shared.digest(plan['config'])):raise ValueError('fixed inference policy drift')
    for key,value in {'threshold':.5,'reducedEncoderLayerIndices':[0,1],'attemptsPerCase':attempts_per_case,'featureCacheForTiming':False,
                      'headsFrozen':True,'attemptBoundaryFsync':True}.items():
        if plan['config'][key]!=value:raise ValueError('fixed inference policy drift: '+key)
    if (plan['formalEvaluationAllowed'] is not False or record['semanticQualityApproved'] is not False or record['fullRequestMeasured'] is not False
            or plan['round1TrainingQuota']!=0 or not plan['retainedDevelopmentPreviouslyObserved']):raise ValueError('journal scope promoted')
    original=json.loads(JOURNAL_BASE_PLAN.read_bytes())
    if plan['dataset']!=original['dataset'] or plan['cases']!=original['cases'] or plan['model']!=original['model']:raise ValueError('fixed cases/model changed')
    if (record['encoder']!=baseline['encoderVariants']['event2'] or record['checkpoint']!=baseline['checkpoint']
            or record['trainedHeadSha256']!=baseline['trainedHeadSha256']['event2']):raise ValueError('fixed weights changed')
    if record['actualRuntime']['threads']!=1 or record['actualRuntime']['interopThreads']!=1 or record['actualRuntime']['device']!='cpu':raise ValueError('resource drift')
    # Rebuild the final record from the append stream, not from a successful-looking status.
    replay=copy.deepcopy(record);experiment.reconcile_journal(replay,journal_path,'report_replay')
    for key in ('attempts','attemptSlots','forwardAttempts','unexecutedAttempts'):
        if replay[key]!=record[key]:raise ValueError('journal/snapshot mismatch: '+key)
    entries,partial=experiment.read_journal(journal_path,record['planSha256'])
    cases={c['caseId']:c for c in plan['cases']}
    count=len(cases)*len(arms)*attempts_per_case
    prior_inputs={a['caseId']:a['coverage'] for a in baseline['attempts'] if a['arm']=='event2'}
    window_count=sum(len(prior_inputs[c]['windows']) for c in cases)*len(arms)*attempts_per_case
    if partial or len(entries)!=1+count*3+window_count*2:raise ValueError('journal event count mismatch')
    expected={(a,c,i) for a in arms for c in cases for i in range(attempts_per_case)}
    for field in ('attempts','attemptSlots'):
        if len(record[field])!=count or {(a['arm'],a['caseId'],a['repeat']) for a in record[field]}!=expected:raise ValueError('attempt count mismatch')
    predictions={r['caseId']:r for r in baseline['fitAndDevelopmentPredictions'] if r['arm']=='event2'}
    old_inputs={a['caseId']:a['coverage'] for a in baseline['attempts'] if a['arm']=='event2'}
    trace=[]
    for a in record['attempts']:
        if a['status']!='complete' or a['featureCacheUsed'] or a.get('exactTelemetryTimingAvailable') is False:raise ValueError('incomplete/cached/unmeasured attempt')
        c=cases[a['caseId']];cov=a['coverage'];validate_coverage(c,cov,'shared')
        prior=old_inputs[a['caseId']]
        for key in ('factRecords','targets','anchorFactIds','candidateFactIds','eventAnchorFactIds'):
            if cov[key]!=prior[key]:raise ValueError('previous input representation changed')
        keys=('inputIds','tokenTypeIds','factIds','factSpans','payloadTokens','totalTokens')
        if [{k:w[k] for k in keys} for w in cov['windows']]!=[{k:w[k] for k in keys} for w in prior['windows']]:
            raise ValueError('previous encoded windows changed')
        if cov['eventAnchorFactIds']!=shared.event_indices(c,cov['factRecords']) or a['inputSha256']!=shared.digest(c['input']):raise ValueError('input/anchor changed')
        ref=predictions[a['caseId']]
        if not allow_probability_drift and (a['probabilities']!=ref['probabilities'] or a['decoded']!=ref['decoded']):raise ValueError('frozen prediction changed')
        values=a['probabilities'];targets=cov['targets']
        if len(values)!=len(targets) or any(not math.isfinite(v) or not 0<=v<=1 for v in values):raise ValueError('invalid probability vector')
        decoded=({'kind':'act' if values[0]>=.5 else 'skip'} if c['task']=='D02' else
                 {'targets':[{'targetId':t} for t,p in zip(targets,values) if p>=.5]})
        if a['decoded']!=decoded:raise ValueError('decision threshold changed')
        parts=list(cov['timing'].values())+[a[k] for k in ('headMs','startJournalMs','snapshotStartMs','resultJournalMs','snapshotEndMs','telemetryJournalMs')]
        total=a['elapsedIncludingTelemetryMs']
        if any(not math.isfinite(x) or x<0 for x in parts+[total]) or total+0.001<sum(parts) or total<a['elapsedThroughResultMs']+a['telemetryJournalMs']:
            raise ValueError('inclusive journal timing mismatch')
        for i,w in enumerate(cov['windows']):trace.append((a,i,w))
    if len(trace)!=window_count or len(record['forwardAttempts'])!=window_count:raise ValueError('window count mismatch')
    for i,((a,index,w),e) in enumerate(zip(trace,record['forwardAttempts'])):
        if e['status']!='complete' or e['eventId']!=i or (e['arm'],e['caseId'],e['repeat'],e['windowIndex'])!=(a['arm'],a['caseId'],a['repeat'],index):raise ValueError('window identity mismatch')
        for key in ('inputIds','tokenTypeIds','factIds','factSpans','payloadTokens','totalTokens'):
            if e[key]!=w[key]:raise ValueError('journal window payload mismatch')
    return predictions


def build_journal():
    pp=DATA/(JOURNAL_RUN+'.plan.json');rp=DATA/(JOURNAL_RUN+'.record.json.gz');jp=DATA/(JOURNAL_RUN+'.record.journal.jsonl.gz')
    plan=json.loads(pp.read_bytes());record=read_archive(rp);raw=gzip.decompress(jp.read_bytes());baseline=read_archive(JOURNAL_BASE_RECORD)
    if record['planSha256']!=sha256_file(pp) or record['journalRecovery']['sha256']!=hashlib.sha256(raw).hexdigest():raise ValueError('journal evidence digest mismatch')
    if plan['baseline']['planSha256']!=sha256_file(JOURNAL_BASE_PLAN) or plan['baseline']['recordSha256']!=sha256_file(JOURNAL_BASE_RECORD):raise ValueError('original checkpoint evidence changed')
    for name,h in plan['code'].items():verify_event_source(name,h)
    if sha256_file(ROOT/plan['protocolPath'])!=plan['protocolSha256']:raise ValueError('journal protocol changed')
    predictions=validate_journal_run(plan,record,jp,baseline);timing=[]
    for arm in JOURNAL_ARMS:
        for case in plan['cases']:
            rows=[a for a in record['attempts'] if a['arm']==arm and a['caseId']==case['caseId']]
            values=[a['elapsedIncludingTelemetryMs'] for a in rows]
            parts={k:statistics.mean(a['coverage']['timing'][k] for a in rows) for k in rows[0]['coverage']['timing']}
            parts.update({k:statistics.mean(a[k] for a in rows) for k in ('headMs','startJournalMs','snapshotStartMs','resultJournalMs','snapshotEndMs','telemetryJournalMs')})
            parts['otherMs']=statistics.mean(values)-sum(parts.values())
            timing.append({'arm':arm,'caseId':case['caseId'],'observations':len(rows),'p50Ms':statistics.median(values),
                'maxMs':max(values),'meanMs':statistics.mean(values),'componentsMeanMs':parts,
                'local50ms':'fail' if max(values)>50 else 'unverified_insufficient_observations',
                'predicted':rows[0]['decoded'],'probabilities':rows[0]['probabilities']})
    # Only inference cases were run. Do not re-label historical fit results as new tests.
    rows=[predictions[c['caseId']] for c in plan['cases']]
    run={'runId':JOURNAL_RUN,'quality':{a:quality(rows) for a in JOURNAL_ARMS},'timing':timing,
         'trainingSteps':0,'timedInferenceItems':40,'forwardWindows':160,'journalEvents':441,
         'encoder':record['encoder'],'headParameters':record['headParameters'],'checkpoint':record['checkpoint'],
         'weightsUnchanged':True,'exactPreviousProbabilities':True,'supervisor':record['supervisor'],
         'allAttemptWallMs':sum(a['elapsedIncludingTelemetryMs'] for a in record['attempts']),
         'batchFinalSnapshotTiming':'included in child process wall; not separately measured',
         'supervisorReplayTiming':'not measured; excluded from process wall, no full-request claim'}
    summary={'schema':'jity-d-journal-summary-v1','date':'2026-11-03','scope':'frozen_checkpoint_exposed_development_inference_only',
        'formalEvaluationAllowed':False,'semanticQualityApproved':False,'fullRequest500msStatus':'unverified',
        'newIndependentTrainingGroups':0,'round1TrainingQuota':0,'runs':[run],
        'archives':[{'path':str(p.relative_to(ROOT)),'gzipSha256':sha256_file(p),
            'rawSha256':hashlib.sha256(gzip.decompress(p.read_bytes())).hexdigest()} for p in (rp,jp)]}
    return summary,{ART/'l3-8-m01-journal-summary.json':(json.dumps(summary,ensure_ascii=False,indent=2)+'\n').encode(),
                    ART/'l3-8-m01-journal-results.html':render_journal(summary,record).encode()}


def render_journal(summary,record):
    e=lambda x:html.escape(str(x));run=summary['runs'][0]
    parts=['''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>L3 追加记录速度对比</title><style>body{background:#f4f6f8;color:#20313e;font:16px/1.7 system-ui;margin:0}main{max-width:1080px;margin:auto;padding:24px}section{background:white;padding:22px;border-radius:12px;margin:20px 0}table{border-collapse:collapse;width:100%;font-size:14px}td,th{text-align:left;padding:10px;border-bottom:1px solid #ddd}.scroll{overflow:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere}.bad{color:#a7352e}h1{font-size:28px}</style><main><p>D / L3 · 2026-11-03 · 固定模型，只改记录方式</p><h1>不用每算一题，就重写整本实验记录</h1><p>同一个约712万参数的两层编码器、同一份已训练判断头。这次训练0步，两种方式分别在4道旧开发题上重复5次，共40次推理。</p><section><h2>答案保持一致</h2><p>所有输出分数与上一批两层版逐值一致：两道行动判断、两道目标判断均答对。没有重新训练、换题、裁掉人物或缓存模型特征。这是代码改动前后的结果一致性，不能升级为独立新题质量通过。</p></section><section><h2>速度看同一批的对比</h2><p>两种方式都追加完整审计事件；兼容对照另在每题前后重写整批快照，新方式只追加新增内容。新批没有前批的训练记录，不能把旧页300–346毫秒直接当成这里的基线。时间包含每题输入、计算、窗口日志、结果落盘，以及最后耗时记录本身。</p><div class="scroll"><table><tr><th>题目</th><th>重写整批：中位/最大ms</th><th>只追加：中位/最大ms</th><th>中位减少</th><th>局部50ms</th></tr>''']
    for cid in sorted({t['caseId'] for t in run['timing']}):
        a=next(t for t in run['timing'] if t['arm']=='snapshot' and t['caseId']==cid)
        b=next(t for t in run['timing'] if t['arm']=='append' and t['caseId']==cid)
        parts.append(f'<tr><td>{e(cid)}</td><td>{a["p50Ms"]:.2f}/{a["maxMs"]:.2f}</td><td>{b["p50Ms"]:.2f}/{b["maxMs"]:.2f}</td><td>{(1-b["p50Ms"]/a["p50Ms"])*100:.1f}%</td><td>{e(b["local50ms"])}</td></tr>')
    parts.append('''</table></div><p class="bad">完整非叙事流程的500毫秒目标仍未测。只有5次/题，未达到正式性能采样规模。批末汇总写入包含在子进程总耗时中，未单独计时；监督器退出后重放耗时未测，不把本页当作游戏请求总耗时。</p></section><section><h2>中断后记录能找回吗？</h2><p>441条追加事件重放一致，覆盖40次推理、160个窗口。开始和结果边界写入磁盘；已保存答案直接找回，不重新调用模型。测试用真实子进程在开始、窗口运行、窗口结束、结果保存、耗时保存等位置异常退出，分别保留已完成、未完成、未开始状态。</p><p>最后半行保留原字节并报告；中间行损坏、串批、重复或顺序错误明确拒绝。已存结果但缺精确尾部计时时，保留答案并标计时未知，不填0毫秒。本项是D实验记录恢复检查，尚未进行游戏浏览器恢复或断电认证。</p></section>''')
    parts.append(f'<section><details><summary>模型身份、分项耗时和全部结论</summary><pre>{e(json.dumps(run,ensure_ascii=False,indent=2))}</pre></details></section>')
    rows=[{k:a[k] for k in ('arm','caseId','repeat','probabilities','decoded','elapsedThroughResultMs','telemetryJournalMs','elapsedIncludingTelemetryMs')} for a in record['attempts']]
    parts.append(f'<section><details><summary>查看全部40次原始预测/耗时</summary><pre>{e(json.dumps(rows,ensure_ascii=False,indent=2))}</pre></details><p><a href="m01-fitting/{JOURNAL_RUN}.plan.json">冻结计划</a> · <a href="m01-fitting/{JOURNAL_RUN}.record.json.gz">完整记录</a> · <a href="m01-fitting/{JOURNAL_RUN}.record.journal.jsonl.gz">完整追加事件</a> · <a href="l3-8-m01-journal-summary.json">机器汇总</a> · <a href="l3-7-m01-event-results.html">上一批模型结果</a></p></section></main></html>')
    return ''.join(parts)



INPUT_RUN='m01-input-dev42-20261103-r2'
INPUT_ARMS=('reference','packed','fast','eager')
INPUT_POLICIES={
    'reference':{'packing':'reference','tokenizer':'slow','attention':'sdpa'},
    'packed':{'packing':'single','tokenizer':'slow','attention':'sdpa'},
    'fast':{'packing':'batch','tokenizer':'fast','attention':'sdpa'},
    'eager':{'packing':'batch','tokenizer':'fast','attention':'eager'}}


def validate_input_run(plan,record,journal_path,baseline):
    predictions=validate_journal_run(plan,record,journal_path,baseline,arms=INPUT_ARMS,allow_probability_drift=True)
    if plan['config']['runtimeArms']!=INPUT_POLICIES or plan['config']['probabilityTolerance']!=1e-6:raise ValueError('input/runtime comparison policy changed')
    rows=record['tokenizationAudit']
    if len(rows)!=20 or [r['caseId'] for r in rows]!=[r['case']['caseId'] for r in plan['dataset']]:raise ValueError('token audit coverage changed')
    for r in rows:
        if set(r['optimizedSha256'])!={'single','batch'} or set(r['optimizedSha256'].values())!={r['referenceSha256']}:raise ValueError('token audit differs')
    if record['tokenizerClasses']!={'slow':'BertTokenizer','fast':'BertTokenizerFast'}:raise ValueError('tokenizer identity changed')
    expected={'sdpa':{'attentionImplementation':'sdpa','attentionClasses':['BertSdpaSelfAttention']*2},
              'eager':{'attentionImplementation':'eager','attentionClasses':['BertSelfAttention']*2}}
    if record['encoderRuntimes']!=expected:raise ValueError('actual attention implementation changed')
    return predictions



def compare_probabilities(selected,predictions,tolerance,require_exact):
    exact=all(a['probabilities']==predictions[a['caseId']]['probabilities'] for a in selected)
    same=all(a['decoded']==predictions[a['caseId']]['decoded'] for a in selected)
    delta=max(abs(p-q) for a in selected for p,q in zip(a['probabilities'],predictions[a['caseId']]['probabilities']))
    stable=all(a['probabilities']==next(x['probabilities'] for x in selected if x['caseId']==a['caseId']) for a in selected)
    gate=(exact if require_exact else delta<=tolerance) and same and stable
    return {'exactProbabilities':exact,'maxAbsoluteProbabilityDelta':delta,'identicalDecisions':same,
            'repeatStable':stable,'registeredEquivalenceGate':'pass' if gate else 'fail'}

def build_input():
    pp=DATA/(INPUT_RUN+'.plan.json');rp=DATA/(INPUT_RUN+'.record.json.gz');jp=DATA/(INPUT_RUN+'.record.journal.jsonl.gz')
    plan=json.loads(pp.read_bytes());record=read_archive(rp);raw=gzip.decompress(jp.read_bytes());baseline=read_archive(JOURNAL_BASE_RECORD)
    if record['planSha256']!=sha256_file(pp) or record['journalRecovery']['sha256']!=hashlib.sha256(raw).hexdigest():raise ValueError('input evidence digest mismatch')
    if plan['baseline']['planSha256']!=sha256_file(JOURNAL_BASE_PLAN) or plan['baseline']['recordSha256']!=sha256_file(JOURNAL_BASE_RECORD):raise ValueError('fixed model evidence changed')
    for name,h in plan['code'].items():verify_event_source(name,h)
    if sha256_file(ROOT/plan['protocolPath'])!=plan['protocolSha256']:raise ValueError('input protocol changed')
    predictions=validate_input_run(plan,record,jp,baseline);timing=[];comparisons={};qualities={}
    for arm in INPUT_ARMS:
        selected=[a for a in record['attempts'] if a['arm']==arm]
        comparisons[arm]=compare_probabilities(selected,predictions,plan['config']['probabilityTolerance'],arm!='eager')
        rows=[]
        for case in plan['cases']:
            a=next(a for a in selected if a['caseId']==case['caseId']);ref=predictions[case['caseId']]
            rows.append({**ref,'decoded':a['decoded'],'probabilities':a['probabilities']})
            attempts=[a for a in selected if a['caseId']==case['caseId']];values=[a['elapsedIncludingTelemetryMs'] for a in attempts]
            parts={k:statistics.mean(a['coverage']['timing'][k] for a in attempts) for k in attempts[0]['coverage']['timing']}
            parts.update({k:statistics.mean(a[k] for a in attempts) for k in ('headMs','startJournalMs','snapshotStartMs','resultJournalMs','snapshotEndMs','telemetryJournalMs')})
            parts['otherMs']=statistics.mean(values)-sum(parts.values())
            timing.append({'arm':arm,'caseId':case['caseId'],'observations':len(attempts),'p50Ms':statistics.median(values),
                'maxMs':max(values),'meanMs':statistics.mean(values),'componentsMeanMs':parts,
                'local50ms':'fail' if max(values)>50 else 'unverified_insufficient_observations'})
        qualities[arm]=quality(rows)
    first=INPUT_RUN.replace('-r2','-r1');fp=DATA/(first+'.plan.json');fr=DATA/(first+'.record.json')
    failed_plan=json.loads(fp.read_bytes());failure=json.loads(fr.read_bytes());snapshot=DATA/'code/m01_input-r1.py'
    if failure['planSha256']!=sha256_file(fp) or failure['attempts'] or failure['unexecutedAttempts']!=80 or failure['forwardAttempts']:raise ValueError('pre-inference failure evidence changed')
    for name,h in failed_plan['code'].items():
        if name.endswith('/m01_shared.py'):
            if sha256_file(snapshot)!=h:raise ValueError('failed source snapshot mismatch')
        else:verify_event_source(name,h)
    run={'runId':INPUT_RUN,'quality':qualities,'timing':timing,'comparisons':comparisons,'tokenizationAuditGroups':20,
         'trainingSteps':0,'timedInferenceItems':80,'forwardWindows':320,'journalEvents':881,
         'encoder':record['encoder'],'headParameters':record['headParameters'],'checkpoint':record['checkpoint'],
         'weightsUnchanged':True,'encoderRuntimes':record['encoderRuntimes'],'tokenizerClasses':record['tokenizerClasses'],
         'supervisor':record['supervisor'],'timingScope':'all per-item work and journals; batch final write in process wall, supervisor replay unmeasured'}
    summary={'schema':'jity-d-input-runtime-summary-v1','date':'2026-11-03','scope':'frozen_checkpoint_exposed_development_inference_only',
        'formalEvaluationAllowed':False,'semanticQualityApproved':False,'fullRequest500msStatus':'unverified',
        'newIndependentTrainingGroups':0,'round1TrainingQuota':0,'runs':[run],
        'firstPreparationFailure':{'runId':first,'status':failure['status'],'error':failure['error'],'businessCalls':0,'unstartedItems':80},
        'archives':[{'path':str(p.relative_to(ROOT)),'gzipSha256':sha256_file(p),
            'rawSha256':hashlib.sha256(gzip.decompress(p.read_bytes())).hexdigest()} for p in (rp,jp)]}
    return summary,{ART/'l3-9-m01-input-summary.json':(json.dumps(summary,ensure_ascii=False,indent=2)+'\n').encode(),
                    ART/'l3-9-m01-input-results.html':render_input(summary,record).encode()}


def render_input(summary,record):
    e=lambda x:html.escape(str(x));run=summary['runs'][0]
    names={'reference':'原输入准备','packed':'去掉重复分词','fast':'快速分词＋单次装箱','eager':'快速分词＋eager编码'}
    parts=['''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>L3 输入准备与编码执行对比</title><style>body{margin:0;background:#f4f6f8;color:#20313e;font:16px/1.7 system-ui}main{max-width:1150px;margin:auto;padding:24px}section{background:white;padding:22px;border-radius:12px;margin:20px 0}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:9px;border-bottom:1px solid #ddd}pre{white-space:pre-wrap;overflow-wrap:anywhere}.bad{color:#a7352e}h1{font-size:28px}</style><main><p>D / L3 · 2026-11-03 · 固定两层模型，训练0步</p><h1>减少重复整理输入，再比较编码方式</h1><p>完整资料和所有人物保留；20组旧开发输入在推理前逐项核对优化前后的全部token与事实跨度，任何差异都停止。业务测试仍只有4道反复看过的开发题，四种方案各重复5次，共80次推理。</p><section><h2>先看输出有没有变化</h2><p>前3臂要求分数逐值一致；eager注意力在运行前登记最大概率差≤0.000001、行动/目标判定完全一致。浮点计算顺序不同与改模型权重分别记录，不能因判断相同就声称分数完全相同。</p><div class="scroll"><table><tr><th>方案</th><th>分数逐值一致</th><th>最大概率差</th><th>所有判定一致</th><th>已登记一致性门</th></tr>''']
    for a,c in run['comparisons'].items():
        parts.append(f'<tr><td>{names[a]}</td><td>{e(c["exactProbabilities"])}</td><td>{c["maxAbsoluteProbabilityDelta"]:.10g}</td><td>{e(c["identicalDecisions"])}</td><td>{e(c["registeredEquivalenceGate"])}</td></tr>')
    parts.append('</table></div><p>一致性门只检查改动前后是否可比，不等于新题质量通过。原4题答案已公开，不能据此宣布泛化。</p></section><section><h2>同批整项耗时，包含输入与记录</h2><div class="scroll"><table><tr><th>题目</th><th>原方案中位/最大ms</th><th>单次分词中位/最大ms</th><th>快速分词中位/最大ms</th><th>eager中位/最大ms</th></tr>')
    for cid in sorted({r['caseId'] for r in run['timing']}):
        parts.append(f'<tr><td>{e(cid)}</td>')
        for arm in INPUT_ARMS:
            t=next(t for t in run['timing'] if t['arm']==arm and t['caseId']==cid)
            parts.append(f'<td>{t["p50Ms"]:.2f}/{t["maxMs"]:.2f}</td>')
        parts.append('</tr>')
    parts.append('</table></div><p>所有臂都重新分词、执行全部窗口，不缓存特征；计入结果落盘和尾部遥测写入。局部是否超过50ms见下表；每题仅5次，即便本批全部低于50也只能记有限观察，完整500ms仍未测。</p><div class="scroll"><table><tr><th>方案</th><th>题目</th><th>输入准备平均ms</th><th>编码平均ms</th><th>局部50ms</th></tr>')
    for t in run['timing']:
        c=t['componentsMeanMs'];parts.append(f'<tr><td>{names[t["arm"]]}</td><td>{e(t["caseId"])}</td><td>{c["packMs"]:.3f}</td><td>{c["encoderMs"]:.3f}</td><td>{e(t["local50ms"])}</td></tr>')
    parts.append('</table></div></section><section><h2>执行范围与失败记录</h2><p class="bad">模型权重/判断头不变，不代表任务能力已通过。行动仍只判做/不做，反应、行动描述和共同结果没有接线；完整500ms、浏览器/生产与独立新题质量都未测。</p><p>第一批在生成输入核对哈希时把元组传给只接收JSON的工具而失败，0次业务推理、80项未开始；原计划/记录和执行源码保留。修正记录代码并补回归后，另用r2批次执行，未改分词策略或训练参数。</p><p>CPU单线程/并发1，120秒/2048MiB监督上限；批末汇总包含在子进程总耗时但未单独计时，监督器重放耗时未测。本页主指标是每项完成，不冒充完整游戏请求。</p></section>')
    parts.append(f'<section><details><summary>全部汇总、模型身份和分项耗时</summary><pre>{e(json.dumps(run,ensure_ascii=False,indent=2))}</pre></details><details><summary>全部80次原始分数和预测</summary><pre>{e(json.dumps([{k:a[k] for k in ("arm","caseId","repeat","probabilities","decoded","elapsedIncludingTelemetryMs")} for a in record["attempts"]],ensure_ascii=False,indent=2))}</pre></details><p><a href="m01-fitting/{INPUT_RUN}.plan.json">冻结计划</a> · <a href="m01-fitting/{INPUT_RUN}.record.json.gz">完整记录</a> · <a href="m01-fitting/{INPUT_RUN}.record.journal.jsonl.gz">完整事件</a> · <a href="l3-9-m01-input-summary.json">机器汇总</a> · <a href="l3-8-m01-journal-results.html">上一批</a></p></section></main></html>')
    return ''.join(parts)



COMPILED_RUN='m01-compiled-dev42-20261103-r1'
COMPILED_ARMS=('fast','compiled')
COMPILED_POLICIES={'fast':{'packing':'batch','tokenizer':'fast','attention':'sdpa'},
                   'compiled':{'packing':'batch','tokenizer':'fast','attention':'compiled'}}


def validate_compiled_run(plan,record,journal_path,setup,baseline):
    predictions=validate_journal_run(plan,record,journal_path,baseline,arms=COMPILED_ARMS,
                                   allow_probability_drift=True,attempts_per_case=20)
    c=plan['config']
    if (c['runtimeArms']!=COMPILED_POLICIES or c['hiddenAtol']!=1e-5 or c['hiddenRtol']!=1e-5
            or c['probabilityTolerance']!=1e-6):raise ValueError('compiled policy changed')
    artifact=record['compiledArtifact']
    if artifact['optimizeNumerics'] is not False or artifact['checkTrace'] is not False or artifact['sourceEncoderTensorSha256']!=record['encoder']['tensorSha256']:
        raise ValueError('compiled artifact identity changed')
    if (not artifact['path'].startswith('.local/world-components-logic/compiled/')
            or len(artifact['sha256'])!=64 or len(artifact['graphSha256'])!=64):raise ValueError('invalid local compiled artifact')
    if record['encoderRuntimes']!={'sdpa':{'attentionImplementation':'sdpa','attentionClasses':['BertSdpaSelfAttention']*2}}:raise ValueError('source encoder runtime changed')
    trace=[e for e in setup if e['phase']=='trace_compile']
    if len(trace)!=2 or trace[0]['status']!='running' or trace[1]['status']!='complete' or trace[1]['forwardCallsObserved']!=1:raise ValueError('trace invocation accounting changed')
    if trace[1]!=record['traceSetup'] or trace[1]['artifactSha256']!=artifact['sha256']:raise ValueError('trace artifact mismatch')
    audit=record['compiledHiddenAudit'];source={r['caseId']:r['coverage']['windows'] for r in baseline['featureCoverage'] if r['arm']=='event2'}
    expected=[(r['case']['caseId'],i,w) for r in plan['dataset'] for i,w in enumerate(source[r['case']['caseId']])]
    if len(audit)!=83 or len(expected)!=83:raise ValueError('complete hidden audit coverage changed')
    events=[e for e in setup if e['phase']=='hidden_audit']
    if len(events)!=332 or len(setup)!=334:raise ValueError('setup forward event count changed')
    keys=('inputIds','tokenTypeIds','factIds','factSpans','payloadTokens','totalTokens')
    index=0
    for a,(cid,wi,w) in zip(audit,expected):
        if (a['caseId'],a['windowIndex'],a['tokens'])!=(cid,wi,w['totalTokens']) or not a['allClose']:raise ValueError('hidden comparison failed/missing')
        if not math.isfinite(a['maxAbsoluteHiddenDelta']) or a['maxAbsoluteHiddenDelta']<0:raise ValueError('invalid hidden delta')
        hashes=[]
        for arm in COMPILED_ARMS:
            start,end=events[index*2:index*2+2]
            for e in (start,end):
                if (e['arm'],e['caseId'],e['windowIndex'],e['forwardIndex'])!=(arm,cid,wi,index):raise ValueError('setup forward identity changed')
                if {k:e['window'][k] for k in keys}!={k:w[k] for k in keys}:raise ValueError('setup input changed')
            if start['status']!='running' or end['status']!='complete':raise ValueError('incomplete setup forward')
            if a['inputSha256']!=shared.digest(end['window']):raise ValueError('hidden audit input digest changed')
            hashes.append(end['hiddenSha256']);index+=1
        if a['exact']!=(hashes[0]==hashes[1]) or (a['exact'] and a['maxAbsoluteHiddenDelta']!=0):raise ValueError('hidden exactness misreported')
    return predictions


def build_compiled():
    pp=DATA/(COMPILED_RUN+'.plan.json');rp=DATA/(COMPILED_RUN+'.record.json.gz')
    jp=DATA/(COMPILED_RUN+'.record.journal.jsonl.gz');sp=DATA/(COMPILED_RUN+'.record.setup.jsonl.gz')
    plan=json.loads(pp.read_bytes());record=read_archive(rp);baseline=read_archive(JOURNAL_BASE_RECORD)
    journal=gzip.decompress(jp.read_bytes());setup_raw=gzip.decompress(sp.read_bytes())
    if (record['planSha256']!=sha256_file(pp) or record['journalRecovery']['sha256']!=hashlib.sha256(journal).hexdigest()
            or record['setupEventsSha256']!=hashlib.sha256(setup_raw).hexdigest()):raise ValueError('compiled evidence digest mismatch')
    if plan['baseline']['planSha256']!=sha256_file(JOURNAL_BASE_PLAN) or plan['baseline']['recordSha256']!=sha256_file(JOURNAL_BASE_RECORD):raise ValueError('original model evidence changed')
    for name,h in plan['code'].items():verify_event_source(name,h)
    if sha256_file(ROOT/plan['protocolPath'])!=plan['protocolSha256']:raise ValueError('compiled protocol changed')
    setup=[json.loads(line) for line in setup_raw.splitlines() if line.strip()]
    predictions=validate_compiled_run(plan,record,jp,setup,baseline);timing=[];comparisons={};qualities={}
    for arm in COMPILED_ARMS:
        selected=[a for a in record['attempts'] if a['arm']==arm]
        comparisons[arm]=compare_probabilities(selected,predictions,1e-6,arm=='fast');rows=[]
        for case in plan['cases']:
            attempts=[a for a in selected if a['caseId']==case['caseId']];values=sorted(a['elapsedIncludingTelemetryMs'] for a in attempts)
            a=attempts[0];rows.append({**predictions[a['caseId']],'decoded':a['decoded'],'probabilities':a['probabilities']})
            parts={k:statistics.mean(a['coverage']['timing'][k] for a in attempts) for k in attempts[0]['coverage']['timing']}
            parts.update({k:statistics.mean(a[k] for a in attempts) for k in ('headMs','startJournalMs','snapshotStartMs','resultJournalMs','snapshotEndMs','telemetryJournalMs')})
            parts['otherMs']=statistics.mean(values)-sum(parts.values())
            timing.append({'arm':arm,'caseId':case['caseId'],'observations':20,'p50Ms':statistics.median(values),
                'p95Ms':values[18],'maxMs':max(values),'meanMs':statistics.mean(values),'componentsMeanMs':parts,
                'over50msObservations':sum(v>50 for v in values),
                'local50ms':'fail' if max(values)>50 else 'within_budget_observed_workload_only'})
        qualities[arm]=quality(rows)
    run={'runId':COMPILED_RUN,'quality':qualities,'timing':timing,'comparisons':comparisons,
         'trainingSteps':0,'timedInferenceItems':160,'businessForwardWindows':640,'journalEvents':1761,
         'setupForwardCalls':167,'setupHiddenWindows':83,'allHiddenOutputsExact':all(r['exact'] for r in record['compiledHiddenAudit']),
         'encoder':record['encoder'],'headParameters':record['headParameters'],'checkpoint':record['checkpoint'],
         'weightsUnchanged':True,'compiledArtifact':record['compiledArtifact'],'supervisor':record['supervisor'],
         'preparationStages':[{k:s[k] for k in ('stage','status','elapsedMs')} for s in record['stages']],
         'timingScope':'warm preloaded inference incl per-item journals; setup separate; final write in process wall; supervisor replay unmeasured'}
    summary={'schema':'jity-d-compiled-summary-v1','date':'2026-11-03','scope':'frozen_checkpoint_exposed_development_compilation_probe',
        'formalEvaluationAllowed':False,'semanticQualityApproved':False,'fullRequest500msStatus':'unverified',
        'newIndependentTrainingGroups':0,'round1TrainingQuota':0,'runs':[run],
        'archives':[{'path':str(p.relative_to(ROOT)),'gzipSha256':sha256_file(p),
            'rawSha256':hashlib.sha256(gzip.decompress(p.read_bytes())).hexdigest()} for p in (rp,jp,sp)]}
    return summary,{ART/'l3-10-m01-compiled-summary.json':(json.dumps(summary,ensure_ascii=False,indent=2)+'\n').encode(),
                    ART/'l3-10-m01-compiled-results.html':render_compiled(summary,record).encode()}


def render_compiled(summary,record):
    e=lambda x:html.escape(str(x));run=summary['runs'][0]
    parts=['''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>L3 编码计算图对比</title><style>body{margin:0;background:#f4f6f8;color:#20313e;font:16px/1.7 system-ui}main{max-width:1100px;margin:auto;padding:24px}section{background:white;padding:22px;border-radius:12px;margin:20px 0}table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:10px;text-align:left;border-bottom:1px solid #ddd}.scroll{overflow:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere}.bad{color:#a7352e}h1{font-size:28px}</style><main><p>D / L3 · 2026-11-03 · 固定模型的执行试验</p><h1>提前整理成计算图，能再快多少？</h1><p>原模型和判断头不变、训练0步；完整资料和所有人物保留。两种执行方式各在4道旧开发题上重复20次，共160次业务推理。</p><section><h2>结果：只快约1毫秒，仍未达标</h2><p>转换前后83个核对窗口的完整隐藏输出完全相同，160次业务推理的概率与原两层版逐值一致，行动/目标判断不变。但计算图的每项中位仍约53–57ms，全部80次均超过50ms，当前不能据此验收。</p><p class="bad">这条转换路线收益有限。全部原始观测保留，下一步需继续研究更小的执行表示或任务/模型拆分；独立新题质量、生成协同和完整500毫秒计算仍未验证。</p></section><section><h2>同一批完整单项计时</h2><div class="scroll"><table><tr><th>题目</th><th>原执行p50/p95/最大ms</th><th>计算图p50/p95/最大ms</th><th>计算图超过50ms</th></tr>''']
    for cid in sorted({r['caseId'] for r in run['timing']}):
        a=next(t for t in run['timing'] if t['arm']=='fast' and t['caseId']==cid)
        b=next(t for t in run['timing'] if t['arm']=='compiled' and t['caseId']==cid)
        parts.append(f'<tr><td>{e(cid)}</td><td>{a["p50Ms"]:.2f}/{a["p95Ms"]:.2f}/{a["maxMs"]:.2f}</td><td>{b["p50Ms"]:.2f}/{b["p95Ms"]:.2f}/{b["maxMs"]:.2f}</td><td>{b["over50msObservations"]}/20</td></tr>')
    parts.append('</table></div><p>原执行有一次105.70ms观测，原样保留；p95不能隐藏超时。每项从输入准备前计到结果/尾部遥测写入完成，包含计算图输入检查；转换/加载/核对属于单列准备阶段。批末汇总在子进程wall中，监督器重放耗时未测。</p></section><section><h2>转换时做了哪些检查？</h2><p>一次trace前向、20组完整83窗口×两个方案共166次核对前向，总计167次准备前向另行记账。转换/保存/重载约136ms，完整核对约2.22秒；没有把准备时间写成0。实际转换图保存在D本地忽略目录，按原源编码器SHA、文件和图SHA识别。</p><p>图只支持CPU、单份输入、完整无padding窗口，使用前检查形状/类型/词表/掩码。未覆盖的输入明确拒绝。原池化与判断头保持同一计算；不升级为浏览器支持或游戏恢复验收。</p><p>仍只有4个反复使用的开发场景，重复20次只扩展延迟观察，不能扩称20倍独立新题或语义通过。行动描述、反应、共同结果和完整500ms均待验证。</p></section>')
    parts.append(f'<section><details><summary>模型/计算图身份、准备耗时及全部分项</summary><pre>{e(json.dumps(run,ensure_ascii=False,indent=2))}</pre></details><details><summary>查看全部160次原始概率与计时</summary><pre>{e(json.dumps([{k:a[k] for k in ("arm","caseId","repeat","probabilities","decoded","elapsedIncludingTelemetryMs")} for a in record["attempts"]],ensure_ascii=False,indent=2))}</pre></details><p><a href="m01-fitting/{COMPILED_RUN}.plan.json">冻结计划</a> · <a href="m01-fitting/{COMPILED_RUN}.record.json.gz">完整记录</a> · <a href="m01-fitting/{COMPILED_RUN}.record.journal.jsonl.gz">业务事件</a> · <a href="m01-fitting/{COMPILED_RUN}.record.setup.jsonl.gz">全部准备前向</a> · <a href="l3-10-m01-compiled-summary.json">机器汇总</a> · <a href="l3-9-m01-input-results.html">上一批</a></p></section></main></html>')
    return ''.join(parts)



# Three-stage diagnostic: audit saved bytes only, no model loading or generation.
CHAIN_PREFIX='action-chain-dev42-20261104-'
CHAIN_CASES=('dev-d02-01','dev-d02-03','dev-d02-05','dev-d02-07')
CHAIN_NOTES={
 'dev-d02-01':'待执行的推门/交钥匙命令；生成应是动作尝试。',
 'dev-d02-03':'六米检修井无跨越设施；应skip，不生成文字、不分析目标。',
 'dev-d02-05':'旧命令已消费；当前任务是保护纸卷免于漏水。',
 'dev-d02-07':'当前NPC p2须处理滑向桌边的秤盘，不能代替p3核对粮袋。'}
CHAIN_TEXT_OBSERVATIONS={
 'r1':{'已消费或过期输入只作背景,不再执行','请只概括当前人物p1接下来尝试的一个动作;已消费或过期输入只作背景','请只概括当前人物p2接下来尝试的一个动作;已消费或过期输入只作背景'},
 'r2':{'程青(甲)接下来打算怎样完成眼前的任务','纪遥(甲)接下来打算怎样完成眼前的任务','外貌','当前人物资料:{"共用文本":[],"格式":"无损表格1'},
 'r3':{'打开侧门，进入值班室交钥匙。','拿起纸卷箱，递给管理员。','核对粮袋封口'}}


def validate_chain_run(plan,record,journal_path,version,baseline):
    import copy
    import experiment
    from action_chain import target_case,instruction_prompt
    from lab import decode_output
    from run_pilot import digest
    if (tuple(c['caseId'] for c in plan['cases'])!=CHAIN_CASES or digest(plan['cases'])!=plan['casesSha256']
            or digest(plan['config'])!=plan['configSha256']):raise ValueError('chain case/config identity mismatch')
    expected_arms=['instruct'] if version=='r3' else ['qa','summary']
    expected_repeats=1 if version=='r3' else 3
    expected_parameters={'m01':7120384,**({'generator':494032768} if version=='r3' else {'m02':77440384})}
    if (plan['arms']!=expected_arms or plan['config']['attemptsPerCase']!=expected_repeats
            or record['modelParameters']!=expected_parameters or record['headParameters']!=180418):raise ValueError('chain model/slot identity mismatch')
    for item in (plan,record):
        if item['formalEvaluationAllowed'] is not False:raise ValueError('formal evaluation scope widened')
    if (plan['newIndependentTrainingGroups']!=0 or plan['round1TrainingQuota']!=0 or record['trainingSteps']!=0
            or record['fullRequestMeasured'] is not False or record['semanticQualityApproved'] is not False
            or not record['modelWeightsUnchanged'] or not record['headsUnchanged']):raise ValueError('chain authority/scope drift')
    if plan['performancePolicy']!={'effectiveDate':'2026-11-04','localHardLimitMs':None,'localReferenceMs':50,'fullNonNarrativeTargetMs':500,'fullRequestMeasured':False}:raise ValueError('performance policy drift')
    key=lambda a:(a['arm'],a['caseId'],a['repeat'])
    slots=experiment.planned_slots(plan,plan['arms'])
    if [key(a) for a in record['attempts']]!=[key(s) for s in slots] or record['unexecutedAttempts']!=0:raise ValueError('chain attempt count/order mismatch')
    replay=copy.deepcopy(record);experiment.reconcile_journal(replay,journal_path,'report_read_only_audit')
    for k in ('attempts','attemptSlots','forwardAttempts','journalRecovery'):
        if replay[k]!=record[k]:raise ValueError('chain journal reconstruction mismatch: '+k)
    if record['journalRecovery']['partialTailBytes'] or record['journalRecovery']['modelCallsDuringReplay']!=0:raise ValueError('chain incomplete journal')
    if record['status']!='diagnostic_completed' or record['failedChains']!=0 or record['completedChains']!=len(slots):raise ValueError('chain completion changed')
    if (record['actualRuntime']['threads']!=1 or record['actualRuntime']['interopThreads']!=1
            or record['actualRuntime']['device']!='cpu' or record['supervisor']['stopReason'] is not None
            or record['supervisor']['exitCode']!=0):raise ValueError('chain execution policy changed')
    if record['supervisor']['observedPeakResidentMiB']>plan['config']['maxResidentMiB'] or record['supervisor']['wallMs']>plan['config']['processWallSeconds']*1000:raise ValueError('chain resource violation')
    previous={x['caseId']:x for x in baseline['fitAndDevelopmentPredictions'] if x['arm']=='event2'}
    cases={c['caseId']:c for c in plan['cases']};generated=set();decoder_calls=0;step_windows=0;skip=0
    for a in record['attempts']:
        c=cases[a['caseId']];decision=a['decision'];checkpoints=a['checkpoints']
        if a['status']!='complete' or a['fullRequestMeasured'] is not False:raise ValueError('chain incomplete/scope mismatch')
        if (decision['probabilities']!=previous[c['caseId']]['probabilities'] or decision['decoded']!=previous[c['caseId']]['decoded']):raise ValueError('original M01 decision changed')
        validate_coverage(c,decision['coverage'],'shared')
        def cp(name):return [x['payload'] for x in checkpoints if x['name']==name]
        if cp('decision_saved')!=[decision]:raise ValueError('decision checkpoint missing')
        windows=[w for w in record['forwardAttempts'] if key(w)==key(a)]
        def match_windows(phase,expected):
            observed=[w for w in windows if w['phase']==phase]
            if len(observed)!=len(expected):raise ValueError('chain window denominator mismatch')
            for event,w in zip(observed,expected):
                if event['status']!='complete' or any(event[k]!=w[k] for k in ('inputIds','tokenTypeIds','factIds','factSpans','totalTokens')):raise ValueError('chain window payload mismatch')
            return len(observed)
        step_windows+=match_windows('decision',decision['coverage']['windows'])
        if decision['decoded']['kind']=='skip':
            skip+=1
            if ('generation' in a or 'targets' in a or cp('generation_started') or cp('candidate_frozen_for_diagnostic')
                    or len(windows)!=len(decision['coverage']['windows']) or [s['step'] for s in a['steps']]!=['decision']):raise ValueError('skip unexpectedly invoked downstream')
            continue
        g=a['generation'];raw=g['raw'];generated.add(raw)
        if (not g['finishedWithEos'] or not raw.strip() or len(raw)>240 or g['rawUtf8Sha256']!=hashlib.sha256(raw.encode()).hexdigest()
                or g['parsed']!=decode_output('D02',json.dumps({'kind':'act','text':raw}),c)
                or g['semanticReview']!='pending_not_approved'):raise ValueError('generated candidate bytes/schema changed')
        if cp('generation_output')!=[g if 'parsed' not in g else {k:v for k,v in g.items() if k!='parsed'}] or cp('generated_candidate')!=[g]:raise ValueError('generation checkpoint mismatch')
        calls=g['decoderForwardAttempts'];decoder_calls+=calls
        if cp('decoder_step_started')!=[{'step':i} for i in range(1,calls+1)] or cp('generation_settled')[0]['decoderForwardAttempts']!=calls:raise ValueError('decoder attempt count mismatch')
        if version=='r3':
            context=g['context'];messages,value=instruction_prompt(c)
            if (context['sourceInput']!=value or context['sourceInputSha256']!=digest(value) or context['messages']!=messages
                    or context['inputTokens']!=len(context['inputTokenIds']) or not 0<context['inputTokens']<=4096
                    or cp('generation_started')!=[context] or calls!=len(g['outputTokenIds'])
                    or any(w['phase']=='generation' for w in windows)):raise ValueError('instruction context/forward mismatch')
        else:
            frames=g['frames'];facts=frames['factRecords']
            if (restore(facts)!=c['input'] or frames['inputSha256']!=digest(c['input']) or frames['factSha256']!=digest(facts)
                    or [i for w in frames['windows'] for i in w['factIds']]!=list(range(len(facts)))
                    or any(w['totalTokens']!=len(w['inputIds']) or w['totalTokens']>512 for w in frames['windows'])
                    or g['memoryTokens']!=sum(w['totalTokens'] for w in frames['windows']) or calls!=len(g['outputTokenIds'])-1):raise ValueError('T5 full memory/forward mismatch')
            started=cp('generation_started')
            if len(started)!=1 or started[0]['frames']!=frames or started[0]['memoryTokens']!=g['memoryTokens']:raise ValueError('T5 memory checkpoint mismatch')
            step_windows+=match_windows('generation',frames['windows'])
        target=a['targets'];child=target_case(c,raw)
        if target['case']!=child:raise ValueError('generated text/roster not faithfully handed over')
        if cp('candidate_frozen_for_diagnostic')!=[{'actionText':raw,'utf8Sha256':g['rawUtf8Sha256'],'targetCase':child,'semanticApproved':False}]:raise ValueError('diagnostic freeze changed')
        validate_coverage(child,target['coverage'],'shared')
        selected=[p for p,value in zip(child['input']['candidateIds'],target['probabilities']) if value>=.5]
        ids=[x['targetId'] for x in target['decoded']['targets']]
        if ids!=selected or len(target['probabilities'])!=len(child['input']['candidateIds']) or target['semanticReview']!='pending_not_approved':raise ValueError('target output/probability mismatch')
        decode_output('D03',json.dumps(target['decoded']),child)
        step_windows+=match_windows('targets',target['coverage']['windows'])
        if [s['step'] for s in a['steps']]!=['decision','generation','targets'] or any(s['status']!='complete' for s in a['steps']):raise ValueError('chain stage mismatch')
        if sum(s['elapsedMs'] for s in a['steps'])>a['elapsedIncludingTelemetryMs'] or a['elapsedIncludingTelemetryMs']<a['elapsedThroughResultMs']:raise ValueError('chain timing omitted work')
    if generated!=CHAIN_TEXT_OBSERVATIONS[version] or step_windows!=len(record['forwardAttempts']):raise ValueError('observed output/forward ledger changed')
    return {'skipNoDownstream':skip,'generationCalls':len(slots)-skip,'targetCalls':len(slots)-skip,
            'encoderForwardWindows':step_windows,'decoderForwardAttempts':decoder_calls}


def build_chain():
    import tempfile
    runs=[];records=[];archives=[];baseline=read_archive(DATA/'m01-event-dev42-20261102-r1.record.json.gz')
    for version in ('r1','r2','r3'):
        run_id=CHAIN_PREFIX+version;pp=DATA/(run_id+'.plan.json');rp=DATA/(run_id+'.record.json.gz');jp=DATA/(run_id+'.record.journal.jsonl.gz')
        plan=json.loads(pp.read_bytes());record=read_archive(rp);raw=gzip.decompress(jp.read_bytes())
        if record['planSha256']!=sha256_file(pp) or record['journalRecovery']['sha256']!=hashlib.sha256(raw).hexdigest():raise ValueError('chain plan/journal digest mismatch')
        if plan['baseline']!=shared.baseline_identity():raise ValueError('original fixed checkpoint evidence changed')
        for name,expected in plan['code'].items():
            snapshot=DATA/f'code/action_chain-{version}.py'
            if name.endswith('/action_chain.py') and version in ('r1','r2'):
                if sha256_file(snapshot)!=expected:raise ValueError('historical chain source changed')
            else:verify_event_source(name,expected)
        if sha256_file(ROOT/plan['protocolPath'])!=plan['protocolSha256']:raise ValueError('chain protocol changed')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'events.jsonl';path.write_bytes(raw)
            counts=validate_chain_run(plan,record,path,version,baseline)
        timing=[]
        for arm in plan['arms']:
            for c in plan['cases']:
                rows=[a for a in record['attempts'] if a['arm']==arm and a['caseId']==c['caseId']]
                times=[a['elapsedIncludingTelemetryMs'] for a in rows]
                timing.append({'arm':arm,'caseId':c['caseId'],'observations':len(rows),'p50Ms':statistics.median(times),'maxMs':max(times),
                    'over500msObservations':sum(v>500 for v in times),'stepsMeanMs':{s['step']:statistics.mean(next(x['elapsedMs'] for x in a['steps'] if x['step']==s['step']) for a in rows) for s in rows[0]['steps']}})
        quality_observation={'decisionRegressionMatched':len(record['attempts']),'generatedSemanticFailuresObserved':2 if version=='r3' else counts['generationCalls'],
            'generatedPromptEchoFailuresObserved':0 if version=='r3' else counts['generationCalls'],
            'generatedTaskOrActorFailuresObserved':2 if version=='r3' else 0,'generatedPlausibleCandidatesPendingReview':1 if version=='r3' else 0,
            'targetSemanticQuality':'unverified_dynamic_candidates_all_empty_upstream_invalid_or_pending','formalSemanticPass':False}
        runs.append({'runId':run_id,'generator':'M03 Qwen2.5-0.5B-Instruct FP32' if version=='r3' else 'M02 T5-77M',
            'completedEngineeringChains':len(record['attempts']),'counts':counts,'quality':quality_observation,
            'modelParameters':record['modelParameters'],'headParameters':record['headParameters'],'trainingSteps':0,'weightsAndHeadsUnchanged':True,
            'supervisor':record['supervisor'],'preparationStages':[{k:s[k] for k in ('stage','elapsedMs','status')} for s in record['stages']],
            'timing':timing,'local50msHardGate':False,'fullRequestMeasured':False})
        records.append(record)
        for p in (rp,jp):archives.append({'path':str(p.relative_to(ROOT)),'gzipSha256':sha256_file(p),'rawSha256':hashlib.sha256(gzip.decompress(p.read_bytes())).hexdigest()})
    summary={'schema':'jity-d-action-chain-summary-v1','date':'2026-11-04','scope':'old_exposed_development_three_stage_diagnostic',
        'formalEvaluationAllowed':False,'semanticQualityApproved':False,'fullRequest500msStatus':'unverified','local50msHardGate':False,
        'fullNonNarrativeTargetMs':500,'newIndependentTrainingGroups':0,'round1TrainingQuota':0,'runs':runs,'archives':archives}
    return summary,{ART/'l3-11-action-chain-summary.json':(json.dumps(summary,ensure_ascii=False,indent=2)+'\n').encode(),
                    ART/'l3-11-action-chain-results.html':render_chain(summary,records).encode()}


def render_chain(summary,records):
    e=lambda x:html.escape(str(x))
    parts=['''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>L3 行动三步协作实测</title><style>body{margin:0;background:#f4f6f8;color:#20313e;font:16px/1.7 system-ui}main{max-width:1100px;margin:auto;padding:24px}section{background:white;padding:22px;border-radius:12px;margin:20px 0}table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:10px;text-align:left;border-bottom:1px solid #ddd}.scroll{overflow:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere}.bad{color:#a7352e}h1{font-size:28px}small{color:#526472}</style><main><p>D / L3 · 2026-11-04 · 离线诊断</p><h1>先判断要不要动，再写动作，最后找牵连人物</h1><section><h2>流程跑通了，模型方案还不能验收</h2><p>程序真实串起了三步：M01判断行动/跳过 → 生成模型写动作 → 原文交回M01分析目标。共52条尝试，39次实际生成，39次目标分析；13次skip均跳过后两步。没有手写动作代替模型。</p><p>前两批77M模型共36次输出都在重复提示、问题或字段。改用494M指令模型后，3次生成中1条符合眼前任务的基本方向，另外2条有任务/人物错误；这只是实现者观察，尚无正式语义通过。所有目标输出均为空，不能据此算目标正确。</p><p class="bad">指令模型的3条生成链耗时1322–1558ms，已经超过完整500ms目标；只测了三步，完整非叙事还未测。50ms现只作参考，不再硬性否决。没有通过L3，也未接入游戏。</p></section><section><h2>指令模型：逐条看真实答案</h2><div class="scroll"><table><tr><th>场景/要求</th><th>真实输出</th><th>观察</th><th>三步总计ms</th></tr>''']
    observations={'dev-d02-01':'符合推门/交钥匙基本方向；待复核，未签通过。','dev-d02-03':'M01输出skip；后两步未调用。','dev-d02-05':'混入旧命令的“管理员”，未明确保护纸卷免于漏水。','dev-d02-07':'写了p3的任务，当前p2保管秤盘的任务遗漏。'}
    for a in records[-1]['attempts']:
        parts.append(f'<tr><td>{e(a["caseId"])}<br>{e(CHAIN_NOTES[a["caseId"]])}</td><td>{e(a.get("generation",{}).get("raw","未调用生成"))}</td><td>{e(observations[a["caseId"]])}</td><td>{a["elapsedIncludingTelemetryMs"]:.2f}</td></tr>')
    parts.append('</table></div><p>“空目标”是模型实际输出，尚未形成按生成原文审过的目标真值，不能算正确。没有生成的skip题也没有伪造空目标。</p></section><section><h2>慢在哪里？</h2><p>指令模型每条文字生成约1209–1425ms，行动判断约52–73ms、目标约55–56ms；文字生成是主要瓶颈。三条仅7–11次生成前向，输入预填充也在其中。加载和文件校验另记准备成本，不塞进热请求，也不填为0。</p><p>下一步先修正当前人物/任务的输入定位，保留完整世界作为共同记忆，复测是否仍混淆；同时把“决定具体动作”和“表达成句”进一步拆开，研究更小模型/短输出或经过独立数据训练的专用头。未达500ms的本配置不能直接定为最终方案。</p></section>')
    for r,record in zip(summary['runs'],records):
        parts.append(f'<section><h2>{e(r["runId"])} · {e(r["generator"])}</h2><p>{r["completedEngineeringChains"]}条工程链完成；CPU单线程、训练0步，骨干与头前后哈希不变。进程{r["supervisor"]["wallMs"]/1000:.2f}秒，采样RSS {r["supervisor"]["observedPeakResidentMiB"]:.2f}MiB。M03单批RSS上限4096MiB；M02单批2048MiB。</p><div class="scroll"><table><tr><th>格式/题目</th><th>次数</th><th>总计中位/最大ms</th><th>超过500ms</th></tr>')
        for t in r['timing']:parts.append(f'<tr><td>{e(t["arm"])} / {e(t["caseId"])}</td><td>{t["observations"]}</td><td>{t["p50Ms"]:.2f} / {t["maxMs"]:.2f}</td><td>{t["over500msObservations"]}</td></tr>')
        outputs=[{k:a[k] for k in ('arm','caseId','repeat','decision','generation','targets','steps','elapsedIncludingTelemetryMs') if k in a} for a in record['attempts']]
        # Coverage/token evidence remains in archives; keep this page easy to read.
        for a in outputs:
            for k in ('decision','targets'):
                if k in a:a[k]={x:v for x,v in a[k].items() if x not in ('coverage','case')}
            if 'generation' in a:a['generation']={x:v for x,v in a['generation'].items() if x not in ('frames','context','outputTokenIds')}
        parts.append(f'</table></div><details><summary>全部真实答案、概率与分步耗时</summary><pre>{e(json.dumps(outputs,ensure_ascii=False,indent=2))}</pre></details><details><summary>模型规模、调用数、准备开销和质量范围</summary><pre>{e(json.dumps(r,ensure_ascii=False,indent=2))}</pre></details><p><a href="m01-fitting/{r["runId"]}.plan.json">冻结计划</a> · <a href="m01-fitting/{r["runId"]}.record.json.gz">完整记录</a> · <a href="m01-fitting/{r["runId"]}.record.journal.jsonl.gz">完整事件</a></p></section>')
    parts.append('<section><h2>本次范围</h2><p>仍使用4道已公开旧题：01/03原为拟合、05/07原为保留开发，重复次数不当新题。r1协议“0107曾参与拟合”为笔误，冻结原件保留，实际角色依原event2记录。新90组未用、训练0步。来源核验与独立复核尚待补齐；反应、共同结果、状态变化、浏览器及生产接线未测。离线冻结checkpoint只保存候选原文，semanticApproved=false，不是A服务采纳。</p><p>M01为两层7.12M编码器+两判断头；M02为77.44M T5，M03为494.03M Qwen2.5指令模型（固定BF16源文件、FP32运行）。生成模型均本地，权重与依赖不入库。日志包含原始文字及实际生成前向，中断重放只恢复台账，不重采样。</p><p>计时从本条输入准备前直到最终遥测写入完成，含阶段交接、flush/fsync；批末汇总在进程wall，监督器退出后重放未单独计时。没有把不同批次数字相加成全请求成绩。</p><p><a href="l3-11-action-chain-summary.json">机器汇总与归档SHA</a> · <a href="l3-10-m01-compiled-results.html">上一批历史结果</a></p></section></main></html>')
    return ''.join(parts)


def main():
    p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group(required=True)
    m.add_argument('--check',action='store_true');m.add_argument('--write-new',action='store_true')
    flavor=p.add_mutually_exclusive_group();flavor.add_argument('--event',action='store_true');flavor.add_argument('--journal',action='store_true');flavor.add_argument('--input',action='store_true');flavor.add_argument('--compiled',action='store_true');flavor.add_argument('--chain',action='store_true');a=p.parse_args()
    summary,files=build_chain() if a.chain else build_compiled() if a.compiled else build_input() if a.input else build_journal() if a.journal else build_event() if a.event else build()
    for path,raw in files.items():
        if path.exists() and path.read_bytes()!=raw:raise ValueError('report differs; preserve earlier version')
        if a.check and not path.exists():raise ValueError('report missing')
    if a.write_new:
        for path,raw in files.items():
            if not path.exists():
                with path.open('xb') as f:f.write(raw)
    print(json.dumps({k:summary[k] for k in ('scope','formalEvaluationAllowed','fullRequest500msStatus')},ensure_ascii=False))


if __name__=='__main__':main()
