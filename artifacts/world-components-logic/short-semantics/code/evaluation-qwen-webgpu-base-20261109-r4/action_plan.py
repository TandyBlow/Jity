"""D-only action-plan annotation preparation. No inference, training or game writes.

Plan drafts are authored examples, not learned decisions or reviewed truth.
This module checks structure/identity only; it never selects a live action.
"""
from __future__ import annotations
import argparse
import copy
import html
import json
from pathlib import Path

from lab import build_model_input,canonical_bytes,guard_case,sha256_file
from pilot_codec import pack,unpack
from run_pilot import digest
import m01_probe

ROOT=Path(__file__).resolve().parents[2]
BASE=Path(__file__).resolve().parent
ART=ROOT/'artifacts/world-components-logic'
DATA=BASE/'data/action-plan'
BATCH='d-action-plan-old10-r1'
PROTOCOL=ROOT/'design/world-engine-reports/components-logic/action-plan-protocol.md'
BASE_COMMIT='195997b644745964111dde071482f16c0ceb850c'
ENTITY_KINDS={'character':'characters','item':'items','place':'places'}
ROLES=('objects','tools','destinations','recipients')
# Annotation authoring only. These entries are never consulted by a model port
# or live action selector; all ten remain unreviewed and ineligible for training.
SPECS={
 '01':{'kind':'act','basis':['/advance','/world/characters/0/tasks/0','/world/places/1'],
       'steps':[('推开',[('item','item_2')],[],[],[],None),
                ('进入',[],[],[('place','loc_b')],[],None),
                ('递交',[('item','item_1')],[],[],[('character','p2')],None)]},
 '02':{'kind':'act','basis':['/advance','/world/characters/0/tasks/0','/world/items'],
       'steps':[('敲击',[('item','item_1')],[('item','item_2')],[],[('character','p2')],'可以开始靠岸')]},
 '03':{'kind':'skip','basis':['/advance','/world/places/1','/world/characters/0/tasks/0'],'steps':[]},
 '04':{'kind':'skip','basis':['/advance','/world/items','/world/characters/0/tasks/0'],'steps':[]},
 '05':{'kind':'act','basis':['/advance/intentStatus','/world/characters/0/tasks/0','/world/places/1','/world/items'],
       'steps':[('覆盖',[('item','item_1')],[('item','item_2')],[],[],None)]},
 '06':{'kind':'skip','basis':['/advance/intentStatus','/world/characters/0/tasks/0','/world/places/1'],'steps':[]},
 '07':{'kind':'act','basis':['/world/characters/1/tasks/0','/world/characters/1/personality','/world/places/1'],
       'steps':[('伸手稳住',[('item','item_1')],[],[],[],None)]},
 '08':{'kind':'act','basis':['/advance/intentStatus','/world/characters/1/tasks/0','/world/places/1','/world/items'],
       'steps':[('稳住',[('item','item_1')],[('item','item_2')],[],[],None)]},
 '09':{'kind':'skip','basis':['/advance/intentStatus','/world/characters/1/tasks/0','/world/places/1'],'steps':[]},
 '10':{'kind':'skip','basis':['/advance/intentStatus','/world/characters/1/tasks/0','/world/places/1'],'steps':[]},
}

# Separate reference wording for the expression component, also unreviewed.
# No runtime renderer or model input uses these annotation targets.
EXPRESSION_DRAFTS={
 '01':'程青尝试推开侧门，进入值班室，将交接钥匙递给闻雪。',
 '02':'罗舟尝试用铃锤敲击铜铃，向许栖传达可以开始靠岸的信号。',
 '05':'纪遥尝试用遮水布覆盖纸卷箱。',
 '07':'陈砚尝试伸手稳住秤盘。',
 '08':'魏澜尝试用固定楔稳住沙漏。',
}


def source_rows():
    rows,review=m01_probe.dataset()
    rows=[r for r in rows if r['case']['task']=='D02']
    if len(rows)!=10:raise ValueError('expected ten original D02 sources')
    return rows,review


def lookup(case):
    world=build_model_input(case)['world'];result={}
    for kind,field in ENTITY_KINDS.items():
        for entity in world[field]:
            key=(kind,entity['id'])
            if key in result:raise ValueError('duplicate entity identity')
            result[key]=entity
    return result


def resolve_pointer(value,path):
    if not isinstance(path,str) or not path.startswith('/') or '~' in path:
        raise ValueError('expected canonical source JSON pointer')
    node=value
    for part in path[1:].split('/'):
        if isinstance(node,list):
            if not part.isdigit() or str(int(part))!=part:raise ValueError('noncanonical list index')
            try:node=node[int(part)]
            except IndexError as error:raise ValueError('source pointer missing') from error
        elif isinstance(node,dict) and part in node:node=node[part]
        else:raise ValueError('source pointer missing')
    return node


def validate_candidate(case,plan):
    """Identity, fields, references and attempt shape; NOT causal/semantic approval."""
    if not guard_case(case)['shouldCall'] or case['task']!='D02':raise ValueError('invalid action source')
    if not isinstance(plan,dict) or set(plan)!={'actorId','kind','mode','basis','steps'}:raise ValueError('closed draft plan fields required')
    if plan['actorId']!=case['input']['actorId'] or plan['mode']!='attempt':raise ValueError('actor or attempt identity mismatch')
    if plan['kind'] not in ('act','skip') or not isinstance(plan['steps'],list):raise ValueError('invalid plan kind/steps')
    if (plan['kind']=='skip')!= (len(plan['steps'])==0):raise ValueError('skip must have no steps; act needs steps')
    if not isinstance(plan['basis'],list) or not plan['basis'] or any(not isinstance(p,str) for p in plan['basis']):raise ValueError('source evidence references required')
    if len(set(plan['basis']))!=len(plan['basis']):raise ValueError('duplicate source evidence')
    for path in plan['basis']:resolve_pointer(case['input'],path)
    entities=lookup(case)
    for step in plan['steps']:
        if not isinstance(step,dict) or set(step)!={'verb',*ROLES,'utterance'}:raise ValueError('closed step fields required')
        if not isinstance(step['verb'],str) or not step['verb'].strip():raise ValueError('open lexical verb required')
        if step['utterance'] is not None and (not isinstance(step['utterance'],str) or not step['utterance'].strip()):raise ValueError('invalid intended utterance')
        for role in ROLES:
            if not isinstance(step[role],list):raise ValueError('entity references must be lists')
            seen=set()
            for ref in step[role]:
                if not isinstance(ref,dict) or set(ref)!={'kind','id'} or not all(isinstance(ref[k],str) for k in ref):raise ValueError('typed entity reference required')
                key=(ref['kind'],ref['id'])
                if key not in entities or key in seen:raise ValueError('unknown/duplicate entity reference')
                if role=='recipients' and key[0]!='character':raise ValueError('recipient must reference a character')
                seen.add(key)
    return {'structurallyValid':True,'semanticApproved':False,'sourceInputSha256':digest(case['input'])}


def bind_candidate(case,plan):
    verdict=validate_candidate(case,plan)
    return {'schema':'jity-d-action-plan-binding-v1','sourceCaseId':case['caseId'],
            'sourceInputSha256':verdict['sourceInputSha256'],'plan':copy.deepcopy(plan),
            'planSha256':digest(plan),'structurallyValid':True,'semanticApproved':False}


def planner_input(case):
    value=build_model_input(case);payload=pack(value)
    if unpack(payload)!=value:raise ValueError('planner input lost facts')
    return {'sourceInputSha256':digest(value),'payload':payload,'containsPlanLabels':False,
            'coverage':'all_original_stage_input','modelImplemented':False}


def realizer_preview(case,bound):
    if bound!=bind_candidate(case,bound['plan']):raise ValueError('stale/altered plan binding')
    if bound['plan']['kind']=='skip':return {'wouldCallExpression':False,'reason':'skip_no_expression','modelExecuted':False}
    entities=lookup(case);refs=[];seen=set()
    keys=[('character',bound['plan']['actorId'])]
    keys += [(r['kind'],r['id']) for s in bound['plan']['steps'] for role in ROLES for r in s[role]]
    for key in keys:
        if key not in seen:
            refs.append({'kind':key[0],'id':key[1],'name':entities[key]['name']});seen.add(key)
    # The realizer only expresses an already proposed plan. It cannot establish
    # whether that plan was appropriate for the full world; planner is unbuilt.
    payload={'actorId':bound['plan']['actorId'],'mode':'attempt','steps':copy.deepcopy(bound['plan']['steps']),'lexicon':refs}
    return {'wouldCallExpression':True,'sourceInputSha256':bound['sourceInputSha256'],'planSha256':bound['planSha256'],
            'payload':payload,'planOrigin':'assistant_annotation_draft_not_model_prediction',
            'allowedForModelUse':False,'plannerFullCoverageRequired':True,'modelExecuted':False}


def build_drafts():
    rows,review=source_rows();drafts=[]
    for row in rows:
        case=row['case'];spec=SPECS[case['caseId'][-2:]]
        steps=[]
        for verb,objects,tools,destinations,recipients,utterance in spec['steps']:
            step={'verb':verb,'utterance':utterance}
            for role,values in zip(ROLES,(objects,tools,destinations,recipients)):
                step[role]=[{'kind':k,'id':i} for k,i in values]
            steps.append(step)
        candidate={'actorId':case['input']['actorId'],'kind':spec['kind'],'mode':'attempt',
                   'basis':list(spec['basis']),'steps':steps}
        validate_candidate(case,candidate)
        if candidate['kind']!=row['label']:raise ValueError('draft differs from original act/skip constraint')
        drafts.append({'schema':'jity-d-action-plan-annotation-v1','annotationId':'plan-'+case['caseId'],
            'sourceCaseId':case['caseId'],'sourceGroup':case['sourceGroup'],'sourceInputSha256':digest(case['input']),
            'originalRole':row['role'],'originalConstraintReviewSha256':row['reviewDraftSha256'],
            'oldReviewScope':'act_skip_and_action_constraints_only_not_this_new_plan',
            'author':'assistant','labelStatus':'draft_pending_human_review','trainingEligible':False,
            'purpose':'existing_exposed_development_annotation_draft','planDraft':candidate,'planSha256':digest(candidate),
            'expressionDraft':EXPRESSION_DRAFTS.get(case['caseId'][-2:]),
            'expressionSha256':digest(EXPRESSION_DRAFTS.get(case['caseId'][-2:]))})
    return drafts,review


def packet_identity(drafts):return digest({'batchId':BATCH,'annotations':drafts})


def review_status(drafts,claims=None):
    if claims is None:return {'newPlanLabelsReviewed':0,'missingPlanReviews':len(drafts),'exploratoryFitExportAllowed':False,'formalEvaluationAllowed':False}
    if not isinstance(claims,dict) or set(claims)!={'schema','batchId','packetSha256','reviewer','decisions'}:raise ValueError('new-plan review claims required; original case review cannot approve new plan labels')
    if claims['schema']!='jity-d-action-plan-review-claims-v1' or claims['batchId']!=BATCH or claims['packetSha256']!=packet_identity(drafts):raise ValueError('review batch identity mismatch')
    if not isinstance(claims['reviewer'],str) or not claims['reviewer'].strip() or claims['reviewer'].strip().lower() in ('assistant','ai','model'):raise ValueError('human reviewer claim required; identity is not authenticated by this tool')
    expected={r['annotationId']:r for r in drafts};seen=set();agreed=0
    if not isinstance(claims['decisions'],list):raise ValueError('review decision list required')
    for item in claims['decisions']:
        if not isinstance(item,dict) or set(item)!={'annotationId','annotationSha256','decision','note'}:raise ValueError('invalid plan review decision')
        key=item['annotationId']
        if key not in expected or key in seen or item['annotationSha256']!=digest(expected[key]):raise ValueError('review annotation identity mismatch')
        if item['decision'] not in ('agree','needs_change','uncertain') or not isinstance(item['note'],str):raise ValueError('invalid review verdict')
        if item['decision']!='agree' and not item['note'].strip():raise ValueError('non-agreement requires evidence note')
        seen.add(key);agreed+=item['decision']=='agree'
    return {'newPlanLabelsReviewed':len(seen),'agreedPlanLabels':agreed,'missingPlanReviews':len(drafts)-len(seen),
            'exploratoryFitExportAllowed':agreed==len(drafts),'formalEvaluationAllowed':False,
            'reviewClaimsOnlyNotAuthenticatedIdentity':True}


def fitting_packet(drafts,claims):
    status=review_status(drafts,claims)
    if not status['exploratoryFitExportAllowed']:raise ValueError('new action-plan labels are not fully reviewed; no fitting export')
    originals={r['case']['caseId']:r for r in source_rows()[0]};fit=[];retained=[]
    for row in drafts:
        original=originals[row['sourceCaseId']];case=original['case']
        if (digest(case['input'])!=row['sourceInputSha256'] or row['originalRole']!=original['role']
                or row['sourceGroup']!=case['sourceGroup'] or row['originalConstraintReviewSha256']!=original['reviewDraftSha256']):raise ValueError('source input/group/split changed')
        if row['planSha256']!=digest(row['planDraft']) or row['expressionSha256']!=digest(row['expressionDraft']):raise ValueError('stale plan/expression content hash')
        if (row['planDraft']['kind']=='skip' and row['expressionDraft'] is not None
                or row['planDraft']['kind']=='act' and (not isinstance(row['expressionDraft'],str) or not row['expressionDraft'].strip())):raise ValueError('expression target/skip mismatch')
        bound=bind_candidate(case,row['planDraft'])
        entry={'annotationId':row['annotationId'],'sourceGroup':row['sourceGroup'],'originalRole':row['originalRole'],
               'sourceCase':case,'plannerInput':planner_input(case),'targetPlan':bound['plan'],'targetExpressionDraft':row['expressionDraft'],
               'realizerAnnotationInput':realizer_preview(case,bound)}
        (fit if row['originalRole']=='fit' else retained).append(entry)
    return {'schema':'jity-d-action-plan-reviewed-development-fit-proposal-v1','batchId':BATCH,
            'reviewClaimsSha256':digest(claims),'packetSha256':packet_identity(drafts),'fit':fit,'retainedDevelopment':retained,
            'newIndependentTrainingGroups':0,'round1TrainingQuota':0,'formalEvaluationAllowed':False,
            'trainingExecuted':False,'trainingExecutionAuthorizedByThisFile':False}


def build_materials():
    drafts,review=build_drafts();sources={r['case']['caseId']:r['case'] for r in source_rows()[0]}
    data=b''.join(canonical_bytes(r)+b'\n' for r in drafts)
    manifest={'schema':'jity-d-action-plan-source-manifest-v1','batchId':BATCH,'sourceHead':BASE_COMMIT,
        'sourceReview':review,'draftFileSha256':__import__('hashlib').sha256(data).hexdigest(),'packetSha256':packet_identity(drafts),
        'protocolSha256':sha256_file(PROTOCOL),'preparationCodeSha256':sha256_file(Path(__file__)),
        'annotations':[{'annotationId':r['annotationId'],'annotationSha256':digest(r),'sourceGroup':r['sourceGroup'],
            'sourceInputSha256':r['sourceInputSha256'],'originalRole':r['originalRole']} for r in drafts],
        'sourceIndependence':'unverified_existing_D_development_only','newIndependentTrainingGroups':0,
        'round1TrainingQuota':0,'trainingEligible':False,'formalEvaluationAllowed':False}
    sizes=[]
    for r in drafts:
        c=sources[r['sourceCaseId']];p=planner_input(c);bound=bind_candidate(c,r['planDraft']);preview=realizer_preview(c,bound)
        sizes.append({'annotationId':r['annotationId'],'kind':r['planDraft']['kind'],
            'fullPlannerPayloadBytes':len(canonical_bytes(p['payload'])),
            'realizerPreviewBytes':len(canonical_bytes(preview['payload'])) if preview['wouldCallExpression'] else None,
            'expressionCalled':False,'sourceRole':r['originalRole']})
    summary={'schema':'jity-d-action-plan-preparation-summary-v1','date':'2026-11-04','batchId':BATCH,
        'stage':'L3 action-plan preparation; no new model execution','scope':'contract_and_old_source_annotation_drafts_only',
        'expressionDrafts':sum(r['expressionDraft'] is not None for r in drafts),
        'draftSourceGroups':len(drafts),'actDrafts':sum(r['planDraft']['kind']=='act' for r in drafts),'skipDrafts':sum(r['planDraft']['kind']=='skip' for r in drafts),
        'originalRoles':{r['sourceCaseId']:r['originalRole'] for r in drafts},'review':review_status(drafts),
        'preparedDataset':str((DATA/'drafts.jsonl').relative_to(ROOT)),'plannerModelImplemented':False,'realizerTrained':False,
        'trainingSteps':0,'modelInferenceCalls':0,'newIndependentTrainingGroups':0,'round1TrainingQuota':0,
        'formalEvaluationAllowed':False,'semanticQualityApproved':False,'fullRequest500msStatus':'unverified','local50msHardGate':False,
        'lastModelRun':'action-focus-dev42-20261104-r2','packetSha256':packet_identity(drafts),'inputSizes':sizes,
        'erratum':{'correctFitExamples':['dev-d02-01','dev-d02-07'],
            'correctRetainedDevelopmentExamples':['dev-d02-03','dev-d02-05'],
            'scope':'L3-11/12 role descriptions only; original roles, numeric results and historical bytes unchanged'}}
    return summary,{DATA/'drafts.jsonl':data,DATA/'source-manifest.json':canonical_bytes(manifest)+b'\n',
        ART/'l3-13-action-plan-preparation-summary.json':(json.dumps(summary,ensure_ascii=False,indent=2)+'\n').encode(),
        ART/'l3-13-action-plan-preparation.html':render(summary,drafts,sources).encode()}


def render(summary,drafts,sources):
    esc=lambda v:html.escape(str(v))
    parts=['''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>L3 动作计划准备</title><style>body{margin:0;background:#f4f6f8;color:#20313e;font:16px/1.7 system-ui}main{max-width:1100px;margin:auto;padding:24px}section{background:white;padding:22px;border-radius:12px;margin:20px 0}table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:10px;text-align:left;border-bottom:1px solid #ddd}.scroll{overflow:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere}.warn{color:#a7352e}</style><main><p>D / L3 · 2026-11-04 · 数据与组件准备</p><h1>先决定具体做什么，再把计划说成一句话</h1><section><h2>这次完成了什么？</h2><p>定义了可校验的动作计划：谁来做、准备尝试什么、涉及哪个物品/工具/地点/人物、依据哪些原事实。准备10组旧D02场景的AI计划草稿（5行动、5跳过），另有5份短表达参考草稿，对应8拟合/2保留开发，源输入及旧审核意见保持原样。</p><p class="warn">这是准备材料，不是模型答案。新动作计划标签尚未人工复核，当前可导出的拟合包为0；没有训练、模型推理或500ms新成绩。原42题初审仍有效，不要求重审原题。</p><p>结构合法只说明ID/字段/引用有效，不说明动作合理。模型仍须负责语义选择；程序不能抄任务充当动作。完整世界继续进入拟议选择器，表达器的短输入只用于表达已经明确的计划；当前选择器未实现，不能拿短输入大小当完整覆盖或速度通过。</p></section><section><h2>分工与下一步</h2><ol><li>程序按ID提供完整事实和当前人物，检查引用及来源身份。</li><li>专用小模型选择具体动作/引用计划；需要新监督数据，尚未训练。</li><li>小生成器将计划表达为尝试，不添加成功结果或控制其他人；尚未训练。</li><li>原文交回现有目标分析，程序继续掌握准入、骰点、状态应用和保存。</li></ol><p>候选排序只能检验给定候选内的判断，开放候选生成仍须保留并验证；语义计划不能被固定动作清单替代。下一批先完善计划标签和独立训练来源，冻结训练/计算配置后分开验证选择与表达，再合起来测真实500ms。</p></section><section><h2>用途说明更正</h2><p>原始分组：01、07是fit；03、05是retained_development。L3-11/12曾写成01/03拟合、05/07保留，且错误地把最初协议的“0107曾拟合”称为笔误，这些说明有误。原始模型记录中的角色一直正确，数值不受影响；此处更正，历史原件字节保留。</p></section>''']
    import review_io
    criteria={r['caseId']:r['review']['draftExpected'] for r in review_io.build_packet()['cases']}
    for row in drafts:
        c=sources[row['sourceCaseId']];bound=bind_candidate(c,row['planDraft']);preview=realizer_preview(c,bound)
        entities=lookup(c);actor=entities[('character',row['planDraft']['actorId'])]
        labels={'pending':'待处理新输入','consumed':'已消费旧输入','expired':'已过期旧输入'}
        tasks='；'.join(t['text']+'（'+t['status']+'）' for t in actor['tasks'])
        parts.append(f'<section><h2>{esc(row["sourceCaseId"])} · {esc(row["originalRole"])}</h2><p><strong>AI计划草稿／未复核／不可训练。</strong></p><p>当前人物：{esc(actor["name"])}（{esc(actor["id"])}）<br>该人物任务：{esc(tasks)}<br>玩家原文：{esc(c["input"]["advance"]["inputText"])}<br>输入状态：{esc(labels[c["input"]["advance"]["intentStatus"]])}</p>')
        if row['planDraft']['kind']=='skip':parts.append('<p>计划草稿：不采取新的动作；后续表达器不调用。是否合理仍按场景核对。</p>')
        else:
            parts.append('<p>以下均是<strong>准备尝试</strong>，没有宣布执行成功：</p><div class="scroll"><table><tr><th>动作词</th><th>对象</th><th>工具</th><th>目的地</th><th>接收人</th><th>拟传达内容</th></tr>')
            for step in row['planDraft']['steps']:
                names=lambda role:'、'.join(entities[(r['kind'],r['id'])]['name'] for r in step[role]) or '无'
                cells=[step['verb'],*[names(role) for role in ROLES],step['utterance'] or '无']
                parts.append('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in cells)+'</tr>')
            parts.append('</table></div>')
        if row['expressionDraft'] is not None:parts.append('<p><strong>短表达参考草稿（AI写作，不是模型输出）：</strong>'+esc(row['expressionDraft'])+'</p>')
        old=criteria[c['caseId']]
        parts.append('<p>原题已审约束（只作核对依据，不自动批准新计划）：'+esc('；'.join(old['mustRespect']))+'<br>原题禁止项：'+esc('；'.join(old['forbidden']))+'</p>')
        parts.append(f'<details><summary>结构化计划、完整原场景与表达输入草稿</summary><pre>{esc(json.dumps({"planDraft":row["planDraft"],"originalInput":c["input"],"realizerPreview":preview},ensure_ascii=False,indent=2))}</pre></details><p>绑定源SHA：{esc(row["sourceInputSha256"])}</p></section>')
    parts.append(f'<section><details><summary>准备状态、来源及输入字节大小（不是计时）</summary><pre>{esc(json.dumps(summary,ensure_ascii=False,indent=2))}</pre></details><p><a href="l3-13-action-plan-preparation-summary.json">机器状态</a> · <a href="../../experiments/world-components-logic/data/action-plan/drafts.jsonl">全部计划草稿</a> · <a href="../../experiments/world-components-logic/data/action-plan/source-manifest.json">来源/哈希清单</a> · <a href="l3-12-action-focus-results.html">上批真实实测</a></p></section></main></html>')
    return ''.join(parts)


def prepare_materials(write=False):
    summary,files=build_materials()
    for path,raw in files.items():
        if path.exists() and path.read_bytes()!=raw:raise ValueError('prepared material differs; preserve earlier batch: '+str(path))
        if not write and not path.exists():raise ValueError('prepared material missing: '+str(path))
    if write:
        for path,raw in files.items():
            path.parent.mkdir(parents=True,exist_ok=True)
            if not path.exists():
                with path.open('xb') as stream:stream.write(raw)
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--check',action='store_true');g.add_argument('--write-new',action='store_true');a=p.parse_args()
    s=prepare_materials(write=a.write_new)
    print(json.dumps({k:s[k] for k in ('scope','draftSourceGroups','trainingSteps','modelInferenceCalls','formalEvaluationAllowed')},ensure_ascii=False))

if __name__=='__main__':main()
