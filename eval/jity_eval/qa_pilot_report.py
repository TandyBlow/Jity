"""Self-contained, private HTML review for frozen-question QA pilot runs.

Rendering reads only the supplied run directory. It neither makes provider
calls nor grades answers; a numeric score alone is not human approval.
"""

import json
import math
import os
import tempfile
from pathlib import Path


_MODES = ("full", "recent", "state")


def _records(value):
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        return _records(value.get("records", []))
    return []


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _json_text(value):
    # Inert JSON in a script element must not permit closing that element.
    return json.dumps(value, ensure_ascii=False, allow_nan=False).replace(
        "&", "\\u0026"
    ).replace("<", "\\u003c").replace(">", "\\u003e").replace(
        "\u2028", "\\u2028"
    ).replace("\u2029", "\\u2029")


def _finite_json(value):
    """Keep malformed numeric metadata displayable, never treat NaN as a score."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): _finite_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_finite_json(item) for item in value]
    return value


def _collect(run_dir):
    root = Path(run_dir).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("run_dir must be a directory")
    warnings = []

    def load(relative, default=None, required=False):
        if not isinstance(relative, str) or not relative:
            return default
        try:
            target = (root / relative).resolve()
            target.relative_to(root)
        except (ValueError, OSError):
            warnings.append("拒绝读取运行目录以外的路径：" + str(relative))
            return default
        if not target.is_file():
            if required:
                warnings.append("缺少文件：" + relative)
            return default
        try:
            return _finite_json(json.loads(target.read_text(encoding="utf-8")))
        except (OSError, ValueError, UnicodeError) as exc:
            warnings.append("无法读取 JSON：{}（{}）".format(relative, type(exc).__name__))
            return default

    manifest = _mapping(load("manifest.json", {}, True))
    plan = _records(load("plan.json", [], True))
    results = _mapping(load("results.json", {}))
    bank_prefix = "private/bank/"
    answers = _records(load(bank_prefix + "private/answers.json", {}, True))
    items = _records(load(bank_prefix + "audit/items.json", {}, True))
    points = _records(load(bank_prefix + "audit/points.json", {}, True))
    evidence = _records(load(bank_prefix + "audit/evidence.json", {}, True))
    questions = _records(load(bank_prefix + "public/questions.json", {}))
    policy = load(bank_prefix + "private/scoring-policy.json", {})

    result_rows = _records(results.get("samples", []))
    result_index = {}
    for row in result_rows:
        key = row.get("id")
        if key in result_index:
            warnings.append("results 中重复样本 ID：" + str(key))
        result_index[key] = row
    samples = []
    seen = set()
    for row in plan:
        sample = dict(row)
        sample.update(result_index.get(row.get("id"), {}))
        sample["planned_identity"] = dict(row)
        if row.get("id") in seen:
            warnings.append("plan 中重复样本 ID：" + str(row.get("id")))
        seen.add(row.get("id"))
        samples.append(sample)
    for row in result_rows:
        if row.get("id") not in seen:
            warnings.append("结果样本不在计划中：" + str(row.get("id")))
            sample = dict(row)
            sample["planned_identity"] = {}
            samples.append(sample)
            seen.add(row.get("id"))
    for sample in samples:
        sample["request"] = _mapping(load(sample.get("request_path"), {}, True))
        sample["response"] = load(sample.get("response_path"), None, True)
        if not isinstance(sample["response"], dict):
            sample["response"] = None

    # Embed only the cited source field, never follow source_path to live data.
    frozen_cache = {}
    for entry in evidence:
        relative = entry.get("frozen_path")
        if not isinstance(relative, str) or not relative:
            entry["frozen_field_read"] = "未提供冻结路径"
            continue
        if relative not in frozen_cache:
            frozen_cache[relative] = load(bank_prefix + relative, None, True)
        value = frozen_cache[relative]
        pointer = entry.get("json_pointer")
        try:
            if value is None or not isinstance(pointer, str):
                raise ValueError("missing source/pointer")
            if pointer and not pointer.startswith("/"):
                raise ValueError("invalid JSON pointer")
            for part in pointer.split("/")[1:]:
                part = part.replace("~1", "/").replace("~0", "~")
                if isinstance(value, list):
                    if not part.isdecimal():
                        raise ValueError("invalid array index")
                    value = value[int(part)]
                elif isinstance(value, dict):
                    value = value[part]
                else:
                    raise ValueError("non-container")
            entry["frozen_field_read"] = "已读取（此页面不代替题库完整验证）"
            entry["frozen_field_value"] = value
        except (KeyError, IndexError, TypeError, ValueError):
            entry["frozen_field_read"] = "无法解析冻结字段，需复核"
            warnings.append("证据字段无法解析：" + str(entry.get("id", relative)))

    return root, {
        "manifest": manifest, "plan": plan, "results": results,
        "samples": samples, "answers": answers, "items": items,
        "points": points, "evidence": evidence, "questions": questions,
        "scoring_policy": policy, "warnings": list(dict.fromkeys(warnings)),
    }


def render_report(run_dir):
    """Write ``run_dir/report.html`` atomically and return its ``Path``.

    Absent results are a prepared/unrun report, not zero-valued performance.
    The output includes private gold and evidence; it is never model input.
    """
    root, payload = _collect(run_dir)
    target = root / "report.html"
    if target.is_symlink():
        raise ValueError("refusing a symlink report destination")
    document = _HTML.replace("__REPORT_DATA__", _json_text(payload))
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=str(root),
            prefix=".qa-report-", suffix=".tmp", delete=False,
        ) as handle:
            temp_name = handle.name
            handle.write(document)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)
    return target


_HTML = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; img-src 'none'; font-src 'none'; base-uri 'none'; form-action 'none'">
<title>Jity 独立问答试运行 · 私有审阅报告</title>
<style>
:root{color-scheme:light;--bg:#f3f5f8;--paper:#fff;--ink:#192332;--muted:#586576;--line:#dce3eb;--accent:#175db1;--warm:#fff4da}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif}main{max-width:1680px;margin:auto;padding:32px 28px 80px}h1{font-size:30px;margin:0 0 6px}h2{font-size:22px;margin:28px 0 12px}h3{font-size:18px;margin:0 0 8px}h4{font-size:15px;margin:14px 0 6px}p{margin:8px 0}.muted{color:var(--muted)}.small{font-size:13px}.notice{background:var(--warm);border-left:4px solid #b27817;padding:13px 18px;border-radius:6px}.box,.question{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:20px;margin:18px 0}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:18px 0}.metric{background:var(--paper);border:1px solid var(--line);border-radius:10px;padding:14px}.metric strong{font-size:25px;display:block}.filters{display:flex;gap:10px;flex-wrap:wrap;align-items:end;padding:16px;background:#eaf0f8;border-radius:10px}.filters label{font-size:12px;color:var(--muted);display:flex;flex-direction:column;gap:3px}select,input,button{font:inherit;border:1px solid #bac8d9;border-radius:6px;background:white;padding:7px 9px;color:var(--ink)}input{min-width:220px}button{cursor:pointer;color:var(--accent)}.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:9px 11px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}th{background:#f1f5fa;white-space:nowrap}td{overflow-wrap:anywhere}.badge{display:inline-block;font-size:12px;padding:2px 8px;background:#edf2f8;color:#3a526e;border-radius:5px;margin:2px 4px 2px 0}.warn{background:#fff0df;color:#8d4b09}.good{background:#e8f2ed;color:#225d3e}.columns{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:16px 0}.columns>section{min-width:0;border:1px solid var(--line);border-radius:8px;padding:13px;background:#fbfcfe}.sample{border-top:1px solid var(--line);padding-top:12px;margin-top:12px}details{margin:8px 0}summary{cursor:pointer;color:var(--accent);font-weight:600}pre{white-space:pre-wrap;word-break:break-word;overflow-wrap:anywhere;background:#f0f3f7;border:1px solid #e2e7ee;border-radius:7px;padding:12px;font:12px/1.6 ui-monospace,SFMono-Regular,Consolas,monospace;max-height:520px;overflow:auto;margin:8px 0}.reply{white-space:pre-wrap;word-break:break-word;background:#fff;border:1px solid var(--line);border-radius:6px;padding:12px;max-height:450px;overflow:auto}.message{margin:8px 0}.gold{border-top:1px solid var(--line);padding-top:10px}.evidence{padding:12px;border:1px solid var(--line);border-radius:7px;margin:10px 0;scroll-margin:20px}.question-text{font-size:19px;font-weight:600;margin:12px 0}.source{font:12px/1.6 ui-monospace,monospace;overflow-wrap:anywhere}.empty{text-align:center;padding:36px;color:var(--muted)}ul{padding-left:22px}.group-title{margin-top:20px}.sticky-note{color:#87500b}.topline{display:flex;justify-content:space-between;gap:15px;flex-wrap:wrap}a{color:var(--accent)}@media(max-width:1050px){.columns{grid-template-columns:1fr}main{padding:22px 14px}.filters{position:static}}@media print{body{background:white}main{max-width:none;padding:0}.filters,button{display:none}.columns{grid-template-columns:1fr}.box,.question{break-inside:avoid}pre,.reply{max-height:none}details:not([open])> :not(summary){display:block}summary{color:black}.notice{background:white}}
</style></head><body><main>
<div class="topline"><div><h1>Jity 独立问答试运行</h1><p class="muted">冻结检查点 · 三组对照 · 私有答案与证据审阅</p></div><span class="badge warn">内部审阅文件，包含私有标准答案</span></div>
<div id="overview"></div>
<div class="notice"><strong>统计边界：</strong>题库的 12 道题与 33 个评分要点来自 4 局游戏；它们不是 12 局独立游戏，也不是 33 个独立样本。三组同题回答属于配对观测。诊断题和近期信息控制题应分开解读；输入是否支持答案不等于模型已经答对。没有人工评分时，正确率为 <code>null</code>（未评分），不会记为 0%。</div>
<div id="metrics" class="metrics"></div>
<div class="filters" aria-label="筛选报告">
<label>问题 / 文本<input id="search" type="search" placeholder="题号、问题、测试目标"></label>
<label>组别<select id="mode"><option value="">全部三组</option><option value="full">完整记忆</option><option value="recent">近期上下文</option><option value="state">结构化状态</option></select></label>
<label>游戏<select id="game"><option value="">全部游戏</option></select></label>
<label>题型<select id="category"><option value="">全部题型</option></select></label>
<label>用途<select id="purpose"><option value="">全部用途</option></select></label>
<label>执行分类<select id="status"><option value="">全部状态</option><option value="unrun">未运行 / 未获批准</option><option value="answered">有效回答</option><option value="api_error">API / 网络失败</option><option value="parse_error">解析 / 回复格式问题</option><option value="incomplete">未完成 / 不确定</option><option value="other">其他状态</option></select></label>
<label>间隔<select id="interval"><option value="">全部间隔</option></select></label>
<button id="reset" type="button">重置筛选</button><button type="button" onclick="window.print()">打印 / 保存 PDF</button>
</div>
<p id="filter-count" class="muted small" aria-live="polite"></p>
<section class="box"><h2 style="margin-top:0">计数与人工审核分母</h2><p class="small muted">以下汇总随筛选变化。有效回答要求执行状态为 answered 且已解析出非空 answer 与 explanation。正确率 = 已人工审核且满分的有效回答数 / 已人工审核有效回答数；得分率 = 审核得分之和 / 对应满分之和。API 失败、解析问题、未完成和未评分回答不当作错误答案计入正确率。接受的人工评分状态仅为 human_reviewed，并要求有效的总分和满分。已审核未满分数包含部分得分回答。</p><div id="summary"></div><div id="pairs"></div><div id="dimensions"></div><div id="group-usage"></div></section>
<div id="questions"></div>
<section class="box"><h2 style="margin-top:0">用量、预算与运行审计</h2><p>本地 token 估计、预算预留与服务端 usage 是不同量。未提供的用量保持未知；缺少 usage 不表示免费或零消耗。费用只按清单中的请求模型费率估算，不查询价格、不执行请求、不自动评分，也不是实际账单。</p><div id="audit"></div></section>
<noscript><p class="notice">此离线报告需要浏览器启用 JavaScript 来展开内嵌数据；它不加载外部资源、不发送网络请求。</p></noscript>
</main><script id="report-data" type="application/json">__REPORT_DATA__</script>
<script>
'use strict';
const D=JSON.parse(document.getElementById('report-data').textContent);
const modes=['full','recent','state'];
const modeNames={full:'完整记忆',recent:'近期上下文',state:'结构化状态'};
const purposeNames={long_term_fact:'长期事实',mixed_fact_diagnostic:'混合事实诊断',recent_state_control:'近期状态控制',recent_unknown_control:'近期未知控制',retention_diagnostic:'记忆保留诊断'};
const categoryNames={early_narrative_fact:'早期叙事事实',item_state:'物品当前状态',updated_information:'更新 / 推翻旧信息',bounded_unknown:'限定范围未知',unknown:'未知',action_feasibility:'行动可行性'};
const humanStatuses=new Set(['human_reviewed']);
const $=id=>document.getElementById(id);
const obj=v=>v&&typeof v==='object'&&!Array.isArray(v)?v:{};
const arr=v=>Array.isArray(v)?v:[];
const num=v=>typeof v==='number'&&Number.isFinite(v);
const esc=v=>String(v==null?'未提供':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pretty=v=>JSON.stringify(v==null?null:v,null,2);
const pre=v=>'<pre>'+esc(typeof v==='string'?v:pretty(v))+'</pre>';
const badge=(v,cls='')=>'<span class="badge '+cls+'">'+esc(v)+'</span>';
const detail=(title,content,open=false)=>'<details'+(open?' open':'')+'><summary>'+esc(title)+'</summary>'+content+'</details>';
const index=rows=>Object.fromEntries(arr(rows).map(r=>[r.id,r]));
const gold=index(D.answers),items=index(D.items),points=index(D.points),publicQuestions=index(D.questions),evidence=index(D.evidence);
const manifest=obj(D.manifest),results=obj(D.results),config=obj(manifest.config);
function item(s){return items[s.question_id]||{};}
function questionMeta(s){return publicQuestions[s.question_id]||{};}
function category(s){return s.category||item(s).category||questionMeta(s).kind||'未标注';}
function purpose(s){return s.purpose||item(s).purpose||obj(points[s.question_id]).purpose||'未标注';}
function interval(s){return s.interval||item(s).interval||{};}
function gap(s){let x=interval(s);if(num(x))return x;for(const k of ['since_last_public_mention_actions','since_latest_explicit_actions','gap_actions'])if(num(obj(x)[k]))return x[k];return null;}
function gapBucket(s){let g=gap(s);return g===null?'未知 / 不适用':g<=5?'0–5 次提交行动':g<=11?'6–11 次提交行动':g<=23?'12–23 次提交行动':'24 次及以上提交行动';}
function validAnswer(s){const p=obj(obj(s.response).parsed);return s.status==='answered'&&typeof p.answer==='string'&&p.answer.trim().length>0&&typeof p.explanation==='string'&&p.explanation.trim().length>0;}
function classification(s){const st=String(s.status||'prepared').toLowerCase(),r=obj(s.response);if(/running|incomplete|uncertain|interrupted|in_flight|started/.test(st))return 'incomplete';if((num(r.http_status)&&r.http_status>=400)||/api_error|http_error|network_error|provider_error|transport_error/.test(st))return 'api_error';if(r.parse_error||/parse_error|invalid_response|response_invalid|parse_failed/.test(st))return 'parse_error';if(validAnswer(s))return 'answered';if(/^(prepared|pending|not_run|unrun|awaiting_approval|awaiting_review_and_budget|excluded_unapproved|context_blocked|not_approved|skipped|blocked|budget_blocked|budget_exceeded)$/.test(st))return 'unrun';return 'other';}
const classNames={answered:'有效回答',unrun:'未运行 / 未获批准',api_error:'API / 网络失败',parse_error:'解析 / 回复格式问题',incomplete:'未完成 / 不确定',other:'其他状态'};
function reviewed(s){const g=obj(s.grade);return classification(s)==='answered'&&humanStatuses.has(g.status)&&num(g.score)&&num(g.max_score)&&g.max_score>0&&g.score>=0&&g.score<=g.max_score;}
function scoreInfo(rows){const done=rows.filter(reviewed);const full=done.filter(s=>Math.abs(s.grade.score-s.grade.max_score)<1e-9).length;const earned=done.reduce((n,s)=>n+s.grade.score,0),max=done.reduce((n,s)=>n+s.grade.max_score,0);return {reviewed:done.length,full,earned,max,accuracy:done.length?full/done.length:null,rate:max?earned/max:null};}
function percent(value){return value===null?'未评分（null）':(100*value).toFixed(1)+'%';}
function approvedCount(){const a=results.approved_questions;if(num(a))return a;if(Array.isArray(a))return a.length;return '未知';}
function metric(name,value,note=''){return '<div class="metric"><span class="muted small">'+esc(name)+'</span><strong>'+esc(value)+'</strong><span class="small muted">'+esc(note)+'</span></div>';}
const all=arr(D.samples);
$('overview').innerHTML='<p>'+badge('运行：'+(results.status||'prepared'))+badge('题库：'+(obj(manifest.bank).version||'未提供'))+badge('模型：'+(config.model||'未提供'))+'</p><p class="small muted">创建时间：'+esc(manifest.created_at)+' · 下方输入是冻结请求消息；没有运行的请求明确标为待发送。原始响应仅来自已保存的响应文件。</p>';
const bankPointCount=arr(D.points).reduce((n,r)=>n+arr(r.points).length,0);
const bankGameCount=new Set(arr(D.questions).map(q=>q.game_id).filter(Boolean)).size;
const scoreAll=scoreInfo(all);
$('metrics').innerHTML=metric('计划样本',all.length,'同一问题的三组回答分别计数')+metric('已批准问题',approvedCount(),'可执行问题 '+(num(results.eligible_questions)?results.eligible_questions:'未知')+'；批准不等于评分')+metric('有效回答',all.filter(s=>classification(s)==='answered').length,'answered 且已解析；HTTP 正文不等于有效答案')+metric('登记请求尝试',num(results.model_calls)?results.model_calls:'未知','未完成记录可能尚未到达服务端')+metric('人工审核回答',scoreAll.reviewed,'正确率 '+percent(scoreAll.accuracy))+metric('冻结题库要点',bankPointCount,bankGameCount+' 局；非独立样本数');
function options(id,values,names={}){for(const v of [...new Set(values)].sort()){const o=document.createElement('option');o.value=v;o.textContent=names[v]||v;$(id).appendChild(o);}}
options('game',all.map(s=>s.game_id||'未标注'));options('category',all.map(category),categoryNames);options('purpose',all.map(purpose),purposeNames);options('interval',all.map(gapBucket));
function summaryTable(rows,key,title,names={}){const groups=new Map();for(const s of rows){const k=key(s)||'未标注';if(!groups.has(k))groups.set(k,[]);groups.get(k).push(s);}let body='';for(const [k,group] of [...groups.entries()].sort((a,b)=>a[0].localeCompare(b[0]))){const st=scoreInfo(group),count=c=>group.filter(s=>classification(s)===c).length;body+='<tr><td>'+esc(names[k]||k)+'</td><td>'+group.length+'</td><td>'+count('answered')+'</td><td>'+count('unrun')+'</td><td>'+count('api_error')+'</td><td>'+count('parse_error')+'</td><td>'+count('incomplete')+'</td><td>'+count('other')+'</td><td>'+st.reviewed+'</td><td>'+st.full+'</td><td>'+(st.reviewed-st.full)+'</td><td>'+(count('answered')-st.reviewed)+'</td><td>'+st.full+' / '+st.reviewed+'</td><td>'+percent(st.accuracy)+'</td><td>'+percent(st.rate)+'</td></tr>';}
return '<h3 class="group-title">'+esc(title)+'</h3><div class="scroll"><table><thead><tr><th>分组</th><th>计划</th><th>有效回答</th><th>未运行</th><th>API 失败</th><th>解析问题</th><th>未完成</th><th>其他</th><th>已审核分母</th><th>审核满分</th><th>审核错误 / 未满分</th><th>回答待复核</th><th>满分 / 已审核</th><th>正确率</th><th>得分率</th></tr></thead><tbody>'+body+'</tbody></table></div>';}
const dimensionNames={historical_fact:'历史事实',current_state:'当前状态',stale_information:'过时信息纠正',unsupported_claim:'无依据断言控制',unknown:'信息不足时承认未知',action_feasibility:'行动可行性'};
function dimensionTable(rows){let content='';for(const m of modes){const group=rows.filter(s=>s.mode===m);if(!group.length)continue;for(const [dimension,label]of Object.entries(dimensionNames)){let correct=0,incorrect=0,pending=0,na=0;for(const s of group){const v=obj(obj(s.grade).dimensions)[dimension];if(v==='not_applicable'){na++;continue;}if(reviewed(s)&&v==='correct')correct++;else if(reviewed(s)&&v==='incorrect')incorrect++;else pending++;}const den=correct+incorrect;content+='<tr><td>'+esc(modeNames[m])+'</td><td>'+esc(label)+'</td><td>'+correct+'</td><td>'+incorrect+'</td><td>'+den+'</td><td>'+pending+'</td><td>'+na+'</td><td>'+percent(den?correct/den:null)+'</td></tr>';}}
return '<h3 class="group-title">六维人工复核</h3><p class="small muted">每一维仅计入 human_reviewed 有效回答中标为 correct / incorrect 的判断。not_applicable 排除在该维分母之外。无依据断言维度的 correct 表示该维通过（未作无依据断言），不是“存在正确的无依据断言”。</p><div class="scroll"><table><thead><tr><th>组别</th><th>维度</th><th>通过</th><th>未通过</th><th>已审核分母</th><th>未审核 / 未运行</th><th>不适用</th><th>维度正确率</th></tr></thead><tbody>'+content+'</tbody></table></div>';}
function canonical(v){if(Array.isArray(v))return v.map(canonical);if(v&&typeof v==='object')return Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])]));return v;}
function pairing(rows){const groups=new Map();for(const s of rows){const key=JSON.stringify([s.question_id,s.repeat??1]);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(s);}let planned=0,answered=0,scored=0,mismatched=0;for(const group of groups.values()){const complete=group.length===3&&modes.every(m=>group.filter(s=>s.mode===m).length===1);const identities=new Set(group.map(s=>JSON.stringify(canonical({question:s.question||questionMeta(s).question,checkpoint:s.checkpoint||questionMeta(s).checkpoint}))));if(identities.size>1)mismatched++;if(complete&&identities.size===1){planned++;if(group.every(s=>classification(s)==='answered'))answered++;if(group.every(reviewed))scored++;}}
return '<h3 class="group-title">三组配对完整性</h3><p class="small muted">按问题与重复号配对，要求三组问题和检查点一致且每组恰有一条。计数只使用当前筛选记录；选择单组或执行状态可能使当前视图的配对不完整。</p><div class="metrics">'+metric('待比较问题 / 重复',groups.size)+metric('计划三组齐全',planned,'身份不一致 '+mismatched+' 组')+metric('三组有效回答齐全',answered,'有效回答未齐 '+(groups.size-answered)+' 组')+metric('三组人工评分齐全',scored,'已审核评分未齐 '+(groups.size-scored)+' 组')+'</div><p class="small sticky-note">'+(scored===0?'当前没有完整的三组人工评分配对，组间效果差异尚不可判断。':'这些配对仅供诊断性审阅；本页不推断统计显著性，也不把多道题当作独立游戏。')+'</p>';}
function attemptCount(s){if(num(s.attempts)&&s.attempts>=0)return s.attempts;if(s.response)return 1;return null;}
function usageValue(s,keys){const u=obj(obj(s.response).usage);for(const key of keys)if(num(u[key])&&u[key]>=0)return u[key];return null;}
function dollars(value){return value===null?'未知（null）':'$'+value.toFixed(6);}
function groupUsage(rows){let body='';for(const m of modes){const group=rows.filter(s=>s.mode===m);if(!group.length)continue;let estimated=0,reserved=0,outlimit=0,estimateMissing=0,reserveMissing=0,outMissing=0,attempts=0,attemptUnknown=0,inputKnown=0,outputKnown=0,inputSeen=0,outputSeen=0,inputUnknown=0,outputUnknown=0,costKnown=0,costSeen=0,costUnknown=0,plannedCost=0,plannedCostUnknown=0,reservedCost=0,reservedCostUnknown=0;const rates=new Set();for(const s of group){const request=obj(s.request),audit=obj(request.token_audit),price=obj(obj(config.prices)[obj(request.body).model||config.model]),rateIn=price.input_per_million,rateOut=price.output_per_million,hasRate=num(rateIn)&&rateIn>=0&&num(rateOut)&&rateOut>=0;if(hasRate)rates.add(rateIn+' / '+rateOut);else rates.add('未知');const est=audit.estimated_input_tokens,bound=audit.input_reservation_tokens,out=audit.output_limit;if(num(est))estimated+=est;else estimateMissing++;if(num(bound))reserved+=bound;else reserveMissing++;if(num(out))outlimit+=out;else outMissing++;if(hasRate&&num(est)&&num(out))plannedCost+=(est*rateIn+out*rateOut)/1e6;else plannedCostUnknown++;if(hasRate&&num(bound)&&num(out))reservedCost+=(bound*rateIn+out*rateOut)/1e6;else reservedCostUnknown++;const tries=attemptCount(s);if(tries===null){attemptUnknown++;continue;}attempts+=tries;if(!tries)continue;const input=usageValue(s,['prompt_tokens','input_tokens']),output=usageValue(s,['completion_tokens','output_tokens']);if(input!==null){inputKnown+=input;inputSeen++;}if(output!==null){outputKnown+=output;outputSeen++;}inputUnknown+=Math.max(0,tries-(input!==null?1:0));outputUnknown+=Math.max(0,tries-(output!==null?1:0));if(input!==null&&output!==null&&hasRate){costKnown+=(input*rateIn+output*rateOut)/1e6;costSeen++;}costUnknown+=Math.max(0,tries-(input!==null&&output!==null&&hasRate?1:0));}
const estimateCell=(value,missing)=>esc(value)+(missing?'；另 '+missing+' 条未知':'');const actualCell=(value,seen,unknown)=>!attempts&&!attemptUnknown?'未调用（null）':(seen?esc(value)+'（已知小计）':'未知（null）')+'<br><span class="muted">未知 '+unknown+' 次'+(attemptUnknown?'；另 '+attemptUnknown+' 条尝试数未知':'')+'</span>';const actualCost=!attempts&&!attemptUnknown?'未调用（null）':(costSeen?dollars(costKnown)+'（已知小计）':'未知（null）')+'<br><span class="muted">'+costUnknown+' 次用量 / 费率未知'+(attemptUnknown?'；另 '+attemptUnknown+' 条尝试数未知':'')+'</span>';
body+='<tr><td>'+esc(modeNames[m])+'</td><td>'+estimateCell(estimated,estimateMissing)+'</td><td>'+estimateCell(reserved,reserveMissing)+'</td><td>'+estimateCell(outlimit,outMissing)+'</td><td>'+esc(attempts)+(attemptUnknown?' + '+attemptUnknown+' 条未知':'')+'</td><td>'+actualCell(inputKnown,inputSeen,inputUnknown)+'</td><td>'+actualCell(outputKnown,outputSeen,outputUnknown)+'</td><td>'+esc([...rates].join('；'))+'</td><td>'+dollars(plannedCostUnknown===group.length?null:plannedCost)+(plannedCostUnknown?'<br>'+plannedCostUnknown+' 条未知':'')+'</td><td>'+dollars(reservedCostUnknown===group.length?null:reservedCost)+(reservedCostUnknown?'<br>'+reservedCostUnknown+' 条未知':'')+'</td><td>'+actualCost+'</td></tr>';}
return '<h3 class="group-title">按组 token 与费用</h3><p class="small muted">估计与预留覆盖当前筛选的全部计划请求，不代表已发送；登记的未完成请求也可能尚未到达服务端。费率列为清单中的输入 / 输出美元每百万 tokens（本试运行按公布的高峰费率配置，不假设缓存折扣）；上限费用假设每次输出达到上限。实测列仅使用保存响应的 usage，未完成 / 缺失用量保留未知；多次尝试只有一份响应时，其余尝试不记为零。费用均为估算，最终以账单为准。</p><div class="scroll"><table><thead><tr><th>组别</th><th>输入估计 tokens</th><th>输入预留 tokens</th><th>计划输出上限</th><th>登记请求尝试</th><th>实测输入 tokens</th><th>实测输出 tokens</th><th>配置费率 输入 / 输出</th><th>估计输入＋输出上限费用</th><th>预留输入＋输出上限费用</th><th>已知 usage 费用估计</th></tr></thead><tbody>'+body+'</tbody></table></div>';}
function tokenView(s){const a=obj(obj(s.request).token_audit),channels=obj(a.channels);let rows='';for(const [k,v0]of Object.entries(channels)){const v=obj(v0);rows+='<tr><td>'+esc(k)+'</td><td>'+esc(v.estimated_tokens)+'</td><td>'+esc(v.utf8_bytes)+'</td></tr>';}
return '<p class="small">输入估计：'+esc(a.estimated_input_tokens)+' · 输入预留：'+esc(a.input_reservation_tokens)+' · 输出上限：'+esc(a.output_limit)+'</p>'+detail('通道计量、估计器与裁剪记录','<div class="scroll"><table><thead><tr><th>通道</th><th>估计 tokens</th><th>UTF-8 字节</th></tr></thead><tbody>'+rows+'</tbody></table></div>'+pre({estimator:a.estimator,truncation:a.truncation}));}
function sampleView(s){const req=obj(s.request),r=obj(s.response),g=obj(s.grade),cl=classification(s),isReviewed=reviewed(s);let messages='';for(const [i,message0]of arr(obj(req.body).messages).entries()){const message=obj(message0);messages+='<div class="message"><span class="badge">'+esc((i+1)+' · '+(message.role||'未知角色'))+'</span>'+pre(message)+'</div>';}
let raw=typeof r.raw_text==='string'?'<div class="reply">'+esc(r.raw_text||'（空响应正文）')+'</div>':'<p class="muted">尚无保存的模型回复。</p>';
const state=badge(classNames[cl],cl==='answered'?'':'warn')+badge(s.status||'prepared')+badge(isReviewed?'已人工评分':'待人工评分',isReviewed?'good':'');
return '<article class="sample"><p class="source">'+esc(s.id)+'</p><p>'+state+'</p><p class="small">尝试次数：'+esc(s.attempts)+' · 总分：'+(isReviewed?esc(g.score)+' / '+esc(g.max_score):'未评分（null）')+'</p>'+tokenView(s)+detail((s.response?'请求消息（运行记录）':'冻结请求消息（待发送）')+' · '+arr(obj(req.body).messages).length+' 条',messages||'<p class="muted">请求消息缺失。</p>')+detail('完整请求体与指纹',pre(req))+'<h4>原始回复</h4>'+raw+(r.parse_error?'<p class="notice small">解析问题：'+esc(r.parse_error)+'</p>':'')+detail('解析结果与响应元数据',pre({parsed:r.parsed===undefined?null:r.parsed,parse_error:r.parse_error,model:r.model,finish_reason:r.finish_reason,http_status:r.http_status,elapsed_seconds:r.elapsed_seconds,usage:r.usage,response_path:s.response_path}))+detail('服务端原始响应文档',pre(r.provider_document))+detail('人工评分要点与六维复核',pre(g))+detail('样本计划与执行元数据',pre(Object.fromEntries(Object.entries(s).filter(([k])=>!['request','response','grade'].includes(k)))))+'</article>';}
function pointRows(qid){const p=arr(obj(points[qid]).points),rub=arr(obj(obj(gold[qid]).rubric).points),rubIndex=index(rub);let rows='';for(const point of p){const chronology=obj(point.chronology),first=obj(chronology.first_explicit),last=obj(chronology.latest_explicit);function loc(v){return v.action_index==null?'不适用 / 未披露':'行动 '+v.action_index+' / 战役 '+(v.campaign_turn??'未知')+' / 节点 '+(v.timeline_node??'未知');}const inp=obj(point.inputs);rows+='<tr><td class="source">'+esc(point.id)+'</td><td>'+esc(obj(rubIndex[point.id]).criterion)+'</td><td>'+esc(loc(first))+'</td><td>'+esc(loc(last))+'<br>提交行动间隔：'+esc(last.gap_actions)+'<br>战役回合间隔：'+esc(last.gap_campaign_turns)+'</td>'+modes.map(m=>'<td>'+esc(obj(inp[m]).support)+'<br><span class="muted">'+esc(obj(inp[m]).note)+'</span></td>').join('')+'</tr>';}
return '<p class="small muted">按评分要点展示最近明确披露与实际输入支持。持续状态仍在检查点可见，不等于剧情刚刚重提；未披露的目标值不能解释为遗忘。</p><div class="scroll"><table><thead><tr><th>要点 ID</th><th>评分语义</th><th>首次明确披露</th><th>最近明确披露与间隔</th><th>完整记忆</th><th>近期上下文</th><th>结构化状态</th></tr></thead><tbody>'+rows+'</tbody></table></div>'+detail('逐要点完整审计（含更新、证据 ID、待复核项）',pre(points[qid]||{}));}
function evidenceView(qid){const it=obj(items[qid]),point=arr(obj(points[qid]).points);const ids=new Set(arr(it.evidence_ids));for(const p of point){for(const id of arr(p.historical_evidence_ids))ids.add(id);for(const m of modes)for(const id of arr(obj(obj(p.inputs)[m]).evidence_ids))ids.add(id);}for(const e of arr(D.evidence))if(e.question_id===qid||String(e.id||'').startsWith(qid+'.'))ids.add(e.id);let content='';for(const id of ids){const e=evidence[id];if(!e){content+='<p class="notice">缺少证据：'+esc(id)+'</p>';continue;}const meta=Object.fromEntries(Object.entries(e).filter(([k])=>!['excerpt','frozen_field_value'].includes(k)));content+='<div class="evidence"><h4>'+esc(id)+'</h4><p>'+badge(e.evidence_role||'证据')+badge('提交行动 '+(e.action_index??'未知'))+badge('节点 '+(e.timeline_node??'未知'))+'</p><p class="source">'+esc(e.frozen_path)+'<br>'+esc(e.json_pointer)+'</p><h4>最小必要摘录</h4>'+pre(e.excerpt)+detail('冻结字段原值',pre(e.frozen_field_value))+detail('来源、指纹与证据元数据',pre(meta))+'</div>';}
return content||'<p class="muted">未找到该题证据索引。</p>';}
function questionView(qid,rows){const s=rows[0],q=publicQuestions[qid]||{},it=items[qid]||{},a=gold[qid]||{},cp=obj(s.checkpoint||q.checkpoint);let cols='';for(const m of modes){const group=rows.filter(x=>x.mode===m);cols+='<section><h3>'+esc(modeNames[m])+'</h3><p class="muted small">'+esc(m==='full'?'近期上下文＋记录中的历史叙事记忆＋结构化状态':m==='recent'?'仅冻结窗口内近期上下文':'近期上下文＋结构化状态（可能包含叙事语义）')+'</p>'+(group.length?group.map(sampleView).join(''):'<p class="muted">未在本次筛选中显示；不代表该组已执行或缺失。</p>')+'</section>';}
return '<section class="question"><div class="topline"><h2 style="margin:0">'+esc(qid)+'</h2><div>'+badge(s.game_id)+badge(categoryNames[category(s)]||category(s))+badge(purposeNames[purpose(s)]||purpose(s))+'</div></div><p class="question-text">'+esc(s.question||q.question)+'</p><p class="small">检查点：提交行动 '+esc(cp.action_index)+' / 战役推进回合 '+esc(cp.campaign_turn)+' / 时间线节点 '+esc(cp.timeline_node)+' · 整题话题间隔：'+esc(gap(s))+' 次提交行动（各评分要点另列）</p><p class="muted small">测试目标：'+esc(it.test_target)+'</p>'+detail('检查点、状态指纹与间隔定义',pre({checkpoint:cp,interval:interval(s),point_support:s.point_support}))+'<div class="columns">'+cols+'</div><div class="gold">'+detail('私有标准答案与评分规则','<div class="reply">'+esc(a.answer)+'</div>'+pre({acceptable_phrasings:a.acceptable_phrasings,required_points:a.required_points,rubric:a.rubric,typical_errors:a.typical_errors}),true)+detail('33 个要点中的本题要点 · 信息通道与真实披露间隔',pointRows(qid))+detail('原始证据摘录与冻结字段',evidenceView(qid))+detail('事实有效期、未知范围、冲突与待复核事项',pre({validity:it.validity,review:it.review,unknown_audit:it.unknown_audit,channels:it.channels,history_scope:obj(points[qid]).history_scope,semantic_decisions:obj(points[qid]).semantic_decisions}))+'</div></section>';}
function update(){const query=$('search').value.trim().toLowerCase(),selected={mode:$('mode').value,game:$('game').value,category:$('category').value,purpose:$('purpose').value,status:$('status').value,interval:$('interval').value};const rows=all.filter(s=>(!selected.mode||s.mode===selected.mode)&&(!selected.game||(s.game_id||'未标注')===selected.game)&&(!selected.category||category(s)===selected.category)&&(!selected.purpose||purpose(s)===selected.purpose)&&(!selected.status||classification(s)===selected.status)&&(!selected.interval||gapBucket(s)===selected.interval)&&(!query||[s.question_id,s.question,item(s).test_target].join(' ').toLowerCase().includes(query)));const groups=new Map();for(const s of rows){if(!groups.has(s.question_id))groups.set(s.question_id,[]);groups.get(s.question_id).push(s);}$('filter-count').textContent='当前显示 '+groups.size+' 道题、'+rows.length+' 个计划样本；筛选不改变记录或评分。';$('summary').innerHTML=rows.length?summaryTable(rows,s=>s.mode,'按组',modeNames)+summaryTable(rows,category,'按题型',categoryNames)+summaryTable(rows,s=>s.game_id,'按游戏')+summaryTable(rows,gapBucket,'按整题话题间隔')+summaryTable(rows,purpose,'按诊断 / 控制用途',purposeNames):'<p class="empty">没有符合筛选条件的样本。</p>';$('pairs').innerHTML=pairing(rows);$('dimensions').innerHTML=dimensionTable(rows);$('group-usage').innerHTML=groupUsage(rows);$('questions').innerHTML=groups.size?[...groups.entries()].map(([id,g])=>questionView(id,g)).join(''):'<p class="empty">暂无可显示的问题。prepared 状态无需已有回答。</p>';}
for(const id of ['search','mode','game','category','purpose','status','interval'])$(id).addEventListener(id==='search'?'input':'change',update);
$('reset').addEventListener('click',()=>{for(const id of ['search','mode','game','category','purpose','status','interval'])$(id).value='';update();});
const limits=[...arr(manifest.limitations),...arr(results.limitations)];
$('audit').innerHTML=(D.warnings.length?'<div class="notice"><strong>报告读取提醒</strong><ul>'+D.warnings.map(w=>'<li>'+esc(w)+'</li>').join('')+'</ul></div>':'')+detail('服务端用量与执行计数（缺失保持未知）',pre({usage:results.usage??null,counts:results.counts??null,registered_http_attempts:results.model_calls??null,call_count_basis:results.call_count_basis??null,pending_http_outcome:results.pending_http_outcome??null,complete_http_responses:results.complete_http_responses??null,reserved_attempts:results.reserved_attempts??null,orphan_reservations:results.orphan_reservations??null,total:results.total??null,approved_questions:results.approved_questions??null,eligible_questions:results.eligible_questions??null}),true)+detail('模型参数、预算、价格及来源',pre(config))+detail('运行清单、输入和代码指纹',pre(manifest))+detail('统一人工评分政策',pre(D.scoring_policy))+detail('限制与待审阅说明','<ul>'+limits.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>')+'<p class="small muted">本报告是私有审阅产物，不得作为任何一组模型可见输入。所有数据均内嵌；页面无外部字体、脚本、图片或网络请求。原始录制路径仅作证据来源标识，报告生成器只读取运行目录中的冻结副本。</p>';
update();
</script></body></html>'''
