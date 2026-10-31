"""Build a local human-review packet; never changes labels or signs approval."""
from __future__ import annotations

import json
from pathlib import Path

from lab import canonical_bytes
from review_io import build_packet

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'artifacts/world-components-logic/l3-1-review.html'

HTML = r'''<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'none'">
<title>L3 新题审阅 · 非叙事组件</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f4f5f7;color:#202735;font:15px/1.65 system-ui,-apple-system,sans-serif}header{background:#162a35;color:#fff;padding:28px max(24px,5vw)}h1{font-size:26px;line-height:1.4;margin:0 0 10px}header p{max-width:950px;color:#d1e0e5;margin:6px 0}.bar{padding:16px max(24px,5vw);display:flex;gap:12px;align-items:center;flex-wrap:wrap;background:white;border-bottom:1px solid #dce1e8}.pill{padding:3px 12px;border-radius:14px;background:#e5edf1;color:#254957}button,select,input,textarea{font:inherit}button{padding:8px 14px;border-radius:8px;border:1px solid #bac9d0;background:#fff;color:#254957;cursor:pointer}button:hover{background:#e9f2f4}button.active{background:#245b65;color:white;border-color:#245b65}button:focus-visible,input:focus-visible,textarea:focus-visible,select:focus-visible{outline:3px solid #de9f35;outline-offset:2px}main{display:grid;grid-template-columns:280px minmax(0,1fr);gap:22px;max-width:1400px;margin:24px auto;padding:0 24px}.sidebar{max-height:calc(100vh - 260px);overflow:auto;position:sticky;top:15px;align-self:start}.case{display:block;width:100%;text-align:left;margin-bottom:8px;padding:10px 12px}.case small{display:block;color:#687586;font-size:12px}.case.active small{color:#d4e8ed}.card{background:white;border:1px solid #e0e5eb;border-radius:12px;padding:24px;margin-bottom:18px;overflow:hidden}h2{font-size:21px;margin:0 0 10px}h3{font-size:16px;margin:18px 0 8px}.muted{color:#697686;font-size:13px}.warning{padding:12px 16px;background:#fff4d9;border-radius:8px;color:#7b5011;margin:12px 0}.good{background:#e3f0ea;color:#24553e}ul{padding-left:23px;margin:6px 0}table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:10px 9px;border-bottom:1px solid #e6ebee;text-align:left;vertical-align:top}th{color:#5c6b7a;background:#f7f9fa}.table{overflow:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f6f8fa;padding:14px;font-size:12px;line-height:1.6;border-radius:6px}textarea{width:100%;min-height:100px;padding:10px;border:1px solid #bec9d1;border-radius:6px;margin:10px 0}input{max-width:240px;padding:7px;border:1px solid #bac9d0;border-radius:6px}.row{display:flex;gap:9px;flex-wrap:wrap;align-items:center}.status{color:#245b65;font-weight:600}.actions{margin-top:12px}.footer{font-size:12px;color:#7b8796;margin:12px 0 30px;overflow-wrap:anywhere}@media(max-width:850px){main{grid-template-columns:1fr;padding:0 12px}.sidebar{position:static;max-height:180px}.card{padding:18px}.bar{padding:12px}header{padding:22px}h1{font-size:23px}}
</style>
<header><h1>帮我们确认：这道题和判断标准合理吗？</h1>
<p>这里是 L3 的开发题草稿，全部由 AI 新写，尚待人工核对。你现在审的是题目与判据，还没有行动、反应或共同结果的模型成绩。</p>
<p>整次计算目标 ≤500 毫秒；速度要另做实测。认可题目不会把项目自动标成“正确”或“达到半秒”。</p></header>
<div class="bar"><span class="pill">40 个来源组 / 42 个测试项</span><span class="pill" id="progress"></span>
<label for="filter">看哪类题</label><select id="filter"><option value="all">全部题目</option><option value="D02">行动：要不要做、怎么做</option><option value="D03">目标：会牵连谁</option><option value="D04">反应：被迫如何应对</option><option value="D05">共同结果：全组一起结算</option></select>
<label for="reviewer">你的称呼</label><input id="reviewer" placeholder="导出前填写" maxlength="80"><button id="export">导出我的审阅意见</button></div>
<div class="bar" role="status" id="storageStatus">意见尚未记录。可分批审阅和导出，原始题目不会被修改。</div>
<main><nav class="sidebar" id="list" aria-label="题目列表"></nav><section id="detail"></section></main>
<script id="packet" type="application/json">__PACKET__</script>
<script>
'use strict';
const packet=JSON.parse(document.getElementById('packet').textContent),taskNames={D02:'行动：要不要做、怎么做',D03:'目标：会牵连谁',D04:'反应：被迫如何应对',D05:'共同结果：全组一起结算'};
const storageKey='jity-d-l3-review-'+packet.inputSha256+'-'+packet.reviewDraftSha256;
const byId=Object.fromEntries(packet.cases.map(c=>[c.caseId,c]));
let saved={reviewer:'',decisions:{},draftNotes:{}},active=packet.cases[0].caseId,storageAvailable=true,storageMessage='尚未记录意见。可分批审阅和导出。';
const isObject=x=>x!==null&&typeof x==='object'&&!Array.isArray(x);
function validDecision(id,d){const c=byId[id];return c&&isObject(d)&&d.caseId===id&&d.sourceGroup===c.sourceGroup&&d.inputSha256===c.inputSha256&&d.reviewDraftSha256===c.reviewSha256&&['agree','revise','uncertain'].includes(d.decision)&&typeof d.note==='string'&&(d.decision!=='revise'||d.note.trim())&&typeof d.recordedAt==='string'&&Number.isFinite(Date.parse(d.recordedAt))}
try{const raw=localStorage.getItem(storageKey);if(raw){const parsed=JSON.parse(raw);if(!isObject(parsed)||typeof parsed.reviewer!=='string'||!isObject(parsed.decisions)||!Object.entries(parsed.decisions).every(([id,d])=>validDecision(id,d))||(parsed.draftNotes!==undefined&&(!isObject(parsed.draftNotes)||!Object.entries(parsed.draftNotes).every(([id,n])=>byId[id]&&typeof n==='string'))))throw Error('invalid saved record');saved={reviewer:parsed.reviewer,decisions:parsed.decisions,draftNotes:parsed.draftNotes||{}};storageMessage='已恢复本浏览器中的意见；完成一批后请导出备份。'}}catch(e){storageAvailable=false;storageMessage='无法读取本地保存：旧记录保持原样。本页新意见暂存在内存，请及时导出备份，关闭或刷新会丢失。'}
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n};
function persist(){if(storageAvailable){try{localStorage.setItem(storageKey,JSON.stringify(saved));storageMessage='意见已保存在本浏览器；建议完成一批就导出备份。'}catch(e){storageAvailable=false;storageMessage='本地保存失败：新意见暂存在本页内存，请及时导出备份，关闭或刷新会丢失。'}}refreshProgress()}
function refreshProgress(){const ds=Object.values(saved.decisions);document.getElementById('progress').textContent='已记录 '+ds.length+' / '+packet.cases.length+' 项 · 认可 '+ds.filter(d=>d.decision==='agree').length+' · 需改 '+ds.filter(d=>d.decision==='revise').length+' · 待定 '+ds.filter(d=>d.decision==='uncertain').length;document.getElementById('storageStatus').textContent=storageMessage}
function bullets(parent,title,values){if(!values||!values.length)return;parent.append(el('h3',title));const list=el('ul');for(const text of values)list.append(el('li',String(text)));parent.append(list)}
function table(parent,head,rows){const wrap=el('div',undefined,'table'),t=el('table'),tr=el('tr');for(const s of head)tr.append(el('th',s));t.append(tr);for(const row of rows){const line=el('tr');for(const s of row)line.append(el('td',String(s)));t.append(line)}wrap.append(t);parent.append(wrap)}
function list(){const target=document.getElementById('list');target.replaceChildren();const f=document.getElementById('filter').value;for(const c of packet.cases){if(f!=='all'&&c.task!==f)continue;const d=saved.decisions[c.caseId],b=el('button',c.caseId+(d?' · '+({agree:'认可',revise:'需修改',uncertain:'待定'}[d.decision]||'已记录'):'') ,'case'+(c.caseId===active?' active':''));b.append(el('small',c.review.sourceNote));b.onclick=()=>{active=c.caseId;draw();list()};target.append(b)}}
function draw(){const c=byId[active],x=c.input,w=x.world,r=c.review,e=r.draftExpected,old=saved.decisions[c.caseId],root=document.getElementById('detail');root.replaceChildren();const names=Object.fromEntries(w.characters.map(p=>[p.id,p.name+' ['+p.id+']'])),name=id=>names[id]||id;
const top=el('article',undefined,'card');top.append(el('h2',taskNames[c.task]),el('p',r.sourceNote),el('div',c.caseId+' · '+c.sourceGroup+(c.derivedFrom?' · 与 '+c.derivedFrom+' 同源的对照项':''),'muted'));root.append(top);
const world=el('article',undefined,'card');world.append(el('h2','先看场景里已知的事实'),el('p','时间：'+w.time));table(world,['地点编号','地点','上级地点'],w.places.map(p=>[p.id,p.name,p.parentId||'无']));table(world,['人物','在哪里','任务','个性 / 理智','外貌'],w.characters.map(p=>[name(p.id),p.position.containerId+' / '+p.position.slot,p.tasks.map(t=>t.text+'（'+t.status+'）').join('；'),p.personality.join('；')+' / '+p.sanity,p.appearance]));table(world,['物品','位置'],w.items.map(i=>[i.name+' ['+i.id+']',i.position.containerId+' / '+i.position.slot]));
if(c.task==='D02'){world.append(el('h3','这一步要判断什么'),el('p','轮到 '+name(x.actorId)+'。主角是 '+name(x.protagonistId)+'。'),el('p','玩家输入：'+x.advance.inputText),el('p','输入状态：'+({pending:'还没处理，需要重新判断能否执行',consumed:'已经处理，只作背景，不重复命令',expired:'已结束，只作背景'}[x.advance.intentStatus]||x.advance.intentStatus)))}
if(x.source){world.append(el('h3','已经冻结的行动'),el('p',name(x.source.memberId)+'：'+x.source.actionText))}
if(c.task==='D03')world.append(el('p','本步只找目标，还不能看到这个行动接下来掷出的骰点或准入结果。'),el('p','已经行动：'+(x.alreadyActedIds.map(name).join('、')||'无')));
if(c.task==='D04')world.append(el('p','本步涉及 '+name(x.memberId)+'；程序准入：'+(x.admission.admitted?'已准入':'未准入')+'；已行动：'+(x.alreadyActedIds.map(name).join('、')||'无')));
const group=x.group||x.confirmedGroup;if(group&&group.members){world.append(el('h3','此时已冻结的组内行动'));table(world,['人物','行动原文'],group.members.map(p=>[name(p.memberId),p.actionText||'缺失']))}
const rolls=x.judgments||(x.group&&x.group.judgments)||x.knownPriorJudgments;if(rolls&&rolls.length){world.append(el('h3','此时可见的程序判定'));table(world,['来源 → 目标','骰点 / 阈值','通过判定','可反应 / 已准入'],rolls.map(j=>[name(j.sourceId)+' → '+name(j.targetId),j.value+' / '+j.threshold,j.passed?'是':'否',(j.eligible?'是':'否')+' / '+(j.admitted?'是':'否')]));world.append(el('p','这些骰点用于是否准入反应；不是“攻击必定命中”的结果。','muted'))}
const raw=el('details');raw.append(el('summary','查看完整输入（不省略字段）'),el('pre',JSON.stringify(c.input,null,2)));world.append(raw);root.append(world);
const rubric=el('article',undefined,'card');rubric.append(el('h2','AI 拟定的判断标准，请你核对'),el('div','这是待审草稿。请判断它是否符合你的游戏规则；有歧义就记“需要修改”或“暂不确定”。','warning'));
const guardNames={ready:'资料结构齐全，允许进入判断',not_admitted:'本次未获准反应，不能调用',already_acted_reuse:'已经行动，应复用原文',missing_frozen_source_text:'缺少已确认的威胁原文，应停止',missing_or_invalid_judgment:'缺少完整有效的程序判定，应停止',missing_member_action:'缺少组内成员的行动，应停止',missing_or_duplicate_relation_judgment:'关系判定缺失或重复，应停止',group_not_closed:'行动组尚未闭合，应停止'};
rubric.append(el('p','程序是否应调用模型：'+(e.expectedCall?'应调用':'应停止或复用已确认内容')+'。当前结构检查：'+(guardNames[c.guard.reason]||c.guard.reason)));
if(e.kind)rubric.append(el('p','拟定行动判断：'+({act:'应该行动',skip:'合理不行动'}[e.kind]||e.kind)));
if(e.targetIds)rubric.append(el('p','拟定目标：'+(e.targetIds.map(v=>name(typeof v==='string'?v:v.targetId)).join('、')||'没有目标')));
bullets(rubric,'必须尊重',e.mustRespect);bullets(rubric,'不能出现',e.forbidden);bullets(rubric,'可接受的其他做法',e.acceptableAlternatives);
const full=el('details');full.append(el('summary','查看这道题的完整判据草稿'),el('pre',JSON.stringify(e,null,2)));rubric.append(full);root.append(rubric);
const decision=el('article',undefined,'card');decision.append(el('h2','你的审阅意见'),el('p','先检查情景是否够清楚，再看判据是否合理。这里只记录你的意见，不会修改原题或自动放行模型。'));
const note=el('textarea');note.placeholder='哪里不合理、缺了什么事实，或你希望怎样判断？';note.value=saved.draftNotes[c.caseId]??old?.note??'';note.setAttribute('aria-label','审阅说明');const noteHint=el('p','写完说明后，请选择下方一种意见。修改说明会清除本题旧选择，需重新确认。','muted');note.oninput=()=>{saved.draftNotes[c.caseId]=note.value;if(saved.decisions[c.caseId]?.note!==note.value)delete saved.decisions[c.caseId];for(const b of actions.children)b.className='';persist();list();noteHint.textContent='说明草稿已记录；请重新选择一种意见，才会计入导出。'};decision.append(note,noteHint);const actions=el('div',undefined,'row');
for(const [key,label] of [['agree','认可题目与判据'],['revise','需要修改'],['uncertain','暂不确定']]){const b=el('button',label,old?.decision===key?'active':'');b.onclick=()=>{if(key==='revise'&&!note.value.trim()){alert('请写一句需要修改的原因。');return}saved.decisions[c.caseId]={caseId:c.caseId,sourceGroup:c.sourceGroup,decision:key,note:note.value,inputSha256:c.inputSha256,reviewDraftSha256:c.reviewSha256,recordedAt:new Date().toISOString()};delete saved.draftNotes[c.caseId];persist();draw();list()};actions.append(b)}decision.append(actions,el('p','本地能否保存请看页首提示。可分批导出，把文件交回核对入档；不会联网发送，也不会自动放行模型或证明来源独立。','muted'));
const nav=el('div',undefined,'row actions'),idx=packet.cases.findIndex(v=>v.caseId===c.caseId);for(const [delta,label]of[[-1,'上一题'],[1,'下一题']]){const b=el('button',label);b.disabled=idx+delta<0||idx+delta>=packet.cases.length;b.onclick=()=>{active=packet.cases[idx+delta].caseId;draw();list();window.scrollTo(0,0)};nav.append(b)}decision.append(nav);root.append(decision,el('div','输入批次：'+packet.inputSha256+' · 判据批次：'+packet.reviewDraftSha256+'。全部仍为开发材料，非封存验收集。','footer'))}
document.getElementById('filter').onchange=()=>{const f=document.getElementById('filter').value;if(f!=='all'&&byId[active].task!==f)active=packet.cases.find(c=>c.task===f).caseId;draw();list()};
document.getElementById('reviewer').value=saved.reviewer||'';document.getElementById('reviewer').oninput=e=>{saved.reviewer=e.target.value;persist()};
document.getElementById('export').onclick=()=>{if(!saved.reviewer.trim()){alert('请先填写你的称呼。');return}if(Object.entries(saved.draftNotes).some(([id,n])=>n.trim()&&!saved.decisions[id])){alert('还有未确认的说明草稿，请先为这些题选择“认可”“需要修改”或“暂不确定”。');return}const decisions=Object.values(saved.decisions);if(!decisions.length){alert('请先审阅至少一道题。');return}const exportedAt=new Date().toISOString(),result={schema:'jity-d-user-review-claims-v1',reviewer:saved.reviewer.trim(),exportedAt,inputFileSha256:packet.inputSha256,reviewDraftFileSha256:packet.reviewDraftSha256,provenanceFileSha256:packet.provenanceSha256,decisions,verificationStatus:'unverified_export_pending_reconciliation',formalEvaluationAllowed:false};const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)+'\n'],{type:'application/json'})),a=el('a');a.href=url;a.download='l3-review-'+packet.inputSha256.slice(0,8)+'-'+exportedAt.replace(/[:.]/g,'-')+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);document.getElementById('storageStatus').textContent='已发起导出，请检查浏览器的下载文件。导出仍待身份核对和本人确认，不是正式签字。'};
refreshProgress();draw();list();
</script></html>'''


def render_source_cards(packet: dict) -> str:
    """Reuse the reviewed storage/export controls with an authoring-card view.

    The original 42-case HTML and its packet/storage identity remain unchanged.
    Source cards are human authoring material, not lab.py executable cases.
    """
    if packet.get('materialKind') != 'source_card_draft':
        raise ValueError('Expected a source-card packet')
    start = HTML.index('function draw(){')
    end = HTML.index("const rubric=el('article'", start)
    source_view = r'''function draw(){const c=byId[active],x=c.input,r=c.review,e=r.draftExpected,old=saved.decisions[c.caseId],root=document.getElementById('detail');root.replaceChildren();const name=id=>id;
const top=el('article',undefined,'card');top.append(el('h2',taskNames[c.task]),el('p',r.sourceNote),el('div',c.caseId+' · '+c.sourceGroup+' · '+(c.split==='development'?'开发用草稿':'封存候选，尚未正式封存'),'muted'));root.append(top);
const facts=el('article',undefined,'card');facts.append(el('h2','场景卡：已知事实与待判断问题'),el('p',x.sourceCard.facts),el('h3','要判断什么'),el('p',x.sourceCard.question),el('div','这是出题草稿，还不是完整模型输入。实体、任务原文、阶段投影与判定身份须继续补齐；认可本卡不代表可以开跑。','warning'));root.append(facts);
'''
    html = HTML[:start] + source_view + HTML[end:]
    replacements = {
        '这里是 L3 的开发题草稿，全部由 AI 新写，尚待人工核对。':
            '这里是 L3 第三步的来源场景卡，含开发用与封存候选，尚未正式封存，全部由 AI 起草、待人工核对。',
        '40 个来源组 / 42 个测试项': '90 张来源卡 · 开发 44 / 封存候选 46',
        '</select>': '<option value="CHAIN">短链：步骤如何衔接</option></select>',
        "D05:'共同结果：全组一起结算'}": "D05:'共同结果：全组一起结算',CHAIN:'短链：步骤如何衔接'}",
        "'程序是否应调用模型：'+(e.expectedCall?'应调用':'应停止或复用已确认内容')+'。当前结构检查：'+(guardNames[c.guard.reason]||c.guard.reason)":
            "'本卡仍待完整输入整理，未执行结构守卫。拟定调用要求：'+(typeof e.expectedCall==='boolean'?(e.expectedCall?'完整资料下应调用':'应停止或复用已确认内容'):'按本卡判据与实际路径判断')",
        '全部仍为开发材料，非封存验收集。': '本批为未冻结的来源卡；封存候选不能用于训练或调参，未经复核不得用于正式评测。',
    }
    for old, new in replacements.items():
        if html.count(old) != 1:
            raise ValueError('共享审阅模板已变更，请核对来源卡视图接入点')
        html = html.replace(old, new)
    embedded = canonical_bytes(packet).decode().replace('<', '\\u003c')
    return html.replace('__PACKET__', embedded)


def main() -> None:
    packet = build_packet()
    # Escape '<' so source text can never close the inert JSON script element.
    embedded = canonical_bytes(packet).decode().replace('<', '\\u003c')
    OUT.write_text(HTML.replace('__PACKET__', embedded), encoding='utf-8')
    print(json.dumps({'path': str(OUT), 'cases': len(packet['cases']), 'semanticApproval': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
