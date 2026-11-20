"""Human-only review of complete round1 contexts; never approves execution."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

from lab import canonical_bytes, load_jsonl, sha256_file
from prepare_review import HTML
import prepare_round1_inputs as inputs

ROOT = inputs.ROOT
OUT = ROOT / 'artifacts/world-components-logic/l3-3-input-review.html'


def sha(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def build_packet():
    files, summary = inputs.build_files()
    for path, raw in files.items():
        if path.read_bytes() != raw:
            raise ValueError(f'补充输入版本不匹配，不能生成审阅批次：{path.name}')
    cards, cases, supplements, chains, probes = inputs.build_materials()
    rubrics = {r['caseId']: r for r in load_jsonl(inputs.SOURCE / 'rubric-drafts.jsonl')}
    supplements = {r['caseId']: r for r in supplements}
    checks = {r['caseId']: r for r in load_jsonl(inputs.DATA / 'input-checks.jsonl')}
    rows = []
    for card in cards:
        cid = card['caseId']
        material = {
            'sourceCard': copy.deepcopy(card['input']['sourceCard']),
            'taskCases': [{'case': c, 'supplement': supplements[c['caseId']],
                           'check': checks[c['caseId']]} for c in cases
                          if supplements[c['caseId']]['sourceCardId'] == cid],
            'chainPlans': [c for c in chains if c['sourceCardId'] == cid],
            'auxiliaryProbes': [p for p in probes if p['sourceCardId'] == cid],
        }
        review = copy.deepcopy(rubrics[cid])
        review['draftExpected']['mustRespect'] += [
            '新增世界、任务、个性和历史前缀与原卡一致且足够判断；补充设定须人工确认。',
            '阶段输入只含当时可见事实；守卫损坏不补猜，短链计划不等于已执行。',
        ]
        rows.append({**card, 'input': material, 'inputSha256': sha(material),
                     'review': review, 'reviewSha256': sha(review),
                     'guard': {'reason': 'human_context_review_only'}})
    return {'schema': 'jity-d-human-review-packet-v1',
            'materialKind': 'expanded_input_draft', 'revision': 1,
            'inputSha256': sha256_file(inputs.DATA / 'task-inputs.jsonl'),
            'reviewDraftSha256': sha256_file(inputs.DATA / 'context-supplements.jsonl'),
            'provenanceSha256': sha256_file(inputs.DATA / 'input-manifest.json'),
            'summary': summary, 'cases': rows,
            'hashScope': 'Per-card input binds source facts, all cases/contexts/checks, chain plans and probes. Manifest binds all six data files and original rubrics.',
            'modelExecutionAuthorized': False}


VIEW = r'''function showWorld(parent,w){
const n=id=>{const p=[...w.characters,...w.items,...w.places].find(p=>p.id===id);return p?p.name+' ['+id+']':id};
parent.append(el('h3','完整世界与新增设定'),el('p','时间：'+JSON.stringify(w.time)));
table(parent,['地点','环境事实'],w.places.map(p=>[n(p.id),p.appearance||'无补充']));
table(parent,['人物 / 位置','任务全文','个性 / 理智','外貌'],w.characters.map(p=>[n(p.id)+' / '+n(typeof p.position==='string'?p.position:p.position.containerId),p.tasks.map(t=>t.text+'（'+t.status+'）').join('；'),p.personality.join('；')+' / '+p.sanity,p.appearance]));
table(parent,['物品 / 位置','当前物性与状态'],w.items.map(i=>[n(i.id)+' / '+n(typeof i.position==='string'?i.position:i.position.containerId),i.appearance||'无补充']));}
function details(parent,title,value){const d=el('details');d.append(el('summary',title),el('pre',JSON.stringify(value,null,2)));parent.append(d)}
function draw(){const c=byId[active],x=c.input,r=c.review,e=r.draftExpected,old=saved.decisions[c.caseId],root=document.getElementById('detail');root.replaceChildren();const name=id=>id;
const top=el('article',undefined,'card');top.append(el('h2',taskNames[c.task]),el('p',r.sourceNote),el('div',c.caseId+' · '+(c.split==='development'?'开发草稿':'封存候选，未冻结'),'muted'),el('h3','原场景卡'),el('p',x.sourceCard.facts),el('p',x.sourceCard.question),el('div','本页审阅原卡、判断标准和完整补充上下文。旧页面的认可不会自动套用。本页只有待审材料，未运行模型。','warning'));root.append(top);
for(const v of x.taskCases){const a=el('article',undefined,'card');a.append(el('h2',v.case.caseId===c.caseId?'当前阶段完整输入':'同源骰点对照：'+v.case.caseId),el('p','程序结构检查：'+v.check.guard.reason+'；仅表示调用形状，不代表运行许可。'));
showWorld(a,v.case.input.world);bullets(a,'本次补充的设定与假设',v.supplement.assumptions);
const stage={...v.case.input};delete stage.world;details(a,'查看当前阶段全部输入',stage);details(a,'查看冻结顺序、身份及原始损坏记录',v.supplement);root.append(a)}
for(const p of x.chainPlans){const a=el('article',undefined,'card');a.append(el('h2','短链初始状态与后续计划'),el('div','动态执行器尚未实现。目标、反应与结果必须来自后续真实预测。','warning'));showWorld(a,p.initialCase.input.world);bullets(a,'新增设定',p.newAssumptions);details(a,'查看完整初态、行动顺序和动态计划',p);root.append(a)}
if(x.auxiliaryProbes.length){const a=el('article',undefined,'card');a.append(el('h2','同源异常检查'));details(a,'缺输入和取消检查的完整材料',x.auxiliaryProbes);root.append(a)}
'''


def render(packet):
    if packet.get('materialKind') != 'expanded_input_draft':
        raise ValueError('必须是完整上下文审阅批次')
    start = HTML.index('function draw(){')
    end = HTML.index("const rubric=el('article'", start)
    html = HTML[:start] + VIEW + HTML[end:]
    replacements = {
        'L3 新题审阅 · 非叙事组件': 'L3 完整输入审阅 · 非叙事组件',
        '帮我们确认：这道题和判断标准合理吗？': '确认原题和新增的完整输入是否合理',
        '这里是 L3 的开发题草稿，全部由 AI 新写，尚待人工核对。': '这里包含 90 张卡的完整上下文草稿及短链初态。新增事实、任务与个性需要一并复核。',
        '40 个来源组 / 42 个测试项': '完整输入草稿 1 · 90 张卡 · 开发 44 / 封存候选 46',
        '</select>': '<option value="CHAIN">短链初态与计划</option></select>',
        "D05:'共同结果：全组一起结算'}": "D05:'共同结果：全组一起结算',CHAIN:'短链初态与计划'}",
        "'程序是否应调用模型：'+(e.expectedCall?'应调用':'应停止或复用已确认内容')+'。当前结构检查：'+(guardNames[c.guard.reason]||c.guard.reason)": "'本卡的新增事实、阶段资料和判据均待复核；具体调用形状见上方各输入的结构检查。'",
        '全部仍为开发材料，非封存验收集。': '本批是待审完整上下文；封存候选禁止用于训练、调参或本次小批诊断。',
    }
    for old, new in replacements.items():
        if html.count(old) != 1:
            raise ValueError('共享模板接入点改变，须复核完整输入视图')
        html = html.replace(old, new)
    return html.replace('__PACKET__', canonical_bytes(packet).decode().replace('<', '\\u003c'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--write-new', action='store_true')
    args = parser.parse_args()
    raw = render(build_packet()).encode('utf-8')
    if OUT.exists() and OUT.read_bytes() != raw:
        raise ValueError('已有完整输入审阅页版本不同，拒绝覆盖')
    if args.check and not OUT.exists():
        raise ValueError('缺少完整输入审阅页')
    if args.write_new and not OUT.exists():
        with OUT.open('xb') as stream:
            stream.write(raw)
    print('完整输入审阅页身份一致；未代签人审或运行模型。')


if __name__ == '__main__':
    main()
