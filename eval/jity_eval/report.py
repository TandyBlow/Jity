"""Self-contained, offline browser reports. No model or network calls."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable


STATUSES = ("pending", "running", "passed", "failed", "adapter_error", "grading_error")
MODES = ("full", "recent", "state")


def summarize_samples(samples: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Keep unscored errors out of accuracy, but visible in coverage and counts."""
    rows = list(samples)
    counts = {status: sum(row.get("status") == status for row in rows) for status in STATUSES}
    groups = {}
    for mode in MODES:
        selected = [row for row in rows if row.get("mode") == mode]
        passed = sum(row.get("status") == "passed" for row in selected)
        failed = sum(row.get("status") == "failed" for row in selected)
        errors = sum(row.get("status") in ("adapter_error", "grading_error") for row in selected)
        graded = passed + failed
        groups[mode] = {
            "total": len(selected), "passed": passed, "failed": failed,
            "graded": graded, "errors": errors,
            "unscored": len(selected) - graded,
            "accuracy": passed / graded if graded else None,
            "coverage": graded / len(selected) if selected else None,
        }
    return {"total": len(rows), "counts": counts, "groups": groups}


def _embedded_json(value: Any) -> str:
    # Escaping '<' also prevents a hostile </script> from ending the data block.
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            .replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def _load_trace(run_dir: Path, relative: Any) -> Dict[str, Any]:
    if not relative:
        return {"trace": None, "trace_note": "此样本尚未产生运行证据。"}
    try:
        candidate = (run_dir / str(relative)).resolve()
        if run_dir not in candidate.parents:
            raise ValueError("证据文件必须位于本次运行目录内")
        with candidate.open(encoding="utf-8") as stream:
            trace = json.load(stream)
        return {"trace": trace, "trace_note": None}
    except (OSError, ValueError, TypeError) as error:
        return {"trace": None, "trace_note": "证据暂不可用：{}".format(error)}


def render_report(run_dir: Path) -> Path:
    """Render report.html from manifest/results and embed local trace files."""
    run_dir = Path(run_dir).resolve()
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    if manifest.get("adapter") != "offline" or results.get("real_model_calls", 0) != 0:
        raise ValueError("第一阶段报告仅支持 offline 运行，真实模型调用必须为 0")
    if not isinstance(results.get("samples"), list):
        raise ValueError("results.samples 必须是列表")
    samples = []
    for raw in results["samples"]:
        row = dict(raw)
        row.update(_load_trace(run_dir, row.get("trace_path")))
        samples.append(row)
    payload = {
        "manifest": manifest, "results": {key: value for key, value in results.items() if key != "samples"},
        "samples": samples, "summary": summarize_samples(samples),
    }
    html = _HTML.replace("__REPORT_DATA__", _embedded_json(payload))
    descriptor, temporary = tempfile.mkstemp(prefix=".report-", suffix=".html", dir=str(run_dir))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(html)
        destination = run_dir / "report.html"
        os.replace(temporary, destination)
        return destination
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


_HTML = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Jity Eval · 离线评测报告</title>
<style>
:root{color-scheme:light;--navy:#12243f;--muted:#64748b;--blue:#315ee8;--line:#dce4ef;--bg:#f3f6fb;--green:#08785a;--red:#bd3644;--amber:#99620d}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--navy);font:15px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}a{color:var(--blue)}
.top{background:var(--navy);color:#fff;padding:24px 0 58px}.wrap{width:min(1120px,calc(100% - 40px));margin:auto}.brand{font-size:14px;font-weight:750;letter-spacing:1.6px;display:flex;justify-content:space-between;align-items:center}.brand a{color:#c7d7f9;font-weight:400;letter-spacing:0;margin-left:20px;text-decoration:none}
.eyebrow{font-size:12px;letter-spacing:2px;color:#a7bddf;margin:32px 0 8px}h1{font-size:clamp(26px,4vw,38px);line-height:1.3;margin:0 0 14px;font-weight:720;overflow-wrap:anywhere}h2{font-size:21px;line-height:1.4;margin:0 0 8px}.subtitle{color:#b7c9e3;margin:0;max-width:720px}.badge{display:inline-flex;border-radius:20px;padding:3px 11px;font-size:12px;font-weight:650;background:#e7edf7;color:#365272;white-space:nowrap}.offline{background:#fce7b0;color:#5c410a;font-size:13px;margin-bottom:16px;padding:5px 13px}
main{margin-top:-28px!important;padding-bottom:48px}.card{background:white;border:1px solid var(--line);border-radius:15px;box-shadow:0 5px 20px #142c4b05}.metrics{display:grid;grid-template-columns:repeat(4,1fr);padding:22px 0}.metric{padding:0 24px;border-right:1px solid var(--line)}.metric:last-child{border:0}.metric-label{font-size:12px;color:var(--muted)}.metric-value{font-size:29px;line-height:1.4;font-weight:740;font-variant-numeric:tabular-nums}.metric-note{font-size:12px;color:var(--muted);margin-top:2px}.section{margin-top:32px}.section-intro{color:var(--muted);margin:0 0 16px;font-size:14px}.mode-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.mode{padding:22px}.mode-title{font-weight:700}.mode-description{font-size:12px;color:var(--muted);min-height:40px;margin:6px 0 12px}.score{font-size:32px;font-weight:750;letter-spacing:-1px}.score small{font-size:12px;color:var(--muted);letter-spacing:0;font-weight:400;margin-left:8px}.bar{background:#eaf0f8;height:7px;border-radius:6px;overflow:hidden;margin:12px 0}.bar span{display:block;height:100%;background:var(--blue)}.mode-stats{font-size:12px;color:var(--muted);display:flex;gap:14px;flex-wrap:wrap}.alert{border:1px solid #ebd1a0;background:#fff9ec;border-radius:10px;padding:12px 16px;color:#79531d;font-size:13px;margin-top:14px}.legend{font-size:12px;color:var(--muted)}
.table-wrap{overflow-x:auto;padding:4px 20px}.table-wrap table{border-collapse:collapse;width:100%;min-width:500px;font-size:13px;text-align:left}th,td{padding:13px 12px;border-bottom:1px solid var(--line)}tr:last-child td{border-bottom:0}th{color:var(--muted);font-size:12px;font-weight:500}.table-sub{display:block;font-size:11px;color:var(--muted)}
.filters{display:grid;grid-template-columns:2fr repeat(4,1fr);gap:12px;padding:18px;margin-bottom:14px}.filters label{font-size:12px;color:var(--muted);display:block}.filters input,.filters select{display:block;margin-top:5px;width:100%;padding:9px 10px;background:#f9fbfe;border:1px solid #cdd7e5;border-radius:7px;color:var(--navy);font:inherit;font-size:13px;min-height:39px}.filters input:focus,.filters select:focus,button:focus-visible,summary:focus-visible{outline:3px solid #b6c9ff;outline-offset:2px}.list-head{display:flex;justify-content:space-between;align-items:center;gap:16px;margin:10px 0 13px;color:var(--muted);font-size:13px}button{font:inherit;border:1px solid var(--line);border-radius:7px;padding:6px 12px;background:white;cursor:pointer;color:var(--navy)}button:hover{background:#edf2fb}
.sample{margin-bottom:10px;overflow:hidden}.sample>summary{list-style:none;cursor:pointer;display:flex;gap:14px;align-items:flex-start;padding:17px 20px}.sample>summary::-webkit-details-marker{display:none}.sample>summary:before{content:'›';font-size:22px;color:#8b9ab0;line-height:24px;transition:transform .15s}.sample[open]>summary:before{transform:rotate(90deg)}.summary-main{flex:1;min-width:0}.sample-title{font-weight:650;font-size:14px;overflow-wrap:anywhere}.sample-meta{font-size:11px;color:var(--muted);margin-top:3px;overflow-wrap:anywhere}.sample-body{border-top:1px solid var(--line);padding:20px}.question{font-size:14px;background:#f2f6fc;border-radius:8px;padding:12px 15px;margin:0 0 16px;white-space:pre-wrap;overflow-wrap:anywhere}.answer-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.answer{padding:14px;border:1px solid var(--line);border-radius:8px;min-width:0}.answer-label{color:var(--muted);font-size:11px}.answer-value{font-weight:600;margin-top:6px;white-space:pre-wrap;overflow-wrap:anywhere}.trace{margin-top:14px;border-top:1px solid var(--line);padding-top:12px}.trace summary{font-size:13px;cursor:pointer;color:#365272}.trace-note{font-size:12px;color:var(--muted);margin:6px 0}.trace pre{font:12px/1.65 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere;background:#f6f8fc;border-radius:8px;padding:14px;max-height:440px;overflow:auto;margin:8px 0 0}.passed{background:#e4f6ed;color:var(--green)}.failed{background:#fde9ed;color:var(--red)}.adapter_error,.grading_error{background:#fff0d2;color:var(--amber)}.running{background:#e9efff;color:var(--blue)}.empty{padding:40px;text-align:center;color:var(--muted)}.error-text{white-space:pre-wrap;overflow-wrap:anywhere}.footer{margin-top:32px;color:var(--muted);font-size:12px}.metadata{padding:16px 20px;font-size:12px}.metadata summary{cursor:pointer}.metadata pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px}.noscript{padding:24px;color:#a12424}
@media(max-width:760px){.wrap{width:calc(100% - 24px)}.mode-grid{grid-template-columns:1fr}.mode-description{min-height:0}.metrics{grid-template-columns:1fr 1fr;gap:18px}.metric:nth-child(2){border:0}.metric{padding:0 18px}.filters{grid-template-columns:1fr 1fr}.filters label:first-child{grid-column:1/-1}.answer-grid{grid-template-columns:1fr}.brand nav{display:none}.sample>summary{padding:14px 12px;gap:8px}.sample-body{padding:14px}.sample>summary>.badge{font-size:10px;padding:3px 7px}.list-head{align-items:flex-start}}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}@media print{.top{padding-bottom:40px}.filters,button{display:none}.card{box-shadow:none}.trace pre{max-height:none}.sample{break-inside:avoid}.mode-grid{grid-template-columns:repeat(3,1fr)}}
</style></head><body>
<header class="top"><div class="wrap"><div class="brand"><span>JITY EVAL</span><nav aria-label="报告导航"><a href="#overview">实验总览</a><a href="#samples">逐题复核</a><a href="#metadata">运行信息</a></nav></div><p class="eyebrow">LONG-TERM CONSISTENCY · OFFLINE LAB</p><div class="badge offline">离线模拟 · 非模型评测成绩 · 真实模型调用 0</div><h1 id="title">长期一致性评测</h1><p class="subtitle">验证评测工具的调度、断点恢复和证据记录。以下结果来自确定性的离线适配器，不代表 Jity 或任何真实模型的能力。</p></div></header>
<main class="wrap"><noscript><div class="card noscript">此报告使用内嵌 JavaScript 展示数据，请允许本地脚本。报告不需要网络。原始结果保存在同目录 results.json 中。</div></noscript>
<section id="overview" aria-label="实验总览"><div class="card metrics" id="metrics"></div><div id="run-alert" role="status"></div></section>
<section class="section" aria-labelledby="mode-title"><h2 id="mode-title">三组对照</h2><p class="section-intro">正确率 = 正确 ÷（正确 + 错误）。运行失败、评分失败和未完成样本不计入正确率，并单独显示。</p><div class="mode-grid" id="modes"></div></section>
<section class="section" aria-labelledby="delay-title"><h2 id="delay-title">随间隔回合变化</h2><p class="section-intro">每格同时显示正确率与已评分数量；这是一份工具验证数据，不用于推断真实模型的遗忘程度。</p><div class="card table-wrap"><table aria-label="各记忆组在不同延迟下的正确率"><thead id="delay-head"></thead><tbody id="delay-body"></tbody></table></div></section>
<section class="section" id="samples" aria-labelledby="sample-title"><h2 id="sample-title">逐题复核</h2><p class="section-intro">展开样本，对照标准答案与实际结果，检查模型可见上下文和后端证据。筛选只影响下方样本列表。</p><div class="card filters"><label>搜索<input id="search" type="search" placeholder="剧本、题目或样本编号"></label><label>实验组<select id="mode-filter"><option value="">全部组别</option><option value="full">A · 完整记忆</option><option value="recent">B · 近期上下文</option><option value="state">C · 结构化状态</option></select></label><label>间隔回合<select id="delay-filter"><option value="">全部间隔</option></select></label><label>测试类型<select id="kind-filter"><option value="">全部类型</option><option value="recall">事实回忆</option><option value="action">事实使用</option></select></label><label>结果状态<select id="status-filter"><option value="">全部状态</option><option value="passed">正确</option><option value="failed">错误</option><option value="adapter_error">运行失败</option><option value="grading_error">评分失败</option><option value="pending">待运行</option><option value="running">运行中</option></select></label></div><div class="list-head"><span id="filter-count" aria-live="polite"></span><button id="clear-filters" type="button">重置筛选</button></div><div id="sample-list"></div></section>
<section class="section" id="metadata"><details class="card metadata"><summary>运行配置与输入指纹</summary><p class="trace-note">报告已内嵌运行证据，可离线打开。此文件是生成时的快照；任务恢复后请重新生成并刷新报告。</p><pre id="metadata-content"></pre></details></section><footer class="footer">Jity Eval · 独立评测工具 / 第一阶段 · 本报告不加载外部资源，不发送网络请求。</footer></main>
<script id="report-data" type="application/json">__REPORT_DATA__</script>
<script>
'use strict';
const data=JSON.parse(document.getElementById('report-data').textContent);
const modes={full:{name:'A · 完整记忆',desc:'离线模拟：历史叙事事实与结构化记录均可见。'},recent:{name:'B · 近期上下文',desc:'离线模拟：仅能读取固定窗口内的近期事实。'},state:{name:'C · 结构化状态',desc:'离线模拟：近期事实加结构化状态，关闭历史叙事记忆。'}};
const statuses={passed:'正确',failed:'错误',pending:'待运行',running:'运行中',adapter_error:'运行失败',grading_error:'评分失败'};
const runStatuses={created:'已创建',running:'运行中',paused:'已暂停',completed:'已完成',completed_with_errors:'已结束 · 含失败样本',failed:'执行失败'};
const kinds={recall:'事实回忆',action:'事实使用'};
const el=(tag,text,cls)=>{const node=document.createElement(tag);if(text!==undefined&&text!==null)node.textContent=String(text);if(cls)node.className=cls;return node;};
const percent=n=>n===null||n===undefined?'—':(n*100).toFixed(1)+'%';
const value=v=>v===null?'未知 / 无可用事实':v===undefined?'尚无结果':typeof v==='object'?JSON.stringify(v):String(v);
const pretty=v=>JSON.stringify(v,null,2);
const rows=data.samples,counts=data.summary.counts;
document.getElementById('title').textContent=data.manifest.title||'长期一致性评测';
function metric(label,number,note){const box=el('div',null,'metric');box.append(el('div',label,'metric-label'),el('div',number,'metric-value'),el('div',note,'metric-note'));document.getElementById('metrics').append(box);}
metric('评测样本',data.summary.total,'运行编号 '+data.manifest.run_id);
metric('已评分',counts.passed+counts.failed,'正确 '+counts.passed+' · 错误 '+counts.failed);
metric('待完成',counts.pending+counts.running,'待运行 '+counts.pending+' · 运行中 '+counts.running);
metric('运行 / 评分失败',counts.adapter_error+counts.grading_error,'运行失败 '+counts.adapter_error+' · 评分失败 '+counts.grading_error);
const warning=el('div',null,'alert');warning.textContent='任务状态：'+(runStatuses[data.results.status]||data.results.status||'未知')+'。'+((counts.adapter_error+counts.grading_error)>0?'存在未评分的失败样本：它们不会被计为正确，请查看错误详情并按需重试。':(counts.pending+counts.running)>0?'任务尚未完成，当前正确率只代表已评分部分。':'本轮离线样本已结束，结果仅用于验证评测工具。');document.getElementById('run-alert').append(warning);
for(const [key,mode] of Object.entries(modes)){const g=data.summary.groups[key],box=el('article',null,'card mode');box.append(el('div',mode.name,'mode-title'),el('p',mode.desc,'mode-description'));const score=el('div',percent(g.accuracy),'score');score.append(el('small','已评分正确率'));box.append(score);const bar=el('div',null,'bar'),fill=el('span');fill.style.width=String((g.accuracy||0)*100)+'%';bar.append(fill);box.append(bar);const stats=el('div',null,'mode-stats');stats.append(el('span','已评分 '+g.graded+' / '+g.total),el('span','失败 '+g.errors),el('span','未评分 '+g.unscored));box.append(stats);document.getElementById('modes').append(box);}
const delays=[...new Set(rows.map(x=>x.delay))].sort((a,b)=>a-b);
const head=el('tr');head.append(el('th','间隔'));for(const mode of Object.values(modes))head.append(el('th',mode.name));document.getElementById('delay-head').append(head);
for(const delay of delays){const tr=el('tr');tr.append(el('td',delay+' 回合'));for(const mode of Object.keys(modes)){const selected=rows.filter(r=>r.delay===delay&&r.mode===mode),graded=selected.filter(r=>r.status==='passed'||r.status==='failed'),passed=graded.filter(r=>r.status==='passed').length;const cell=el('td',percent(graded.length?passed/graded.length:null));cell.append(el('span','正确 '+passed+' / 已评分 '+graded.length+' · 总数 '+selected.length,'table-sub'));tr.append(cell);}document.getElementById('delay-body').append(tr);const opt=el('option',delay+' 回合');opt.value=String(delay);document.getElementById('delay-filter').append(opt);}
const traceNames={visible_context:'适配器可见上下文',raw_response:'原始离线回复',parsed_draft:'解析后的草稿',validated_output:'规则校验后的输出',committed_state:'保存状态',grading:'评分依据',backend_truth:'后端真实状态（不进入模型上下文）',channels_requested:'请求的记忆通道',channels_applied:'实际使用的记忆通道'};
function traceBlock(name,body){const section=el('details',null,'trace');section.append(el('summary',traceNames[name]||name));if(name==='backend_truth')section.append(el('p','此信息仅用于后端与评分取证，不提供给被测适配器的回答逻辑。','trace-note'));section.append(el('pre',pretty(body)));return section;}
function renderSample(row){const card=el('details',null,'card sample'),summary=el('summary'),main=el('div',null,'summary-main');main.append(el('div',row.case_title||row.case_id,'sample-title'),el('div',(modes[row.mode]?.name||row.mode)+' · '+(kinds[row.kind]||row.kind)+' · 间隔 '+row.delay+' 回合 · 检查点 '+row.checkpoint_turn+' · 重复 '+row.repeat+' · 尝试 '+row.attempts,'sample-meta'));summary.append(main,el('span',statuses[row.status]||row.status,'badge '+(statuses[row.status]?row.status:'pending')));card.append(summary);const body=el('div',null,'sample-body');body.append(el('p',row.question,'question'));const answers=el('div',null,'answer-grid');for(const [label,answer] of [['标准答案',value(row.expected_value)],['实际结果',(row.status==='pending'||row.status==='running'||row.status==='adapter_error')?'尚无可评分回复':value(row.actual_value)]]){const box=el('div',null,'answer');box.append(el('div',label,'answer-label'),el('div',answer,'answer-value'));answers.append(box);}body.append(answers);body.append(el('p','样本 '+row.sample_id+' · 题目 '+row.probe_id,'sample-meta'));if(row.decision)body.append(el('p','行动决策：'+row.decision,'trace-note'));if(row.error)body.append(el('div',row.error,'alert error-text'));if(row.trace_note)body.append(el('p',row.trace_note,'trace-note'));if(row.trace&&typeof row.trace==='object'){for(const [name,entry] of Object.entries(row.trace))body.append(traceBlock(name,entry));}card.append(body);return card;}
const filterIds=['search','mode-filter','delay-filter','kind-filter','status-filter'];
function refresh(){const query=document.getElementById('search').value.trim().toLowerCase(),mode=document.getElementById('mode-filter').value,delay=document.getElementById('delay-filter').value,kind=document.getElementById('kind-filter').value,status=document.getElementById('status-filter').value;const selected=rows.filter(r=>(!mode||r.mode===mode)&&(!delay||String(r.delay)===delay)&&(!kind||r.kind===kind)&&(!status||r.status===status)&&(!query||[r.case_id,r.case_title,r.sample_id,r.probe_id,r.question].join(' ').toLowerCase().includes(query)));const list=document.getElementById('sample-list');list.replaceChildren();if(!selected.length)list.append(el('div','没有符合筛选条件的样本。','card empty'));else{const fragment=document.createDocumentFragment();for(const row of selected)fragment.append(renderSample(row));list.append(fragment);}document.getElementById('filter-count').textContent='显示 '+selected.length+' / '+rows.length+' 个样本';}
for(const id of filterIds)document.getElementById(id).addEventListener(id==='search'?'input':'change',refresh);
document.getElementById('clear-filters').addEventListener('click',()=>{for(const id of filterIds)document.getElementById(id).value='';refresh();});
document.getElementById('metadata-content').textContent=pretty(data.manifest);refresh();
</script></body></html>'''
