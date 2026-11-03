"""Rebuild a read-only report from archived M01 fitting/inference evidence."""
from __future__ import annotations

import argparse
from collections import Counter
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

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/'artifacts/world-components-logic'
DATA=ART/'m01-fitting'
FIT='m01-fit-dev42-20261102-r1'
INFER='m01-infer-dev42-20261102-r3'


def raw_archive(name):return gzip.decompress((DATA/(name+'.gz')).read_bytes())
def read_archive(name):return json.loads(raw_archive(name))
def same(label,decoded,task):return (decoded['kind']==label if task=='D02' else {x['targetId'] for x in decoded['targets']}==set(label))


def verify_fit_evidence(plan,fit_record_path,fit_plan_path,fitted):
    if plan['fitRecord']['path']!=str(fit_record_path.relative_to(ROOT)) or plan['fitRecord']['sha256']!=sha256_file(fit_record_path):raise ValueError('frozen fitting archive identity mismatch')
    if plan['fitPlanSha256']!=fitted['planSha256'] or plan['fitPlanSha256']!=sha256_file(fit_plan_path):raise ValueError('frozen fitting plan identity mismatch')
    if plan['trainedHeadSha256']!=fitted['trainedHeadSha256']:raise ValueError('trained head identity mismatch')


def summarize(attempts):
    result=[]
    for cid in sorted({a['caseId'] for a in attempts}):
        rows=[a for a in attempts if a['caseId']==cid];times=sorted(a['elapsedMs'] for a in rows)
        result.append({'caseId':cid,'task':rows[0]['task'],'n':len(rows),'p50Ms':statistics.median(times),
                       'p95Ms':times[math.ceil(.95*len(times))-1],'maxMs':max(times),
                       'windowsPerItem':sum(len(c['windows']) for c in rows[0]['coverage']),
                       'candidateCount':len(rows[0]['coverage']),
                       'maxWindowTokens':max(w['totalTokens'] for c in rows[0]['coverage'] for w in c['windows']),
                       'local50ms':'fail' if any(t>50 for t in times) else 'unverified_insufficient_n',
                       'predictions':[r['decoded'] for r in rows]})
    return result


def build():
    fp=DATA/(FIT+'.plan.json');ip=DATA/(INFER+'.plan.json')
    fitplan=json.loads(fp.read_text(encoding='utf-8'));plan=json.loads(ip.read_text(encoding='utf-8'))
    fitted=read_archive(FIT+'.record.json');record=read_archive(INFER+'.record.json')
    verify_fit_evidence(plan,DATA/(FIT+'.record.json.gz'),fp,fitted)
    if fitted['planSha256']!=sha256_file(fp) or record['planSha256']!=sha256_file(ip):raise ValueError('plan/record mismatch')
    snapshot=DATA/'code/m01_probe-fit-r1.py'
    if sha256_file(snapshot)!=fitplan['code']['experiments/world-components-logic/m01_probe.py']:raise ValueError('fitting source snapshot mismatch')
    for name,h in plan['code'].items():
        if sha256_file(ROOT/name)==h:continue
        raw=subprocess.check_output(['git','show','f3c5bbfbad7fc0110b67666e31c4dd36e6f9698d:'+name],cwd=ROOT)
        if hashlib.sha256(raw).hexdigest()!=h:raise ValueError('executed inference code mismatch')
    if fitted['checkpoint']!=plan['checkpoint'] or not fitted['encoderUnchanged']:raise ValueError('trained identity mismatch')
    events_raw=raw_archive(INFER+'.record.windows.jsonl')
    if hashlib.sha256(events_raw).hexdigest()!=record['windowEventsSha256']:raise ValueError('window event stream mismatch')
    events=[json.loads(x) for x in events_raw.splitlines() if x.strip()]
    starts={e['eventId']:e for e in events if e['status']=='running'}
    settles={e['eventId']:e for e in events if e['status']!='running'}
    if len(starts)!=160 or set(starts)!=set(settles) or any(e['status']!='complete' for e in settles.values()):raise ValueError('missing/failed inference forward')
    expected_trace=[(a['caseId'],c['targetId'],i,w) for a in record['attempts'] for c in a['coverage'] for i,w in enumerate(c['windows'])]
    for index,(cid,target,window_index,w) in enumerate(expected_trace):
        event=settles[index]
        if (event['caseId'],event['targetId'],event['windowIndex'])!=(cid,target,window_index):raise ValueError('forward event scope mismatch')
        if any(event[k]!=w[k] for k in ('inputIds','tokenTypeIds','factIds','totalTokens','payloadTokens')):raise ValueError('forward payload mismatch')
    cases={c['caseId']:c for c in plan['cases']};by_label={r['case']['caseId']:r for r in fitplan['dataset']}
    expected={(c,i) for c in cases for i in range(5)}
    if {(a['caseId'],a['repeat']) for a in record['attempts']}!=expected or len(record['attempts'])!=20:raise ValueError('attempt slots mismatch')
    for a in record['attempts']:
        if a['status']!='complete' or a['featureCacheUsed'] is not False:raise ValueError('incomplete/cached inference')
        for c in a['coverage']:
            if canonical_bytes(restore(c['factRecords']))!=canonical_bytes(cases[a['caseId']]['input']):raise ValueError('facts incomplete')
            if [i for w in c['windows'] for i in w['factIds']]!=list(range(len(c['factRecords']))):raise ValueError('window coverage incomplete')
            if any(w['totalTokens']>512 for w in c['windows']):raise ValueError('window overflow')
    quality={}
    for task in ('D02','D03'):
        quality[task]={}
        for role in ('fit','retained_development'):
            rows=[r for r in fitted['fitAndDevelopmentPredictions'] if r['task']==task and r['role']==role]
            quality[task][role]={'matchingSourceGroups':sum(same(r['label'],r['decoded'],task) for r in rows),'sourceGroups':len(rows)}
    for a in record['attempts']:
        original=next(p for p in fitted['fitAndDevelopmentPredictions'] if p['caseId']==a['caseId'])
        if a['decoded']!=original['decoded'] or a['probabilities']!=original['probabilities']:raise ValueError('checkpoint observations changed')
    archives=[]
    for name in (FIT+'.record.json',INFER+'.record.json',INFER+'.record.windows.jsonl'):
        path=DATA/(name+'.gz');raw=raw_archive(name)
        archives.append({'path':str(path.relative_to(ROOT)),'gzipSha256':sha256_file(path),
                         'rawSha256':hashlib.sha256(raw).hexdigest(),'rawBytes':len(raw),
                         'restoreTo':str((DATA/name).relative_to(ROOT))})
    result={'schema':'jity-d-m01-fitting-summary-v1','date':'2026-11-02','scope':'reviewed_development_fitting_probe_only',
       'fitPlanSha256':sha256_file(fp),'inferencePlanSha256':sha256_file(ip),'archives':archives,
       'encoderParameters':fitted['encoderParameters'],'headParameters':fitted['headParameters'],
       'encoderFrozenAndUnchanged':fitted['encoderUnchanged'],'stepsPerHead':{t:len(x) for t,x in fitted['fitLosses'].items()},
       'checkpoint':fitted['checkpoint'],'oldDevelopmentGroupsConsumed':20,'newIndependentTrainingGroups':0,'round1TrainingQuota':0,
       'qualityObservations':quality,'timingBefore':summarize(fitted['attempts']),'timingAfter':summarize(record['attempts']),
       'finalForwardCalls':len(starts),'fitAndDiagnosticForwardCalls':len(fitted['forwardAttempts']),
       'actualRuntime':record['actualRuntime'],'supervisor':record['supervisor'],
       'complete512WindowCoverage':'verified_for_this_probe_not_cross_window_semantic_sufficiency',
       'formalEvaluationAllowed':False,'semanticQualityApproved':False,'fullRequest500msStatus':'unverified',
       'trainedTargetHeadPromotion':'rejected_missing_required_targets',
       'headOutputScope':{'D02':'act_skip_only_no_action_text','D03':'entire_roster_target_set'},
       'nextWork':['Reduce repeated global encoding with a separately registered learned candidate-fusion head; retain complete facts',
                   'Cross-window semantic quality and D03 required-target recall must improve before promotion',
                   'New independent training data and formal calibration still required; round1 is not training data',
                   'D04/D05 generation and real model collaboration remain unfinished']}
    raw=(json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    return result,{ART/'l3-5-m01-summary.json':raw,ART/'l3-5-m01-results.html':render(result,fitted,record,by_label).encode('utf-8')}


def render(summary,fitted,record,labels):
    e=lambda x:html.escape(str(x));names={'D02':'行动判断（仅act/skip）','D03':'目标分析（完整名册）'}
    parts=[f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>L3 小编码器与判断头实测</title><style>body{{margin:0;background:#f4f6f8;color:#20313e;font:16px/1.7 system-ui,sans-serif}}main{{max-width:1100px;margin:auto;padding:24px 18px}}article{{background:white;padding:22px;margin:18px 0;border:1px solid #dce3e8;border-radius:12px}}table{{width:100%;border-collapse:collapse;font-size:14px}}td,th{{padding:10px;text-align:left;border-bottom:1px solid #dde4e8}}.scroll{{overflow:auto}}.bad{{color:#a7352e}}.muted{{color:#667784}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f6f8;padding:12px;font-size:13px}}h1{{font-size:28px}}h2{{font-size:21px}}</style><main><p class="muted">D / 2026-11-02 · 旧开发题拟合探针</p><h1>小编码器、512分窗和两个判断头已经真实运行</h1><p>冻结编码器 {summary['encoderParameters']:,} 参数；两个可学习判断头共 {summary['headParameters']} 参数，每头拟合200步。原输入全部事实保留，每窗不超过512 token。当前路线仍有漏目标和超时问题，尚不可作为可用组件。</p>
<article><h2>这次做了什么</h2><ol><li>下载并验真已登记M01；安全加载编码器，未创建随机pooler。</li><li>将完整输入按原子事实分窗，重建原文核摘要，不截断、不删除人物或任务。</li><li>复用已审开发标签做工程拟合：16来源组拟合、4来源组保留开发；90组完全不进入训练。</li><li>固定训练检查点后单独做20次推理，逐窗追加日志；没有再拟合、改阈值或换题。</li></ol><p>这些旧20组已用于拟合/开发观察，不是新独立训练数据，不再当未见封存资料。每任务保留组仅2个，不能据此推断普遍准确率。</p></article>
<article><h2>判断结果：拟合与保留开发分开</h2><div class="scroll"><table><tr><th>任务</th><th>拟合来源组匹配</th><th>保留开发匹配</th><th>范围</th></tr>''']
    for task in ('D02','D03'):
        q=summary['qualityObservations'][task];a=q['fit'];b=q['retained_development']
        parts.append(f"<tr><td>{names[task]}</td><td>{a['matchingSourceGroups']}/{a['sourceGroups']}</td><td>{b['matchingSourceGroups']}/{b['sourceGroups']}</td><td>{'未生成行动正文' if task=='D02' else '非空集合题漏掉p2、p3'}</td></tr>")
    parts.append('</table></div><p class="bad">D03保留题漏掉必需目标，不能晋升。D02的2/2也不代表完整行动组件通过，固定阈值未做正式校准。</p></article><article><h2>完整判别计时：每题重新分词并执行全部窗口</h2><p>第一轮每个窗口重写累计状态，开销很大；第二轮锁定相同权重，以追加窗口事件保存证据。两轮预测完全相同。数字包含日志开销，不是只量线性头。</p><div class="scroll"><table><tr><th>保留题</th><th>窗口/候选</th><th>首次中位数ms</th><th>独立推理中位数ms</th><th>p95/最大ms</th><th>50ms预算</th></tr>')
    for before,after in zip(summary['timingBefore'],summary['timingAfter']):
        parts.append(f"<tr><td>{e(after['caseId'])}</td><td>{after['windowsPerItem']}窗/{after['candidateCount']}候选</td><td>{before['p50Ms']:.2f}</td><td>{after['p50Ms']:.2f}</td><td>{after['p95Ms']:.2f}/{after['maxMs']:.2f}</td><td class='bad'>未通过</td></tr>")
    parts.append('</table></div><p>D03按三个人物完整目标集合计时，不能用一个候选或一个窗口的速度代替。每题5次，完整D02–D05协同及500ms游戏请求尚未测量；这个编码器判别任务与上一批生成任务不同，不能直接称模型整体更快或更好。</p></article>')
    for cid in sorted({a['caseId'] for a in record['attempts']}):
        row=next(a for a in record['attempts'] if a['caseId']==cid);label=labels[cid]['label']
        observations=[]
        for a in record['attempts']:
            if a['caseId']!=cid:continue
            observations.append({k:a[k] for k in ('repeat','status','elapsedMs','probabilities','decoded','featureCacheUsed')})
            observations[-1]['coverage']=[{'targetId':c['targetId'],'factSha256':c['factSha256'],'fullFactsRestored':c['fullFactsRestored'],
                                          'windowTokens':[w['totalTokens'] for w in c['windows']],
                                          'coveredFacts':sum(len(w['factIds']) for w in c['windows'])} for c in a['coverage']]
        parts.append(f"<article><h2>{e(cid)}</h2><p>原判据：{e(label)}；实际预测：{e(row['decoded'])}</p><pre>原始分数：{e(row['probabilities'])}</pre><p>5次重复预测相同，仍只算一个来源场景。</p><details><summary>查看原完整输入</summary><pre>{e(json.dumps(labels[cid]['case']['input'],ensure_ascii=False,indent=2))}</pre></details><details><summary>查看5次原始分数、耗时和覆盖摘要</summary><pre>{e(json.dumps(observations,ensure_ascii=False,indent=2))}</pre></details><p>完整逐token记录保留在下方无损归档。</p></article>")
    parts.append(f'<article><h2>证据与下一步</h2><p>全部大原始记录使用gzip无损归档，解压字节SHA在汇总中。训练权重留在D本地忽略目录，仓库不包含权重。r2只有准备，未启动，已明确归档其被后续r3替代的状态。</p><p><a href="l3-5-m01-summary.json">机器汇总与归档身份</a> · <a href="m01-fitting/{FIT}.plan.json">拟合计划</a> · <a href="m01-fitting/{INFER}.plan.json">独立推理计划</a></p><p><a href="m01-fitting/{FIT}.record.json.gz">完整拟合记录</a> · <a href="m01-fitting/{INFER}.record.json.gz">完整推理记录</a> · <a href="m01-fitting/{INFER}.record.windows.jsonl.gz">逐窗token原始事件</a></p><p>下一步应减少重复编码并改善候选条件融合，保持全事实覆盖，修复漏目标；再准备独立训练数据和正式校准，接入反应与共同结果。当前仍未完成跨窗语义验证、M01/M02协同、来源核验、浏览器或生产接线。</p></article></main></html>')
    return ''.join(parts)


def main():
    p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group(required=True)
    m.add_argument('--check',action='store_true');m.add_argument('--write-new',action='store_true');a=p.parse_args();s,files=build()
    for path,raw in files.items():
        if path.exists() and path.read_bytes()!=raw:raise ValueError('report version differs')
        if a.check and not path.exists():raise ValueError('report missing')
    if a.write_new:
        for path,raw in files.items():
            if not path.exists():
                with path.open('xb') as f:f.write(raw)
    print(json.dumps({'encoderParameters':s['encoderParameters'],'headParameters':s['headParameters'],'qualityObservations':s['qualityObservations'],'fullRequest500msStatus':s['fullRequest500msStatus']},ensure_ascii=False))


if __name__=='__main__':main()
