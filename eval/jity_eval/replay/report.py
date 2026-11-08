"""Self-contained browser audit of real Jity context assembly, without scores."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any


STATUSES = ("pending", "running", "assembled", "error", "missing_call")
MODES = {"A": "full", "B": "recent", "C": "state", "full": "full", "recent": "recent", "state": "state"}


def _embedded_json(value: Any) -> str:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            .replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def _trace(run_dir: Path, relative: Any) -> dict:
    if not relative:
        return {"trace": None, "trace_note": "此样本尚无审计证据。"}
    try:
        if not isinstance(relative, str) or Path(relative).is_absolute():
            raise ValueError("证据路径必须是本次运行目录内的相对路径")
        candidate = (run_dir / relative).resolve()
        if run_dir not in candidate.parents:
            raise ValueError("证据路径不能越过本次运行目录")
        value = json.loads(candidate.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("审计证据必须是 JSON 对象")
        if value.get("real_model_calls", 0) != 0:
            raise ValueError("审计证据包含真实模型调用，不能标记为离线组装")
        return {"trace": value, "trace_note": None}
    except (OSError, ValueError, TypeError) as exc:
        return {"trace": None, "trace_note": "审计证据不可用：%s" % exc}


def summarize_samples(samples: list[dict]) -> dict:
    """Assembly coverage and audited inputs only: no accuracy or model score."""
    counts = {key: sum(row.get("status") == key for row in samples) for key in STATUSES}
    groups = {}
    for mode in ("full", "recent", "state"):
        selected = [row for row in samples if MODES.get(row.get("mode")) == mode]
        traces = [row["trace"] for row in selected if row.get("status") == "assembled" and isinstance(row.get("trace"), dict)]
        tokens = [trace.get("truncation", {}).get("tokens_after") for trace in traces]
        tokens = [value for value in tokens if type(value) in (int, float)]
        channels = {}
        for trace in traces:
            for key, value in trace.get("channel_policy", {}).items():
                if type(value) is bool and key != "backend_state_retained":
                    channels.setdefault(key, set()).add(value)
        groups[mode] = {
            "total": len(selected), "assembled": sum(row.get("status") == "assembled" for row in selected),
            "errors": sum(row.get("status") in ("error", "missing_call") for row in selected),
            "audited": len(traces), "token_samples": len(tokens),
            "tokens_after_mean": sum(tokens) / len(tokens) if tokens else None,
            "tokens_after_min": min(tokens) if tokens else None,
            "tokens_after_max": max(tokens) if tokens else None,
            "retrieved_hits": sum(len(trace.get("retrieval_hits", [])) for trace in traces),
            "injected_hits": sum(len(trace.get("injected_memory_hits", [])) for trace in traces),
            "truncated": sum(bool(trace.get("truncation", {}).get("applied")) for trace in traces),
            "leak_findings": sum(len(trace.get("leak_audit", {}).get("findings", [])) for trace in traces),
            "channels": {key: "mixed" if len(values) != 1 else next(iter(values)) for key, values in channels.items()},
        }
    return {"total": len(samples), "counts": counts, "groups": groups,
            "review_required": sum(bool(row.get("review_required")) for row in samples),
            "missing_evidence": sum(row.get("status") == "assembled" and row.get("trace") is None for row in samples)}


def render_report(run_dir: Path) -> Path:
    run_dir = Path(run_dir).resolve()
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    if manifest.get("kind") != "jity_context_replay" or manifest.get("simulation") is not False:
        raise ValueError("本报告仅接受 Jity 历史快照上下文组装结果")
    if manifest.get("real_model_calls") != 0 or results.get("real_model_calls") != 0:
        raise ValueError("离线上下文报告要求真实模型调用为 0")
    if not isinstance(results.get("samples"), list):
        raise ValueError("results.samples 必须是列表")
    samples = []
    for raw in results["samples"]:
        if not isinstance(raw, dict) or raw.get("status") not in STATUSES or raw.get("mode") not in MODES:
            raise ValueError("样本包含未知状态或实验组")
        row = dict(raw)
        row["mode"] = MODES[row["mode"]]
        row.update(_trace(run_dir, row.get("trace_path")))
        samples.append(row)
    payload = {"manifest": manifest, "results": {key: value for key, value in results.items() if key != "samples"},
               "samples": samples, "summary": summarize_samples(samples)}
    descriptor, temporary = tempfile.mkstemp(prefix=".context-report-", suffix=".html", dir=run_dir)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(_HTML.replace("__REPORT_DATA__", _embedded_json(payload)))
            stream.flush()
            os.fsync(stream.fileno())
        target = run_dir / "report.html"
        os.replace(temporary, target)
        return target
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


_HTML = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Jity Eval · 历史回放上下文审计</title>
<style>
:root{color-scheme:light;--ink:#142640;--muted:#64748b;--blue:#315ee8;--line:#dce4ef;--bg:#f3f6fb;--green:#08785a;--red:#b12c43;--amber:#80530c}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}.wrap{width:min(1160px,calc(100% - 40px));margin:auto}header{background:var(--ink);color:white;padding:24px 0 58px}.brand{font-weight:750;letter-spacing:1.6px;font-size:14px}.eyebrow{font-size:12px;letter-spacing:2px;color:#a7bddf;margin:28px 0 10px}h1{font-size:clamp(25px,4vw,38px);line-height:1.3;margin:0 0 14px}h2{font-size:21px;margin:0 0 8px}.subtitle{color:#c2d1e6;margin:0;max-width:850px}.badge{display:inline-block;border-radius:20px;padding:4px 11px;font-size:12px;font-weight:650;background:#e7edf7;color:#365272;white-space:nowrap}.offline{background:#d7eeff;color:#153c59;margin-bottom:16px}main{margin-top:-28px!important;padding-bottom:48px}.card{background:white;border:1px solid var(--line);border-radius:14px;box-shadow:0 4px 18px #142c4b05}.metrics{display:grid;grid-template-columns:repeat(4,1fr);padding:22px 0}.metric{padding:0 24px;border-right:1px solid var(--line)}.metric:last-child{border:0}.label,.note{font-size:12px;color:var(--muted)}.number{font-size:29px;line-height:1.4;font-weight:740;font-variant-numeric:tabular-nums}.alert{padding:14px 18px;background:#fff8e9;border:1px solid #ead7aa;border-radius:10px;font-size:13px;margin-top:14px;color:var(--amber)}.section{margin-top:30px}.intro{color:var(--muted);margin:0 0 16px;font-size:14px}.mode-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.mode{padding:22px}.mode-title{font-weight:750}.mode .number{margin-top:12px}.mode .number small{font-size:12px;font-weight:400;letter-spacing:0;color:var(--muted);margin-left:8px}.mode-description{font-size:12px;color:var(--muted);min-height:40px}.stats{font-size:12px;margin-top:10px;display:grid;gap:4px}.channel-list{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}.channel{padding:2px 7px;border-radius:5px;background:#edf6f1;color:#25664a;font-size:11px}.channel.off{background:#f1f3f6;color:#7b879a}.channel.mixed{background:#fff0d2;color:var(--amber)}.filters{padding:16px;display:grid;grid-template-columns:2fr 1fr 1fr 1fr;gap:12px}.filters label{font-size:12px;color:var(--muted);display:flex;flex-direction:column;gap:5px}input,select,button{font:inherit}input,select{width:100%;min-height:39px;border:1px solid var(--line);border-radius:7px;padding:7px 9px;background:white;color:var(--ink)}input:focus,select:focus,button:focus,summary:focus-visible{outline:2px solid #5277ed;outline-offset:2px}.list-head{display:flex;justify-content:space-between;align-items:center;font-size:12px;color:var(--muted);padding:16px 0 10px}button{padding:5px 11px;border:1px solid var(--line);border-radius:7px;background:white;color:var(--ink);cursor:pointer}.sample{margin-bottom:10px}.sample>summary{list-style:none;display:flex;justify-content:space-between;align-items:center;gap:14px;padding:17px 20px;cursor:pointer}.sample>summary::-webkit-details-marker{display:none}.sample>summary:before{content:'›';font-size:22px;color:#8799b4}.sample[open]>summary:before{transform:rotate(90deg)}.summary-main{flex:1;min-width:0}.question{font-weight:600;overflow-wrap:anywhere}.meta{font-size:12px;color:var(--muted);margin-top:4px}.sample-body{border-top:1px solid var(--line);padding:18px 20px}.assembled{background:#e4f6ed;color:var(--green)}.error,.missing_call{background:#fde9ed;color:var(--red)}.running{background:#e9efff;color:var(--blue)}.review{background:#fff0d2;color:var(--amber)}.mini-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.mini{border:1px solid var(--line);border-radius:8px;padding:12px;min-width:0}.mini strong{display:block;font-size:19px}.trace{border-top:1px solid var(--line);padding-top:10px;margin-top:12px}.trace summary{font-size:13px;font-weight:600;cursor:pointer;color:#365272}pre{font:12px/1.6 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere;background:#f6f8fc;border-radius:8px;padding:14px;max-height:500px;overflow:auto;margin:10px 0 0}.metadata{padding:18px;font-size:13px}.metadata>summary{cursor:pointer}.empty{text-align:center;padding:36px;color:var(--muted)}.footer{font-size:12px;color:var(--muted);margin-top:28px}.error-text{white-space:pre-wrap;overflow-wrap:anywhere}.decision{background:#eef4ff;border-radius:8px;padding:12px;font-size:13px;margin:0 0 15px}.noscript{padding:20px;color:var(--red)}
@media(max-width:780px){.wrap{width:calc(100% - 24px)}.metrics{grid-template-columns:1fr 1fr;gap:18px}.metric:nth-child(2){border:0}.metric{padding:0 18px}.mode-grid{grid-template-columns:1fr}.mode-description{min-height:0}.filters{grid-template-columns:1fr 1fr}.filters label:first-child{grid-column:1/-1}.mini-grid{grid-template-columns:1fr 1fr}.sample>summary{padding:14px 12px;gap:8px}.sample>summary>.badge{font-size:10px;padding:3px 6px}.sample-body{padding:14px}.question{font-size:14px}}
@media print{.filters,button{display:none}pre{max-height:none}.card{box-shadow:none}.sample{break-inside:avoid}}
</style></head><body>
<header><div class="wrap"><div class="brand">JITY EVAL</div><p class="eyebrow">FROZEN HISTORY · CONTEXT AUDIT</p><div class="badge offline">真实 Jity 上下文组装 · 真实模型调用 0 · 未生成探针答案</div><h1>历史回放上下文审计</h1><p class="subtitle">从同一个历史快照恢复后端状态，在独立探针分支构造三组实际上下文。组装成功只说明输入构造完成，不代表模型记住事实，也不是长期一致性成绩。</p></div></header>
<main class="wrap"><noscript><div class="card noscript">请允许内嵌 JavaScript 以查看报告；本文件不需要网络，原始证据保存在运行目录中。</div></noscript>
<section aria-label="运行总览"><div id="metrics" class="card metrics"></div><div id="run-status" class="alert" role="status"></div><div class="alert">证据边界：当前来自历史快照恢复；真实向量检索、Director 与记忆维护调用未重放。来源回合可能只由文本匹配或状态变化定位；未知的语义重提与同义转述仍待人工复核。报告不生成模型答案或正确率。</div></section>
<section class="section" aria-labelledby="groups-title"><h2 id="groups-title">三组实际输入</h2><p class="intro">显示已组装样本的 token 估计、实际检索/注入数量和通道策略。token 使用离线估算器；各组保留相同后端真实状态，只改变模型可见信息。</p><div id="groups" class="mode-grid"></div></section>
<section class="section" aria-labelledby="samples-title"><h2 id="samples-title">逐题上下文与来源</h2><p class="intro">展开可查看完整 messages、检索命中、状态注入、裁剪步骤、来源回合和泄漏审计。精确文本扫描通过不等于语义上没有泄漏。</p><div class="card filters"><label>搜索<input id="search" type="search" placeholder="问题、探针或样本编号"></label><label>实验组<select id="mode-filter"><option value="">全部组别</option><option value="full">A · 完整记忆</option><option value="recent">B · 关闭持久记忆</option><option value="state">C · 仅结构化记忆</option></select></label><label>间隔回合<select id="delay-filter"><option value="">全部间隔</option></select></label><label>结果状态<select id="status-filter"><option value="">全部状态</option><option value="assembled">组装成功</option><option value="missing_call">缺失调用记录</option><option value="error">组装错误</option><option value="pending">待运行</option><option value="running">运行中</option></select></label></div><div class="list-head"><span id="filter-count" aria-live="polite"></span><button id="reset" type="button">重置筛选</button></div><div id="samples"></div></section>
<section class="section"><details class="card metadata"><summary>数据集、运行配置与证据限制</summary><p class="note">当前 HTML 已内嵌证据，是生成时的快照；恢复任务后请重新生成报告。后端状态散列只用于核验分支隔离。</p><pre id="metadata"></pre></details></section><footer class="footer">Jity Eval · 历史快照上下文审计 · 自包含离线报告，不加载外部资源，不发送网络请求。</footer></main>
<script id="report-data" type="application/json">__REPORT_DATA__</script>
<script>
'use strict';
const data=JSON.parse(document.getElementById('report-data').textContent),rows=data.samples,counts=data.summary.counts;
const modes={full:{label:'A · 完整记忆',description:'近期上下文＋历史叙事记忆＋结构化状态。'},recent:{label:'B · 关闭持久记忆',description:'仅近期上下文与必要的共同游戏规则。'},state:{label:'C · 仅结构化记忆',description:'近期上下文＋结构化状态；历史叙事记忆关闭。'}};
const statuses={assembled:'组装成功',missing_call:'缺失调用记录',error:'组装错误',pending:'待运行',running:'运行中'};
const channels={recent_messages:'近期上下文',narrative_memory:'叙事记忆',persona:'人物记忆',recap:'前情摘要',structured_state:'结构化状态',score_tracker:'物品状态',recent_events:'历史事件'};
const names={messages:'实际 messages（完整输入）',retrieval_hits:'检索结果与最终保留标记',injected_memory_hits:'实际注入的记忆',retrieval:'检索实现与查询',state_injection:'状态注入与可见字段',truncation:'裁剪、token 估计与限制',provenance:'来源回合与定位依据',leak_audit:'关闭通道的泄漏审计',channel_policy:'实际通道策略',sections_before:'裁剪前分节',sections_after:'裁剪后分节',pipeline_scope:'复用链路与未执行步骤'};
const pretty=value=>JSON.stringify(value,null,2),display=value=>value===null||value===undefined?'—':String(value);
const el=(tag,text,cls)=>{const node=document.createElement(tag);if(text!==null&&text!==undefined)node.textContent=String(text);if(cls)node.className=cls;return node;};
function metric(label,value,note){const box=el('div',null,'metric');box.append(el('div',label,'label'),el('div',value,'number'),el('div',note,'note'));document.getElementById('metrics').append(box);}
metric('计划样本',rows.length,'每个探针 × 一个实验组');metric('上下文组装成功',counts.assembled,'尚未生成模型答案或评分');metric('缺记录 / 组装错误',counts.missing_call+counts.error,'缺记录 '+counts.missing_call+' · 错误 '+counts.error);metric('等待执行',counts.pending+counts.running,'待运行 '+counts.pending+' · 运行中 '+counts.running);
document.getElementById('run-status').textContent='任务状态：'+display(data.results.status)+'；待人工复核 '+data.summary.review_required+' 个样本；已组装但证据不可用 '+data.summary.missing_evidence+' 个。缺失调用记录会停止对应回放，不会转为真实请求。';
for(const [key,mode] of Object.entries(modes)){const group=data.summary.groups[key],box=el('article',null,'card mode');box.append(el('div',mode.label,'mode-title'),el('p',mode.description,'mode-description'));const number=el('div',group.assembled+' / '+group.total,'number');number.append(el('small','组装完成'));box.append(number);const stats=el('div',null,'stats');stats.append(el('span','平均 token 估计：'+(group.tokens_after_mean===null?'—':Math.round(group.tokens_after_mean))+'（'+group.token_samples+' 份证据）'),el('span','范围：'+display(group.tokens_after_min)+' – '+display(group.tokens_after_max)),el('span','检索命中 '+group.retrieved_hits+' · 注入命中 '+group.injected_hits),el('span','发生预算裁剪 '+group.truncated+' · 精确泄漏命中 '+group.leak_findings),el('span','错误 '+group.errors+' · 可审计 '+group.audited));box.append(stats);const list=el('div',null,'channel-list');for(const [name,enabled] of Object.entries(group.channels)){const text=(channels[name]||name)+' '+(enabled==='mixed'?'混合':enabled?'开':'关');list.append(el('span',text,'channel '+(enabled==='mixed'?'mixed':enabled?'':'off')));}if(!Object.keys(group.channels).length)list.append(el('span','尚无已组装通道证据','note'));box.append(list);document.getElementById('groups').append(box);}
for(const delay of [...new Set(rows.map(row=>row.delay))].sort((a,b)=>a-b)){const option=el('option',display(delay)+' 回合');option.value=String(delay);document.getElementById('delay-filter').append(option);}
function block(name,value){const details=el('details',null,'trace');details.append(el('summary',names[name]||name));if(name==='messages')details.append(el('p','这是实际提供给探针模型的消息内容；本轮并未调用探针模型。','note'));if(name==='provenance')details.append(el('p','状态最后变化回合不等于事实最后提及回合；未知来源以 null 保留。','note'));details.append(el('pre',pretty(value)));return details;}
function renderRow(row){const card=el('details',null,'card sample'),summary=el('summary'),main=el('div',null,'summary-main');main.append(el('div',row.question||row.probe_id,'question'),el('div',modes[row.mode].label+' · 间隔 '+display(row.delay)+' 回合 · 检查点 '+display(row.checkpoint_turn)+' · 来源 '+display(row.source_turn)+' · 尝试 '+display(row.attempts),'meta'));summary.append(main,el('span',statuses[row.status],'badge '+row.status));card.append(summary);const body=el('div',null,'sample-body');body.append(el('p','样本 '+display(row.id)+' · 探针 '+display(row.probe_id),'meta'),el('p','未生成探针答案；未评分。assembled 仅表示上下文组装成功。','decision'));if(row.review_required)body.append(el('p','待人工复核：事实最后一次语义提及尚未确认；10/20/40 回合间隔不得据此视为已验证。','alert'));if(row.error)body.append(el('div',typeof row.error==='object'?pretty(row.error):row.error,'alert error-text'));if(row.trace_note)body.append(el('p',row.trace_note,'note'));const trace=row.trace;if(trace){const truncation=trace.truncation||{},grid=el('div',null,'mini-grid');for(const [label,value] of [['token 估计（裁剪后）',truncation.tokens_after],['检索命中',(trace.retrieval_hits||[]).length],['注入记忆',(trace.injected_memory_hits||[]).length],['精确泄漏命中',(trace.leak_audit?.findings||[]).length]]){const box=el('div',null,'mini');box.append(el('span',label,'label'),el('strong',display(value)));grid.append(box);}body.append(grid);const ordered=Object.keys(names);for(const key of ordered)if(Object.hasOwnProperty.call(trace,key))body.append(block(key,trace[key]));const remaining=Object.fromEntries(Object.entries(trace).filter(([key])=>!ordered.includes(key)));if(Object.keys(remaining).length)body.append(block('其余完整审计元数据',remaining));}card.append(body);return card;}
const filterIds=['search','mode-filter','delay-filter','status-filter'];function refresh(){const query=document.getElementById('search').value.trim().toLowerCase(),mode=document.getElementById('mode-filter').value,delay=document.getElementById('delay-filter').value,status=document.getElementById('status-filter').value;const selected=rows.filter(row=>(!mode||row.mode===mode)&&(!delay||String(row.delay)===delay)&&(!status||row.status===status)&&(!query||[row.id,row.probe_id,row.question,row.error].join(' ').toLowerCase().includes(query)));const list=document.getElementById('samples');list.replaceChildren();if(selected.length){const fragment=document.createDocumentFragment();for(const row of selected)fragment.append(renderRow(row));list.append(fragment);}else list.append(el('div','没有符合筛选条件的样本。','card empty'));document.getElementById('filter-count').textContent='显示 '+selected.length+' / '+rows.length+' 个样本';}
for(const id of filterIds)document.getElementById(id).addEventListener(id==='search'?'input':'change',refresh);document.getElementById('reset').addEventListener('click',()=>{for(const id of filterIds)document.getElementById(id).value='';refresh();});document.getElementById('metadata').textContent=pretty(data.manifest);refresh();
</script></body></html>'''
