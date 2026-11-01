"""Read-only evidence report for four preserved development pilot runs."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import html
import json
import math
from pathlib import Path
import statistics

from lab import canonical_bytes, load_jsonl, sha256_file
from pilot_codec import unpack

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / 'artifacts/world-components-logic'
PILOTS = ART / 'pilots'
PREFIX = 'm02-dev42-20261101-'
CASE_NAMES = {'dev-d02-01': '行动', 'dev-d03-01': '目标', 'dev-d04-01': '反应', 'dev-d05-01': '共同结果'}


def summary(attempts):
    result = []
    for cid in sorted({r['caseId'] for r in attempts}):
        rows = [r for r in attempts if r['caseId'] == cid]
        values = sorted(r['elapsedMs'] for r in rows)
        result.append({'caseId': cid, 'attempts': len(rows), 'inputTokens': rows[0]['inputTokens'],
            'statuses': dict(Counter(r['status'] for r in rows)),
            'structureValid': sum(r.get('structureStatus') == 'valid' for r in rows),
            'p50Ms': statistics.median(values), 'p95Ms': values[math.ceil(.95*len(values))-1],
            'maxMs': max(values), 'localBudgetExceeded': any(v > 50 for v in values),
            'uniqueRawOutputs': list(dict.fromkeys(r['raw'] for r in rows)),
            'performanceSampleStatus': 'insufficient_n_for_formal_acceptance' if len(rows) < 20 else 'needs_full_protocol'})
    return result


def build():
    runs = []
    for revision in ('r1', 'r2', 'r3', 'r4'):
        plan_path = PILOTS / f'{PREFIX}{revision}.plan.json'
        record_path = PILOTS / f'{PREFIX}{revision}.record.json'
        plan, record = json.loads(plan_path.read_text(encoding='utf-8')), json.loads(record_path.read_text(encoding='utf-8'))
        if record['planSha256'] != sha256_file(plan_path):
            raise ValueError('record/plan identity mismatch')
        if len(record['attempts']) != record['plannedAttempts'] or record['unexecutedAttempts'] != 0:
            raise ValueError('pilot has incomplete attempts; report must be revised')
        for a in record['attempts']:
            c = next(c for c in plan['cases'] if c['caseId'] == a['caseId'])
            original = hashlib.sha256(canonical_bytes(c['input'])).hexdigest()
            if original != a['modelInputSha256'] or a['fullRequestMeasured'] is not False:
                raise ValueError('attempt input/full-request scope mismatch')
            if hashlib.sha256(a['prompt'].encode()).hexdigest() != a['promptSha256']:
                raise ValueError('prompt identity mismatch')
            actual = json.loads(a['prompt'].rsplit('\n', 1)[1])
            if plan['config']['serialization'] == 'lossless_chinese_tables_v1': actual = unpack(actual)
            if actual != c['input']: raise ValueError('actual prompt did not preserve the whole stage input')
        if record['generationCalls'] != sum(bool(a.get('generationPerformed')) for a in record['attempts']):
            raise ValueError('generation count mismatch')
        runs.append({'runId': plan['runId'], 'inputLimit': plan['config']['maxInputTokens'],
                     'serialization': plan['config']['serialization'],
                     'planPath': str(plan_path.relative_to(ROOT)), 'planSha256': sha256_file(plan_path),
                     'recordPath': str(record_path.relative_to(ROOT)), 'recordSha256': sha256_file(record_path),
                     'generationCalls': record['generationCalls'], 'status': record['status'],
                     'parameterCount': record['parameterCount'], 'peakResidentMiB': record['peakResidentMiB'],
                     'actualRuntime': record.get('actualRuntime'),
                     'environmentEvidence': 'runtime_reverified_and_import_versions_recorded' if record.get('actualRuntime') else 'preparation_metadata_only_no_retrospective_runtime_attestation',
                     'supervisor': record['supervisor'], 'stages': record['stages'],
                     'tasks': summary(record['attempts'])})
    latest = runs[-1]
    observations = [
        {'caseId': 'dev-d02-01', 'finding': '格式拒绝；输出只是“不能宣布成功”的规则句，没有act/skip结构和行动正文。'},
        {'caseId': 'dev-d03-01', 'finding': '格式拒绝；没有返回目标集合，输出复述禁止事项。'},
        {'caseId': 'dev-d04-01', 'finding': '非空正文结构检查通过，但内容是禁止事项，没有应对冻结威胁的反应行动。'},
        {'caseId': 'dev-d05-01', 'finding': '格式拒绝；没有完整成员结果映射，也没有联合因果结算。'},
    ]
    snapshots = []
    for versions, name in ((['r1'], 'run_pilot-r1.py'), (['r2','r3'], 'run_pilot-r2-r3.py')):
        snapshot = PILOTS/'code'/name
        for version in versions:
            plan = json.loads((PILOTS/f'{PREFIX}{version}.plan.json').read_text(encoding='utf-8'))
            if sha256_file(snapshot) != plan['code']['experiments/world-components-logic/run_pilot.py']:
                raise ValueError('historical runner snapshot does not match its plan')
        snapshots.append({'runs': versions, 'path': str(snapshot.relative_to(ROOT)), 'sha256': sha256_file(snapshot),
                          'restoreTo': 'experiments/world-components-logic/run_pilot.py'})
    report = {'schema': 'jity-d-pilot-summary-v1', 'date': '2026-11-01',
        'scope': 'four_previously_reviewed_development_cases_five_repeats_each_not_formal_screening',
        'runs': runs, 'historicalRunnerSnapshots': snapshots,
        'businessGenerationsTotal': sum(r['generationCalls'] for r in runs),
        'verdict': 'current_M02_zero_shot_configuration_not_usable_on_these_four_cases',
        'assistantDiagnosticObservations': observations,
        'observationScope': 'implementation_author_obvious_failure_triage_not_independent_human_blind_score',
        'sourceIndependence': 'unverified', 'formalEvaluationAllowed': False,
        'semanticQualityApproved': False, 'fullRequestMeasured': False,
        'fullRequest500msStatus': 'unverified', 'local50msStatus': 'failed_on_all_four_tested_tasks',
        'input512Status': 'still_overflow_even_after_lossless_serialization',
        'nextWork': ['512-token complete-coverage splitting remains unfinished; no input truncation accepted',
                     'Decompose learned decisions from short generation; prepare/train independent M01 business heads',
                     'Register any training or task-adapted M02 arm before running; do not use evaluation groups for training',
                     'Then compare actual collaboration and dynamic chain, preserving program authority and total timing'],
        'notTested': ['trained M01 heads', 'M01/M02 collaboration', 'dynamic short-chain runner',
                      'full D06-D08 request', 'browser integration', 'production integration', 'independent formal semantic evaluation']}
    raw = (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode()
    return report, {ART/'l3-4-pilot-summary.json': raw, ART/'l3-4-pilot-results.html': render(report).encode('utf-8')}


def render(report):
    e = lambda value: html.escape(str(value))
    latest = report['runs'][-1]
    title = 'L3 第一批真实运行：结果与原始回答'
    chunks = [f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src 'none'">
<title>{title}</title><style>*{{box-sizing:border-box}}body{{margin:0;background:#f4f6f8;color:#172a38;font:16px/1.7 system-ui,sans-serif}}main{{max-width:1120px;margin:auto;padding:28px 20px}}h1{{font-size:29px}}h2{{font-size:22px}}article,.metrics{{background:white;padding:24px;border:1px solid #d9e1e7;border-radius:12px;margin:18px 0}}.metrics{{display:flex;gap:28px;flex-wrap:wrap}}b.number{{display:block;font-size:31px}}.bad{{color:#a12a25}}.muted{{color:#657786;font-size:14px}}table{{width:100%;border-collapse:collapse;font-size:14px}}th,td{{padding:11px 8px;border-bottom:1px solid #dde4e9;text-align:left;vertical-align:top}}.scroll{{overflow:auto}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f6f8;padding:14px;font-size:13px}}a{{color:#17647d}}details{{margin:12px 0}}summary{{cursor:pointer}}.bar{{background:#fbe3dc;height:12px;border-radius:5px}}.bar span{{display:block;height:100%;background:#be5140;border-radius:5px}}@media(max-width:700px){{main{{padding:16px 10px}}article{{padding:16px}}h1{{font-size:24px}}}}</style>
<main><p class="muted">D / world-components-logic · 2026-11-01 · 已审42项中的4个开发场景</p><h1>{title}</h1>
<p>已经完成模型加载和第一批真实业务生成。当前77M模型的零样本配置未完成这四道题的要求，仍不能作为可用组件。</p>
<div class="metrics"><div><b class="number">4 × 5</b>每批四个场景，各重复五次</div><div><b class="number">{report['businessGenerationsTotal']}</b>真实业务生成，含最终代码复验</div><div><b class="number bad">未通过</b>当前方案的明显失败初筛</div><div><b class="number">未测</b>完整流程500毫秒</div></div>
<article><h2>这次具体做了什么</h2><ol><li>将已审题接入D独立离线运行器，记录完整输入、回答、错误和耗时。</li><li>新增可完整还原的中文字段、表格和重复文本编码；没有删除事实或截断输入。</li><li>保留512上限下的失败，再单独登记1024探索批取得真实答案。</li><li>单CPU线程、单进程，监督墙钟120秒及内存2048MiB；未运行训练或封存比较。</li></ol></article>
<article><h2>输入长度：改善了多少</h2><p>无损编码仍未装进512。1024批只是取得诊断证据，512内的完整分块仍待实现。</p><div class="scroll"><table><tr><th>任务</th><th>原JSON token</th><th>无损编码 token</th><th>512上限</th></tr>''']
    for old, new in zip(report['runs'][0]['tasks'], latest['tasks']):
        chunks.append(f"<tr><td>{e(CASE_NAMES[new['caseId']])}</td><td>{old['inputTokens']}</td><td>{new['inputTokens']}</td><td class='bad'>仍超限</td></tr>")
    chunks.append('</table></div></article><article><h2>真实回答与逐任务耗时</h2><p>耗时包含本次输入装配、分词、生成、解码及格式校验，不包含冷加载，也不是完整游戏流程。每任务仅5次，不能签正式性能通过。初始局部工程预算为50毫秒。</p><div class="scroll"><table><tr><th>任务</th><th>结构通过</th><th>中位数 ms</th><th>p95 / 最大 ms</th><th>相对50ms预算</th></tr>')
    for task in latest['tasks']:
        chunks.append(f"<tr><td>{e(CASE_NAMES[task['caseId']])}</td><td>{task['structureValid']} / 5</td><td>{task['p50Ms']:.2f}</td><td>{task['p95Ms']:.2f} / {task['maxMs']:.2f}</td><td><div class='bar'><span style='width:{min(100,task['p50Ms']/350*100):.1f}%'></span></div>{task['p50Ms']/50:.1f}倍</td></tr>")
    chunks.append('</table></div><p class="bad">反应题的“结构通过”仅表示非空文本；它没有完成应对行动，不能算答对。</p></article>')
    rubric = {r['caseId']: r for r in load_jsonl(ROOT/'experiments/world-components-logic/data/dev-review-drafts.jsonl')}
    plan = json.loads((PILOTS/f'{PREFIX}r4.plan.json').read_text(encoding='utf-8'))
    record = json.loads((PILOTS/f'{PREFIX}r4.record.json').read_text(encoding='utf-8'))
    for observation, task in zip(report['assistantDiagnosticObservations'], latest['tasks']):
        cid = task['caseId']; case = next(c for c in plan['cases'] if c['caseId'] == cid)
        chunks.append(f"<article><h2>{e(CASE_NAMES[cid])} · {e(cid)}</h2><p>{e(observation['finding'])}</p><h3>模型原始回答（5次相同）</h3><pre>{e(task['uniqueRawOutputs'][0])}</pre>")
        for label, value in [('查看已审题完整输入',case['input']), ('查看原判据',rubric[cid]['draftExpected']), ('查看5次完整原始记录',[a for a in record['attempts'] if a['caseId']==cid])]:
            chunks.append(f'<details><summary>{label}</summary><pre>{e(json.dumps(value,ensure_ascii=False,indent=2))}</pre></details>')
        chunks.append('</article>')
    chunks.append('<article><h2>四批证据都保留</h2><div class="scroll"><table><tr><th>批次</th><th>输入上限</th><th>真实业务生成</th><th>证据</th></tr>')
    for run in report['runs']:
        name=run['runId']
        chunks.append(f'<tr><td>{e(name)}</td><td>{run["inputLimit"]}</td><td>{run["generationCalls"]}</td><td><a href="pilots/{e(name)}.plan.json">配置与输入</a> · <a href="pilots/{e(name)}.record.json">运行记录</a></td></tr>')
    chunks.append('</table></div><p>r1/r2共40次输入超限拦截；r3首次真实生成20次，r4修复异常记录与环境复核后再生成20次。最终代码复验与早期批次分开，不能合并凑成每任务20次正式样本。耗时包含运行日志开销。r1–r3只保留当时准备环境声明，r4另记录实际解释器、依赖和线程；旧记录没有倒填证明。</p></article><article><h2>下一步与尚未完成</h2><p>当前零样本联合生成不推荐直接使用。下一步是拆分判断与短文本任务，准备独立训练的小判断头，再验证实际协同；512完整输入分块仍待。正式人工盲评、来源核验、短链、完整请求、浏览器与生产接线均未通过。本页的明显失败说明由实现者整理，不冒充独立正式评分。</p><p><a href="l3-4-pilot-summary.json">查看机器可读汇总及文件哈希</a></p></article></main></html>')
    return ''.join(chunks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check',action='store_true');mode.add_argument('--write-new',action='store_true')
    args=parser.parse_args();report,files=build()
    for path, raw in files.items():
        if path.exists() and path.read_bytes()!=raw:raise ValueError(f'报告已有不同版本：{path}')
        if args.check and not path.exists():raise ValueError(f'缺报告：{path}')
    if args.write_new:
        for path, raw in files.items():
            if not path.exists():
                with path.open('xb') as f:f.write(raw)
    print(json.dumps({'businessGenerations':report['businessGenerationsTotal'],'verdict':report['verdict']},ensure_ascii=False))


if __name__=='__main__':main()
