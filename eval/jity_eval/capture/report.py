"""Self-contained audit report for recorded games and exact-response replay.

The report deliberately has no memory score. Missing evidence remains visible;
merely calling a row ``completed`` is insufficient to count a complete game.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from urllib.parse import quote, urlsplit


def _embedded_json(value):
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            .replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def _read_object(path, missing):
    if not path.exists():
        missing.append(path.name + " 尚未生成")
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        missing.append(path.name + " 无法读取：" + str(exc))
        return {}
    if not isinstance(value, dict):
        missing.append(path.name + " 必须是 JSON 对象")
        return {}
    return value


def _local_link(root, value):
    """Return only existing, contained local paths, never an external URL."""
    if not isinstance(value, str) or not value or "\\" in value:
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        return None
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    candidate = (root / relative).resolve()
    if candidate == root or root not in candidate.parents or not candidate.exists():
        return None
    return quote(relative.as_posix(), safe="/")


def _is_ending(value):
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(isinstance(value.get(k), str) and value[k].strip() for k in ("id", "name", "reason"))
    return False


def summarize_games(games):
    rows = []
    for index, value in enumerate(games):
        if not isinstance(value, dict):
            rows.append({"id": "invalid-row-%s" % index, "status": "invalid", "kind": "unknown",
                         "completion_verified": False, "strict_replay_verified": False,
                         "report_findings": ["游戏记录必须是 JSON 对象"], "raw_value": value})
            continue
        row = dict(value)
        findings = []
        is_smoke = row.get("kind") in ("smoke", "summary_smoke", "acceptance")
        claimed_complete = row.get("status") in ("complete", "completed")
        complete = claimed_complete and row.get("game_over") is True and _is_ending(row.get("ending"))
        if claimed_complete and not complete and not is_smoke:
            findings.append("记录宣称完成，但缺少 game_over=true 或实际结局；不计为完整游戏")
        replay = row.get("replay") if isinstance(row.get("replay"), dict) else {}
        replay_claim = replay.get("status") in ("passed", "verified", "complete", "completed")
        strict = (replay_claim and type(replay.get("network_attempts")) is int
                  and replay.get("network_attempts") == 0
                  and replay.get("all_calls_consumed") is True
                  and replay.get("key_state_match") is True
                  and replay.get("ending_match") is True
                  and replay.get("reload_match") is True
                  and not replay.get("errors"))
        if replay_claim and not strict:
            findings.append("重放报告缺少完整断网、逐调用消耗、关键状态、结局或重载核对证据")
        row.update(completion_verified=bool(complete), strict_replay_verified=bool(strict),
                   is_smoke=is_smoke, report_findings=findings)
        rows.append(row)
    formal = [row for row in rows if not row.get("is_smoke") and row.get("kind") != "unknown"]
    return {"games": rows, "formal_games": len(formal),
            "complete_games": sum(row["completion_verified"] for row in formal),
            "accepted_games": sum(row["completion_verified"] and row["strict_replay_verified"] for row in formal),
            "unfinished_games": sum(not row["completion_verified"] for row in formal),
            "smoke_runs": sum(row.get("is_smoke", False) for row in rows),
            "findings": sum(len(row["report_findings"]) for row in rows)}


def render_capture_report(dataset_dir: Path) -> Path:
    """Render manifest.json + summary.json atomically, without executing a game."""
    root = Path(dataset_dir).resolve()
    if not root.is_dir():
        raise ValueError("录制目录不存在：" + str(root))
    missing = []
    manifest = _read_object(root / "manifest.json", missing)
    summary = _read_object(root / "summary.json", missing)
    raw_games = summary.get("games", [])
    if not isinstance(raw_games, list):
        missing.append("summary.games 必须是列表")
        raw_games = []
    counts = summarize_games(raw_games)
    for row in counts["games"]:
        row["links"] = {}
        for label, candidate in (("单局目录", row.get("path")),
                                 ("单局汇总", row.get("summary_path")),
                                 ("重放证据", row.get("replay_path"))):
            link = _local_link(root, candidate)
            if link:
                row["links"][label] = link
            elif candidate:
                row["report_findings"].append("%s路径不可用或不在本次录制目录内" % label)
    counts["findings"] = sum(len(row["report_findings"]) for row in counts["games"])
    payload = {"manifest": manifest, "summary": summary, "audit": counts, "missing": missing,
               "links": {label: link for label, name in (("数据集说明与恢复范围", "DATASET.md"),
                                                          ("版本与配置", "manifest.json"), ("原始汇总", "summary.json"))
                         if (link := _local_link(root, name))}}
    descriptor, temporary = tempfile.mkstemp(prefix=".capture-report-", suffix=".html", dir=root)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(_HTML.replace("__REPORT_DATA__", _embedded_json(payload)))
            stream.flush()
            os.fsync(stream.fileno())
        target = root / "report.html"
        os.replace(temporary, target)
        return target
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


_HTML = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'">
<title>Jity Eval · 完整游戏录制与严格重放</title>
<style>
:root{color-scheme:light;--ink:#182a41;--muted:#63748c;--line:#dce3eb;--bg:#f3f6fa;--green:#08684f;--red:#a5273f;--amber:#8b570b;--blue:#345ddb}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}.wrap{width:min(1220px,calc(100% - 40px));margin:auto}header{padding:28px 0 58px;background:#182a41;color:#fff}.brand{letter-spacing:2px;font-weight:750;font-size:13px}.eyebrow{letter-spacing:2px;color:#a2bad7;font-size:11px;margin:28px 0 10px}h1{font-size:clamp(25px,4vw,38px);line-height:1.3;margin:0 0 14px}h2{font-size:21px;margin:0 0 9px}h3{font-size:14px;margin:20px 0 8px}.subtitle{max-width:950px;color:#c4d2e5;margin:0}.tag{display:inline-block;padding:3px 9px;border-radius:20px;font-size:11px;font-weight:650;background:#edf1f6;color:#4e6380;white-space:nowrap}.pass{background:#e4f6ed;color:var(--green)}.fail{background:#ffe9ee;color:var(--red)}.warn{background:#fff1da;color:var(--amber)}main{margin-top:-28px!important;padding-bottom:45px}.card{background:white;border:1px solid var(--line);border-radius:12px;box-shadow:0 3px 15px #10254005}.metrics{display:grid;grid-template-columns:repeat(4,1fr);padding:22px 0}.metric{padding:0 24px;border-right:1px solid var(--line)}.metric:last-child{border:0}.label,.note{font-size:12px;color:var(--muted)}.number{font-size:29px;line-height:1.4;font-weight:750;font-variant-numeric:tabular-nums}.alert{overflow-wrap:anywhere;padding:13px 17px;border-radius:8px;background:#fff8e9;border:1px solid #ead8ad;color:var(--amber);margin-top:14px;font-size:13px}.section{margin-top:28px}.intro{color:var(--muted);margin:0 0 15px}.overview{padding:20px}.budget{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.budget>div{border:1px solid var(--line);border-radius:8px;padding:13px}.budget strong{display:block;font-size:22px}.filters{padding:16px;display:grid;grid-template-columns:2fr 1fr 1fr;gap:12px}label{display:flex;flex-direction:column;gap:5px;font-size:12px;color:var(--muted)}input,select,button{font:inherit}input,select{border:1px solid var(--line);border-radius:6px;background:white;color:var(--ink);padding:8px;min-height:38px}input:focus,select:focus,summary:focus-visible,a:focus-visible{outline:2px solid #4269e6;outline-offset:2px}.list-meta{color:var(--muted);font-size:12px;margin:14px 0 9px}.game{margin-bottom:12px}.game>summary{display:flex;gap:16px;align-items:center;padding:18px 20px;cursor:pointer;list-style:none}.game>summary::-webkit-details-marker{display:none}.game>summary:before{content:'›';color:#8ba0bb;font-size:23px}.game[open]>summary:before{transform:rotate(90deg)}.summary-main{flex:1;min-width:0}.game-title{font-size:16px;font-weight:650;overflow-wrap:anywhere}.meta{font-size:12px;color:var(--muted);margin-top:5px}.game-body{border-top:1px solid var(--line);padding:20px}.mini-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.mini{border:1px solid var(--line);border-radius:8px;padding:12px;min-width:0}.mini strong{display:block;font-size:18px;overflow-wrap:anywhere}.tables{display:grid;grid-template-columns:1fr 1fr;gap:20px;align-items:start}table{border-collapse:collapse;width:100%;font-size:12px}th,td{padding:9px 10px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top;overflow-wrap:anywhere}th{font-weight:600;color:var(--muted);background:#f8fafc}td:last-child{text-align:right;font-variant-numeric:tabular-nums}pre{font:12px/1.65 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere;background:#f6f8fb;border-radius:7px;padding:14px;max-height:440px;overflow:auto;margin:9px 0 0}.evidence{border-top:1px solid var(--line);margin-top:15px;padding-top:12px}.evidence>summary{cursor:pointer;font-size:13px;font-weight:600;color:#355377}.links{display:flex;gap:16px;flex-wrap:wrap;margin-top:14px}a{color:var(--blue);text-underline-offset:3px}.checklist{display:flex;flex-wrap:wrap;gap:7px;margin:12px 0}.empty{text-align:center;padding:32px;color:var(--muted)}.metadata{padding:20px}.metadata>summary{cursor:pointer}.footer{color:var(--muted);font-size:12px;margin-top:25px}.coverage-list{padding-left:20px;margin:8px 0}.coverage-list li{margin:4px 0}.bad{color:var(--red)}.ending{background:#edf3ff;padding:12px 14px;border-radius:8px;margin:14px 0;overflow-wrap:anywhere}.noscript{padding:24px;color:var(--red)}
@media(max-width:800px){.wrap{width:calc(100% - 24px)}.metrics{grid-template-columns:1fr 1fr;gap:16px}.metric{padding:0 18px}.metric:nth-child(2){border:0}.budget,.tables{grid-template-columns:1fr}.mini-grid{grid-template-columns:1fr 1fr}.filters{grid-template-columns:1fr 1fr}.filters label:first-child{grid-column:1/-1}.game>summary{padding:14px 12px;gap:9px;flex-wrap:wrap}.summary-main{min-width:180px}.game-body{padding:14px}.game-title{font-size:14px}}@media print{.filters{display:none}.card{box-shadow:none}pre{max-height:none}.game{break-inside:avoid}}
</style></head><body>
<header><div class="wrap"><div class="brand">JITY EVAL</div><p class="eyebrow">RECORDED API RESPONSES · DETERMINISTIC REPLAY</p><h1>完整游戏录制与严格重放</h1><p class="subtitle">保留实际请求和原始响应，离线重新执行游戏流程并核对结果。这里只验收固定回归数据的可追溯性和可重放性，不生成三组记忆对照的新答案，不评价长期记忆能力。</p></div></header>
<main class="wrap"><noscript><div class="card noscript">请允许内嵌 JavaScript 以查看报告。本文件不需要网络；原始证据见同目录的 manifest.json 与 summary.json。</div></noscript>
<section aria-label="数据集验收总览"><div id="metrics" class="card metrics"></div><div id="run-status" class="alert" role="status"></div><div class="alert">完整游戏必须真实触发 game_over 并记录结局。触及采集器行动、调用或费用上限而未结束的记录保留为未完成。游戏自身规则产生的预算收束属于实际结局，但不代表全部主线或配置结局通关。严格重放使用精确记录的原始响应，不重新生成模型响应；缺失调用不得由最终剧情 JSON、虚构响应或后续快照替代。</div></section>
<section class="section" aria-labelledby="budget-title"><h2 id="budget-title">用量与预算</h2><p class="intro">已知费用、按费率估算的费用和未结算请求预留分别展示；预留不是已发生账单。最终账单以服务商为准，未知费用不记为零。</p><div class="card overview"><div id="budget" class="budget"></div><details class="evidence"><summary>总预算、调用与 token 限制</summary><pre id="budget-details"></pre></details></div></section>
<section class="section" aria-labelledby="games-title"><h2 id="games-title">逐局记录与验收</h2><p class="intro">小规模验收单独列出，不计入 4 局正式数据。展开查看实际结局、角色调用、用量、覆盖事件、异常和严格重放证据。不同策略不证明不同配置分支或多个结局已覆盖。</p><div id="dataset-links" class="links"></div><div class="card filters"><label>搜索<input id="search" type="search" placeholder="局次、策略、结局或异常"></label><label>记录类型<select id="kind-filter"><option value="">全部记录</option><option value="game">正式采集</option><option value="smoke">小规模验收</option></select></label><label>验收状态<select id="status-filter"><option value="">全部状态</option><option value="accepted">完整且严格重放通过</option><option value="incomplete">未完成</option><option value="replay-pending">尚未严格重放通过</option></select></label></div><div id="filter-count" class="list-meta" aria-live="polite"></div><div id="games"></div></section>
<section class="section"><details class="card metadata"><summary>冻结版本、配置与完整汇总</summary><div id="source-links" class="links"></div><h3>代码、配置和提示词版本</h3><pre id="manifest"></pre><h3>原始汇总</h3><pre id="raw-summary"></pre></details></section>
<footer class="footer">Jity Eval · 固定游戏回归数据 · 未执行三组真实模型探针评测。此 HTML 是生成时的快照，恢复或重放后需重新生成。本文件不加载外部资源、不发送网络请求。</footer></main>
<script id="report-data" type="application/json">__REPORT_DATA__</script>
<script>
'use strict';
const data=JSON.parse(document.getElementById('report-data').textContent),rows=data.audit.games;
const el=(tag,text,cls)=>{const node=document.createElement(tag);if(text!==undefined&&text!==null)node.textContent=String(text);if(cls)node.className=cls;return node;};
const display=v=>v===undefined||v===null?'未提供':typeof v==='object'?JSON.stringify(v):String(v),pretty=v=>JSON.stringify(v,null,2),number=v=>typeof v==='number'?v.toLocaleString('zh-CN'):display(v),money=v=>typeof v==='number'?'US$'+v.toFixed(4):'未知';
function metric(label,value,note){const box=el('div',null,'metric');box.append(el('div',label,'label'),el('div',value,'number'),el('div',note,'note'));document.getElementById('metrics').append(box);}
metric('完整正式游戏',data.audit.complete_games+' / 4','需真实 game_over 与实际结局');metric('严格重放验收通过',data.audit.accepted_games+' / 4','完整＋零网络＋调用/状态/重载一致');metric('已创建但未完成',data.audit.unfinished_games,'原始证据保留，不计完整游戏');metric('小规模验收记录',data.audit.smoke_runs,'独立记录，不计正式 4 局');
const warnings=[...data.missing];for(const row of rows)for(const finding of row.report_findings)warnings.push(display(row.id)+'：'+finding);
document.getElementById('run-status').textContent='数据集状态：'+display(data.summary.status)+'；已列出 '+data.audit.formal_games+' 局正式采集。'+(warnings.length?' 证据提醒：'+warnings.join('；'):' 所有未完成及重放差异仍需逐局查看。');
const budget=data.summary.budget||{},cost={...budget,...(budget.cost||{}),...(data.summary.cost||{})};if(cost.estimated_usd===undefined&&typeof budget.known_usage_cost_usd==='number')cost.estimated_usd=budget.known_usage_cost_usd;if(cost.reserved_usd===undefined&&typeof budget.cost_usd==='number'&&typeof budget.known_usage_cost_usd==='number')cost.reserved_usd=Math.max(0,budget.cost_usd-budget.known_usage_cost_usd);for(const [label,key,note] of [['已知费用','known_usd','来自可核对的费用信息'],['按费率估算','estimated_usd','用量 × 记录费率'],['保留预留额度','reserved_usd','含缺失用量或未知完成状态']]){const item=el('div');item.append(el('span',label,'label'),el('strong',money(cost[key])),el('span',note,'note'));document.getElementById('budget').append(item);}document.getElementById('budget-details').textContent=pretty(budget);
function evidence(label,value){const details=el('details',null,'evidence');details.append(el('summary',label),el('pre',pretty(value)));return details;}
function table(title,values){const box=el('div');box.append(el('h3',title));if(!values||typeof values!=='object'||!Object.keys(values).length){box.append(el('p','未记录，不视为零。','note'));return box;}const t=el('table'),head=el('tr');head.append(el('th','类别'),el('th','数量 / 记录'));const thead=el('thead');thead.append(head);t.append(thead);const body=el('tbody');for(const [key,value] of Object.entries(values)){const tr=el('tr');tr.append(el('td',key),el('td',number(value)));body.append(tr);}t.append(body);box.append(t);return box;}
function ending(value){if(typeof value==='string')return value.trim()?value:'尚无已记录结局';if(value&&typeof value==='object')return value.name||value.reason||value.id||display(value);return '尚无已记录结局';}
function links(box,values){const list=el('div',null,'links');for(const [name,url] of Object.entries(values||{})){const link=el('a',name);link.setAttribute('href',url);list.append(link);}box.append(list);}
function listOrObject(box,label,value){box.append(el('h3',label));if(Array.isArray(value)){if(!value.length){box.append(el('p','未记录目标或事件；不等于已全部覆盖。','note'));return;}const list=el('ul',null,'coverage-list');for(const item of value)list.append(el('li',display(item)));box.append(list);}else if(value&&typeof value==='object')box.append(el('pre',pretty(value)));else box.append(el('p',display(value),'note'));}
const coverageNames={action_checks:'行动检定',anchors:'锚点揭示',anchors_revealed:'锚点揭示',campaign_stages:'战役阶段',ending:'实际结局',failed_checks:'失败检定',item_gains:'物品获取',item_removals:'物品移除',consumed_item_state:'明确消耗状态',location_changes:'地点变化',npc_dialogue:'人物对话',status_changes:'状态变化',summary_calls:'摘要调用'};
function renderCoverage(body,coverage){
  const observed=coverage.observed??coverage.events;
  if(observed&&typeof observed==='object'&&!Array.isArray(observed)){
    const counts=Object.fromEntries(Object.entries(observed).map(([key,value])=>[coverageNames[key]||key,Array.isArray(value)?value.length:value]));
    body.append(table('实际覆盖事件 · 记录条数',counts),el('p','这些是已记录事件的数量；同一物品或人物可出现多次。行动策略不是覆盖证据，物品移除也不自动等于消耗。','note'),evidence('覆盖事件原始明细',observed));
  }else listOrObject(body,'实际覆盖事件',observed??coverage);
  const uncovered=Array.isArray(coverage.uncovered)?coverage.uncovered.map(value=>typeof value==='string'?(coverageNames[value]||value):value):coverage.uncovered;
  listOrObject(body,'未覆盖 / 无法确认的目标',uncovered);
}
function renderErrors(body,row){
  const values=Array.isArray(row.errors)?row.errors:(row.errors?[row.errors]:[]);
  if(!values.length){body.append(el('p','汇总中没有异常记录；覆盖范围仍以调用和事件证据为准。','note'));return;}
  const groups=new Map();
  for(const value of values){
    const item=value&&typeof value==='object'?value:{message:display(value)};
    const label=[item.status_code!==undefined?'HTTP '+display(item.status_code):'',item.purpose||item.component||'',item.exception_type||item.type||item.error_type||'',item.message||item.error||item.note||(item.raw_text?'剧情响应解析失败（原文见完整记录）':'未分类异常')].filter(Boolean).map(display).join(' · ');
    const group=groups.get(label)||{count:0,turns:new Set()};group.count++;if(Number.isInteger(item.turn))group.turns.add(item.turn);groups.set(label,group);
  }
  body.append(el('h3','异常与降级记录'));
  const t=el('table'),head=el('tr');head.append(el('th','事件类别'),el('th','记录条数 / 涉及行动'));const thead=el('thead');thead.append(head);t.append(thead);const tbody=el('tbody');
  for(const [label,group] of groups){const tr=el('tr');tr.append(el('td',label),el('td',group.count+' 条'+(group.turns.size?' / '+group.turns.size+' 次行动':'')));tbody.append(tr);}t.append(tbody);body.append(t,el('p','警告条数可能包含恢复时重演前缀产生的重复记录，不等于独立失败次数或额外 API 请求。实际 HTTP 尝试以用途表和原始调用序号为准。','note'));
  if(values.some(v=>v&&typeof v==='object'&&String(v.message||'').includes('PCB persona extraction failed')))body.append(el('div','PCB 人物记忆维护存在本地异常。该失败分支不能算作成功覆盖；是否发起模型请求须核对用途记录，详情见数据集说明。','alert'));
  if(values.some(v=>v&&typeof v==='object'&&v.purpose==='embedding'&&v.status_code===404))body.append(el('div','嵌入接口存在 HTTP 404。原错误响应已录制；若日志显示 SHA-256 回退，重放会重现既有本地回退，不能视为远程语义嵌入成功。','alert'));
  body.append(evidence('异常原始记录（未删减）',row.errors));
}
function renderRecovery(body,row){
  const retries=Array.isArray(row.known_parse_retries)?row.known_parse_retries:null;
  body.append(el('p','SDK 自动重试：'+number(row.retries)+'；已记录的应用级解析重试：'+(retries?number(retries.length):'未单独提供')+'。两者分别计数，不将 SDK 的 0 解释为没有应用重试。','note'));
  if(retries&&retries.length){
    const turns=[...new Set(retries.map(item=>item.turn))].map(display).join('、');
    body.append(el('div','解析失败后的应用级重试涉及行动 '+turns+'。原失败响应仍保留；逐次状态未提交、骰点沿用及是否回退均在下方恢复证据中列明。','alert'),evidence('已记录的解析重试',retries));
  }
  if(Array.isArray(row.resolved_replay_issues)&&row.resolved_replay_issues.length)body.append(el('div','曾发现重放差异，已保留原失败结果及解决后的证据。消息时间恢复只恢复原始外生元数据，仍须精确匹配原请求；不替代模型响应或游戏状态。','alert'),evidence('已解决的重放差异与原失败记录',row.resolved_replay_issues));
}
function renderGame(row){
  const card=el('details',null,'card game'),head=el('summary'),main=el('div',null,'summary-main');
  main.append(el('div',display(row.id)+' · '+display(row.strategy),'game-title'),el('div',(row.is_smoke?'小规模验收':'正式采集')+' · 种子 '+display(row.seed)+' · '+display(row.turns)+' 次已提交行动 · 原始状态 '+display(row.status),'meta'));
  head.append(main,el('span',row.is_smoke?'验收片段':row.completion_verified?'完整游戏':'未完成 / 未验证','tag '+(row.completion_verified?'pass':row.is_smoke?'':'warn')),el('span',row.strict_replay_verified?'严格重放通过':'重放未通过验收','tag '+(row.strict_replay_verified?'pass':'warn')));card.append(head);
  const body=el('div',null,'game-body'),usage=row.usage||{},cost=row.cost||{},grid=el('div',null,'mini-grid');
  for(const [label,value] of [['输入 tokens',number(usage.input_tokens??usage.prompt_tokens)],['输出 tokens',number(usage.output_tokens??usage.completion_tokens)],['估算费用',money(cost.estimated_usd)],['SDK 自动重试',number(row.retries)]]){const item=el('div',null,'mini');item.append(el('span',label,'label'),el('strong',value));grid.append(item);}
  body.append(grid,el('div','实际结局：'+ending(row.ending),'ending'));
  const completion=row.completion_context||{};
  if(Object.keys(completion).length){body.append(el('p','结束 / 当前原因：'+display(completion.reason)+'；战役有效推进 '+display(completion.effective_turns)+' / '+display(completion.campaign_turn_budget)+'；章节索引 '+display(completion.arc_index)+'，小节索引 '+display(completion.session_index)+'（索引从 0 开始）。','note'),evidence('结束原因与推进证据',completion));}
  else body.append(el('p','汇总未单独提供结束原因与有效推进次数；不依据结局名称推断通关路线。详情见数据集说明及检查点。','note'));
  if(row.report_findings.length)body.append(el('div',row.report_findings.join('；'),'alert'));
  const tables=el('div',null,'tables');tables.append(table('按角色 / 用途的实际 HTTP 请求',row.calls_by_purpose),table('按请求模型的实际 HTTP 请求',row.calls_by_model));body.append(tables);
  if(row.response_models)body.append(evidence('服务商响应中的模型标识',row.response_models));
  const replay=row.replay||{},checklist=el('div',null,'checklist');
  for(const [label,value] of [['网络请求为零',replay.network_attempts===0],['所有调用已消耗',replay.all_calls_consumed],['关键状态一致',replay.key_state_match],['结局一致',replay.ending_match],['重载一致',replay.reload_match]])checklist.append(el('span',label+'：'+(value===true?'已核对':'未核对 / 不一致'),'tag '+(value===true?'pass':'warn')));
  body.append(el('h3','严格重放核对'),checklist);renderRecovery(body,row);renderErrors(body,row);renderCoverage(body,row.coverage||{});
  body.append(evidence('用量、已知 / 估算 / 预留费用',{usage:row.usage,cost:row.cost,sdk_retries:row.retries,application_parse_retries:row.known_parse_retries}),evidence('严格重放与重载完整证据',replay),evidence('本局完整汇总',Object.fromEntries(Object.entries(row).filter(([key])=>!['links','report_findings'].includes(key)))));links(body,row.links);card.append(body);return card;
}
function refresh(){const query=document.getElementById('search').value.trim().toLowerCase(),kind=document.getElementById('kind-filter').value,status=document.getElementById('status-filter').value;const selected=rows.filter(row=>(!kind||(kind==='smoke'?row.is_smoke:!row.is_smoke))&&(!status||(status==='accepted'?row.completion_verified&&row.strict_replay_verified:status==='incomplete'?!row.completion_verified:!row.strict_replay_verified))&&(!query||pretty(row).toLowerCase().includes(query)));const list=document.getElementById('games');list.replaceChildren();if(selected.length){for(const row of selected)list.append(renderGame(row));}else list.append(el('div','没有符合条件的记录。尚未开始的采集不会显示为已完成。','card empty'));document.getElementById('filter-count').textContent='显示 '+selected.length+' / '+rows.length+' 份记录';}
for(const id of ['search','kind-filter','status-filter'])document.getElementById(id).addEventListener(id==='search'?'input':'change',refresh);document.getElementById('manifest').textContent=pretty(data.manifest);document.getElementById('raw-summary').textContent=pretty(data.summary);links(document.getElementById('source-links'),data.links);links(document.getElementById('dataset-links'),data.links);refresh();
</script></body></html>'''


def main(argv=None):
    """Regenerate presentation only; never import or execute the capture runner."""
    import argparse
    parser = argparse.ArgumentParser(description="Render the Jity capture delivery report from recorded JSON only")
    parser.add_argument("dataset_dir", type=Path)
    args = parser.parse_args(argv)
    print(render_capture_report(args.dataset_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
