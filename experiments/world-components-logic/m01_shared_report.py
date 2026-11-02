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
    for arm in shared.ARMS:
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
    expected={(arm,cid,i) for arm in shared.ARMS for cid in cases for i in range(5)}
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


def main():
    p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group(required=True)
    m.add_argument('--check',action='store_true');m.add_argument('--write-new',action='store_true');a=p.parse_args()
    summary,files=build()
    for path,raw in files.items():
        if path.exists() and path.read_bytes()!=raw:raise ValueError('report differs; preserve earlier version')
        if a.check and not path.exists():raise ValueError('report missing')
    if a.write_new:
        for path,raw in files.items():
            if not path.exists():
                with path.open('xb') as f:f.write(raw)
    print(json.dumps({k:summary[k] for k in ('scope','formalEvaluationAllowed','fullRequest500msStatus')},ensure_ascii=False))


if __name__=='__main__':main()
