"""Build a local D02 human-review packet and reconcile exported claims.

The packet is blind to the assistant's expected decision: the reviewer sees the
action text and the draft annotations separately, then records independent M1
and M2 verdicts.  Reconciliation checks file hashes and writes a report; it
never edits labels, grants approval, or starts training.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
DATA = HERE / 'data' / 'd02-checkers' / 'pilot-v1'
OUT = HERE.parents[1] / 'artifacts' / 'world-components-logic' / 'd02-checkers'
SCHEMA = 'jity-d02-human-review-claims-v1'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load():
    samples = [json.loads(line) for line in (DATA / 'samples.jsonl').read_text().splitlines()]
    worlds = json.loads((DATA / 'worlds.json').read_text())
    manifest = json.loads((DATA / 'manifest.json').read_text())
    return samples, worlds, manifest


def packet():
    samples, worlds, manifest = load()
    rows = []
    for sample in samples:
        rows.append({
            'sampleId': sample['sampleId'], 'scenarioGroup': sample['scenarioGroup'],
            'split': sample['split'], 'source': sample['source'],
            'worldId': sample['worldId'], 'actorId': sample['actorId'],
            'text': sample['text'], 'steps': sample['steps'],
            'world': worlds[sample['worldId']],
            'draft': {'roleAudit': sample['roleAudit'],
                      'expressionAudit': sample['expressionAudit'],
                      'tags': sample['tags']},
            'annotationStatus': sample['annotationStatus'],
        })
    return {
        'schema': 'jity-d02-human-review-packet-v1',
        'createdAt': dt.datetime.now(dt.timezone.utc).isoformat(),
        'batch': {
            'samplesSha256': sha(DATA / 'samples.jsonl'),
            'manifestSha256': sha(DATA / 'manifest.json'),
            'worldsSha256': sha(DATA / 'worlds.json'),
            'sampleCount': len(rows),
        },
        'instructions': '先独立判断 M1/M2，再展开 AI 草稿对照；逐题记录认可/需修改/不确定。',
        'samples': rows,
    }


HTML = r'''<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'none'">
<title>D02 角色／表达检查 · 人审标注</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f4f5f7;color:#202735;font:15px/1.65 system-ui,-apple-system,sans-serif}header{background:#162a35;color:#fff;padding:24px max(20px,4vw)}h1{font-size:25px;margin:0 0 8px}header p{max-width:1000px;color:#d1e0e5;margin:5px 0}.bar{position:sticky;top:0;z-index:2;padding:12px max(20px,4vw);display:flex;gap:10px;align-items:center;flex-wrap:wrap;background:#fff;border-bottom:1px solid #dce1e8}.pill{padding:3px 11px;border-radius:13px;background:#e5edf1;color:#254957;font-size:13px}button,select,input,textarea{font:inherit}button{padding:7px 12px;border-radius:7px;border:1px solid #bac9d0;background:#fff;color:#254957;cursor:pointer}button:hover{background:#e9f2f4}button.active{background:#245b65;color:#fff;border-color:#245b65}button:focus-visible,input:focus-visible,textarea:focus-visible,select:focus-visible{outline:3px solid #de9f35;outline-offset:2px}main{display:grid;grid-template-columns:300px minmax(0,1fr);gap:20px;max-width:1450px;margin:20px auto;padding:0 20px}.sidebar{max-height:calc(100vh - 250px);overflow:auto;position:sticky;top:88px;align-self:start}.case{display:block;width:100%;text-align:left;margin-bottom:6px;padding:8px 10px;font-size:13px}.case small{display:block;color:#687586;font-size:11px}.case.active small{color:#d4e8ed}.card{background:#fff;border:1px solid #e0e5eb;border-radius:11px;padding:20px;margin-bottom:16px;overflow:hidden}h2{font-size:20px;margin:0 0 8px}h3{font-size:16px;margin:16px 0 6px}.muted{color:#697686;font-size:13px}.warning{padding:10px 14px;background:#fff4d9;border-radius:8px;color:#7b5011;margin:10px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f6f8fa;padding:12px;font-size:13px;line-height:1.7;border-radius:6px}table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:7px 8px;border-bottom:1px solid #e6ebee;text-align:left;vertical-align:top}th{color:#5c6b7a;background:#f7f9fa}.table{overflow:auto}textarea{width:100%;min-height:90px;padding:9px;border:1px solid #bec9d1;border-radius:6px;margin:8px 0}input{max-width:260px;padding:7px;border:1px solid #bac9d0;border-radius:6px}.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.verdict button{padding:6px 10px}.verdict button.sel-agree{background:#245b65;color:#fff}.verdict button.sel-revise{background:#a14b25;color:#fff}.verdict button.sel-uncertain{background:#8a6a1f;color:#fff}.footer{font-size:12px;color:#7b8796;margin:10px 0 30px;overflow-wrap:anywhere}details{margin:8px 0}summary{cursor:pointer;color:#245b65;font-weight:600}@media(max-width:850px){main{grid-template-columns:1fr;padding:0 10px}.sidebar{position:static;max-height:180px}.card{padding:15px}header{padding:18px}}
</style>
<header><h1>D02 角色／实体与表达类型：人审标注</h1>
<p>这是 120 条助手草稿的审阅页，不是模型成绩。请先读行动原文并独立判断，再展开 AI 草稿对照；不要默认草稿正确。</p>
<p>每题分别记录 M1（跨度／角色／实体）和 M2（表达类型／问题跨度）。修改和不确定必须写原因；导出文件只是待核对的人审声明，不是自动批准。</p></header>
<div class="bar"><span class="pill" id="batch"></span><span class="pill" id="progress"></span>
<label for="filter">筛选</label><select id="filter"><option value="all">全部</option><option value="train">train</option><option value="development">development</option><option value="calibration">calibration</option><option value="sealed">sealed</option><option value="api_first_output">API 自然首输出</option></select>
<label for="reviewer">审阅人</label><input id="reviewer" maxlength="80" placeholder="填写称呼">
<button id="export">导出审阅意见</button></div>
<div class="bar" role="status" id="storage">意见尚未记录；可分批审阅和导出。</div>
<main><nav class="sidebar" id="list" aria-label="样本列表"></nav><section id="detail"></section></main>
<script id="packet" type="application/json">__PACKET__</script>
<script>
'use strict';
const packet=JSON.parse(document.getElementById('packet').textContent);
const storageKey='jity-d02-human-review-'+packet.batch.samplesSha256+'-'+packet.batch.manifestSha256;
const byId=Object.fromEntries(packet.samples.map(s=>[s.sampleId,s]));
let saved={reviewer:'',decisions:{}},active=packet.samples[0].sampleId,storageOk=true,storageMsg='意见尚未记录；可分批审阅和导出。';
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n};
const isObj=x=>x!==null&&typeof x==='object'&&!Array.isArray(x);
function valid(id,d){const s=byId[id];return s&&isObj(d)&&d.sampleId===id&&['agree','revise','uncertain'].includes(d.m1)&&['agree','revise','uncertain'].includes(d.m2)&&Array.isArray(d.categories)&&d.categories.every(x=>typeof x==='string')&&typeof d.note==='string'&&(d.m1==='agree'&&d.m2==='agree'||d.note.trim())&&typeof d.recordedAt==='string'&&Number.isFinite(Date.parse(d.recordedAt))}
try{const raw=localStorage.getItem(storageKey);if(raw){const p=JSON.parse(raw);if(!isObj(p)||typeof p.reviewer!=='string'||!isObj(p.decisions)||!Object.entries(p.decisions).every(([id,d])=>valid(id,d)))throw Error('bad');saved={reviewer:p.reviewer,decisions:p.decisions};storageMsg='已恢复本浏览器中的意见；完成一批请导出备份。'}}catch(e){storageOk=false;storageMsg='无法读取本地保存；本页意见暂存内存，关闭会丢失。'}
function persist(){if(storageOk){try{localStorage.setItem(storageKey,JSON.stringify(saved));storageMsg='意见已保存在本浏览器；建议完成一批就导出备份。'}catch(e){storageOk=false;storageMsg='本地保存失败；请及时导出，关闭会丢失。'}}refresh()}
function refresh(){const ds=Object.values(saved.decisions);document.getElementById('progress').textContent='已记录 '+ds.length+' / '+packet.samples.length+' · M1 需改 '+ds.filter(d=>d.m1==='revise').length+' · M2 需改 '+ds.filter(d=>d.m2==='revise').length+' · 不确定 '+ds.filter(d=>d.m1==='uncertain'||d.m2==='uncertain').length;document.getElementById('storage').textContent=storageMsg}
function table(parent,head,rows){const wrap=el('div',undefined,'table'),t=el('table'),tr=el('tr');for(const h of head)tr.append(el('th',h));t.append(tr);for(const r of rows){const line=el('tr');for(const v of r)line.append(el('td',String(v)));t.append(line)}wrap.append(t);parent.append(wrap)}
function stepText(s,step){return s.text.slice(step.start,step.end)}
function kindName(k){return {character:'人物',item:'物品',location:'地点'}[k]||k}
function draft(s){const d=s.draft,r=d.roleAudit,e=d.expressionAudit,root=el('div');root.append(el('h3','AI 草稿：M1'),el('p','这是待审文本，不是答案。重点看跨度是否逐字一致、角色是否符合句义、状态是否把“没有角色”和“不知道是谁”分开。','muted'));
 const rows=[];for(const st of r.steps)for(const m of st.mentions){const ent=m.entityId?(s.world.entities[m.entityId]?.name||m.entityId):'';rows.push([st.stepId,m.surface+' ['+m.start+','+m.end+')',(m.roles||[]).join('/')||'（无公开角色）',(m.diagnosticRoles||[]).join('/')||'—',m.status,ent||(m.candidates||[]).join('/')||'—',m.bindingBasis])}
 table(root,['步骤','跨度','公开角色','诊断角色','状态','实体/候选','依据'],rows);
 root.append(el('h3','AI 草稿：M2'),el('p','标签：'+(e.label??'（弃答）')+'；弃答：'+(e.abstain?JSON.stringify(e.abstain):'无')));const issues=(e.issues||[]).map(i=>[i.code,i.scope,i.stepId||'',i.start===undefined?'':i.start+'-'+i.end,i.blocking?'阻断':'提示']);if(issues.length)table(root,['问题码','作用域','步骤','跨度','级别'],issues);else root.append(el('p','没有问题片段。这只表示 M2 草稿未发现表达类型问题，不代表 M1 角色或实体一定正确。'));
 root.append(el('h3','样本覆盖标签（不是 M2 问题码）'));root.append(el('p',(d.tags||[]).join('、'),'muted'));root.append(el('p','这些标签说明该样本覆盖的角色／场景；M2 是否有问题，只看上方 issues 表。','muted'));return root}
function draw(){const s=byId[active],old=saved.decisions[active],root=document.getElementById('detail');root.replaceChildren();
 const top=el('article',undefined,'card');top.append(el('h2',s.sampleId),el('p',s.scenarioGroup+' · '+s.split+' · '+s.source,'muted'));top.append(el('p','当前执行人：'+(s.world.entities[s.actorId]?.name||s.actorId)+'（'+s.actorId+'）'));
 top.append(el('h3','完整行动原文（偏移为 Unicode code point 半开区间）'));const pre=el('pre');let last=0;for(const st of s.steps){if(st.start>last)pre.append(document.createTextNode(s.text.slice(last,st.start)));const mark=el('span',stepText(s,st));mark.style.background='#eef4f7';pre.append(mark);pre.append(document.createTextNode(' ['+st.stepId+'] '));last=st.end}if(last<s.text.length)pre.append(document.createTextNode(s.text.slice(last)));top.append(pre);root.append(top);
 const world=el('article',undefined,'card');world.append(el('h2','实体登记'),el('p','程序只认这些 ID、名称、别名和类型；文本出现未登记对象要标未知。','muted'));table(world,['ID','类型','名称','别名'],Object.entries(s.world.entities).map(([id,e])=>[id,kindName(e.type),e.name,(e.aliases||[]).join('、')]));root.append(world);
 const blank=el('article',undefined,'card');blank.append(el('h2','先独立判断（再展开草稿）'),el('p','M1：每个提及的跨度是否逐字匹配？公开角色是否符合句义？未知/歧义/缺失是否分开？'),el('p','M2：整段是尝试、结果断言、非行动、混合还是不确定？问题片段在什么作用域？'));const det=el('details');det.append(el('summary','展开 AI 草稿并逐项对照'),draft(s));blank.append(det);root.append(blank);
 const review=el('article',undefined,'card');review.append(el('h2','审阅记录'),el('p','先选 M1/M2 结论；有修改或不确定时必须写原因和问题类别。','muted'));
 const cats=['跨度/切片','角色语义','实体绑定','执行人/主体','表达标签','问题作用域','数据缺失','其他'];const catBox=el('div',undefined,'row');const boxes=[];for(const c of cats){const lab=el('label');const cb=document.createElement('input');cb.type='checkbox';cb.checked=!!old?.categories?.includes(c);cb.onchange=()=>{if(old){old.categories=boxes.filter(x=>x.cb.checked).map(x=>x.name);old.recordedAt=new Date().toISOString();persist();list()}};lab.append(cb,document.createTextNode(' '+c));boxes.push({cb,name:c});catBox.append(lab)}review.append(catBox);
 const note=el('textarea');note.placeholder='写清哪一处、为什么错、应该怎样；修改/不确定必填。';note.value=old?.note||'';note.oninput=()=>{if(old){old.note=note.value;old.recordedAt=new Date().toISOString();persist()}};review.append(note);
 function verdictRow(key,label){const row=el('div',undefined,'row verdict');row.append(el('span',label));for(const [v,t] of [['agree','认可'],['revise','需修改'],['uncertain','不确定']]){const b=el('button',t,old?.[key]===v?'sel-'+v:'');b.onclick=()=>{if(!saved.decisions[active])saved.decisions[active]={sampleId:active,m1:'',m2:'',categories:[],note:'',recordedAt:new Date().toISOString()};const d=saved.decisions[active];d[key]=v;d.note=note.value;d.categories=boxes.filter(x=>x.cb.checked).map(x=>x.name);d.recordedAt=new Date().toISOString();if((d.m1==='revise'||d.m2==='revise'||d.m1==='uncertain'||d.m2==='uncertain')&&!d.note.trim()){alert('修改或不确定需要写原因。');d[key]='';}persist();draw();list()};row.append(b)}return row}
 review.append(verdictRow('m1','M1 角色/实体：'),verdictRow('m2','M2 表达类型：'));
 const nav=el('div',undefined,'row');const i=packet.samples.findIndex(x=>x.sampleId===active);for(const [d,t] of [[-1,'上一题'],[1,'下一题']]){const b=el('button',t);b.disabled=i+d<0||i+d>=packet.samples.length;b.onclick=()=>{active=packet.samples[i+d].sampleId;draw();list();window.scrollTo(0,0)};nav.append(b)}review.append(nav);root.append(review);
 root.append(el('div','批次 '+packet.batch.samplesSha256.slice(0,16)+' · '+packet.batch.sampleCount+' 条 · 导出只是待核对声明，不是正式签字。','footer'))}
function list(){const target=document.getElementById('list');target.replaceChildren();const f=document.getElementById('filter').value;for(const s of packet.samples){if(f!=='all'&&(f==='api_first_output'?s.source!==f:s.split!==f))continue;const d=saved.decisions[s.sampleId];const b=el('button',s.sampleId+(d?' · '+d.m1+'/'+d.m2:''),'case'+(s.sampleId===active?' active':''));b.append(el('small',s.split+' · '+s.source));b.onclick=()=>{active=s.sampleId;draw();list()};target.append(b)}}
document.getElementById('filter').onchange=()=>{const f=document.getElementById('filter').value,s=packet.samples.find(x=>f==='all'||(f==='api_first_output'?x.source===f:x.split===f));if(s){active=s.sampleId;draw();list()}};
document.getElementById('reviewer').value=saved.reviewer||'';document.getElementById('reviewer').oninput=e=>{saved.reviewer=e.target.value;persist()};
document.getElementById('export').onclick=()=>{if(!saved.reviewer.trim()){alert('请先填写审阅人称呼。');return}const ds=Object.values(saved.decisions);if(!ds.length){alert('请至少审阅一题。');return}const bad=ds.filter(d=>!valid(d.sampleId,d));if(bad.length){alert('有未完成的记录：请为每题选择 M1/M2 结论并补齐原因。');return}const out={schema:'jity-d02-human-review-claims-v1',reviewer:saved.reviewer.trim(),exportedAt:new Date().toISOString(),batch:packet.batch,decisions:ds.map(d=>({sampleId:d.sampleId,m1:d.m1,m2:d.m2,categories:d.categories,note:d.note,recordedAt:d.recordedAt})),verificationStatus:'unverified_export_pending_reconciliation',humanSemanticApproval:false};const a=el('a');const url=URL.createObjectURL(new Blob([JSON.stringify(out,null,2)+'\n'],{type:'application/json'}));a.href=url;a.download='d02-human-review-'+new Date().toISOString().replace(/[:.]/g,'-')+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);document.getElementById('storage').textContent='已发起导出；请检查下载文件。'};
document.getElementById('batch').textContent='120 条 · 20 组 · 批次 '+packet.batch.samplesSha256.slice(0,10);
document.getElementById('reviewer').value=saved.reviewer||'';refresh();draw();list();
</script></html>'''


def build():
    value = packet()
    OUT.mkdir(parents=True, exist_ok=True)
    embedded = json.dumps(value, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
    path = OUT / 'pilot-review.html'
    path.write_text(HTML.replace('__PACKET__', embedded), encoding='utf-8')
    (OUT / 'pilot-review-packet.json').write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'html': str(path), 'packet': str(OUT / 'pilot-review-packet.json'),
                      'samples': value['batch']['sampleCount'],
                      'samplesSha256': value['batch']['samplesSha256']}, ensure_ascii=False))


def reconcile(path):
    claims = json.loads(Path(path).read_text(encoding='utf-8'))
    current = packet()
    if claims.get('schema') != SCHEMA:
        raise SystemExit('不是 D02 人审导出格式')
    if not isinstance(claims.get('reviewer'), str) or not claims['reviewer'].strip():
        raise SystemExit('缺少审阅人称呼')
    if claims.get('batch') != current['batch']:
        raise SystemExit('批次哈希不匹配：请确认导出对应当前 samples/manifest/worlds')
    if claims.get('verificationStatus') != 'unverified_export_pending_reconciliation':
        raise SystemExit('导出不能自授审批状态')
    if claims.get('humanSemanticApproval') is not False:
        raise SystemExit('导出不能声明人审通过')
    decisions = claims.get('decisions')
    if not isinstance(decisions, list) or not decisions:
        raise SystemExit('没有审阅记录')
    valid_ids = {s['sampleId'] for s in current['samples']}
    seen = set()
    counts = {'agree': 0, 'revise': 0, 'uncertain': 0}
    rows = []
    for item in decisions:
        sid = item.get('sampleId')
        if sid not in valid_ids or sid in seen:
            raise SystemExit('未知或重复 sampleId: %r' % sid)
        seen.add(sid)
        for key in ('m1', 'm2'):
            if item.get(key) not in counts:
                raise SystemExit('非法 %s: %r' % (key, item.get(key)))
            counts[item[key]] += 1
        note = item.get('note', '')
        if not isinstance(note, str):
            raise SystemExit('note 必须是字符串')
        if (item['m1'] != 'agree' or item['m2'] != 'agree') and not note.strip():
            raise SystemExit('修改/不确定缺少原因: ' + sid)
        rows.append({'sampleId': sid, 'm1': item['m1'], 'm2': item['m2'],
                     'categories': item.get('categories', []), 'note': note})
    report = {
        'schema': 'jity-d02-human-review-reconciliation-v1',
        'reconciledAt': dt.datetime.now(dt.timezone.utc).isoformat(),
        'reviewerClaim': claims['reviewer'], 'batch': current['batch'],
        'reviewed': len(seen), 'missing': current['batch']['sampleCount'] - len(seen),
        'missingSampleIds': sorted(valid_ids - seen),
        'counts': counts, 'decisions': rows,
        'verificationStatus': 'unverified_export_pending_human_confirmation',
        'humanSemanticApproval': False, 'labelMutation': 'none',
        'note': '只核对导出与批次身份并汇总意见；不改标签、不训练、不声称人审通过。',
    }
    out = OUT / ('review-reconciliation-%s.json' % dt.datetime.now().strftime('%Y%m%dT%H%M%S'))
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('reviewed', 'missing', 'counts')}, ensure_ascii=False))
    print('wrote', out)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('build')
    rec = sub.add_parser('reconcile')
    rec.add_argument('file', type=Path)
    args = parser.parse_args()
    if args.command == 'build':
        build()
    else:
        reconcile(args.file)


if __name__ == '__main__':
    main()
