"""Project assistant annotations into actual primitive bridge request shapes.

The oracle exists ONLY while authoring supervision. Runtime modules never import
this file or look up examples. Reference packaging checks do not score a model.
"""
import copy
import json
from run_pilot import digest
from short_contracts import result
from short_training import NARROW_COMPOSITES,compose_narrow
from short_heads_lifecycle import COMPONENTS as LIFE,assemble_lifecycle_head
from short_heads_updates import COMPONENTS as UPDATE,assemble_update_head

LABELS={
'D02.2.next':['fragment','end'],'D05.3.next':['fact','end'],
'D02.3.verdict':['pass','reject'],'D02.3.role':['present','absent'],
'D02.4.check':['pass','fail'],'D02.5.check':['pass','fail'],'D03.1.relation':['target','none'],
'D03.2.verdict':['pass','reject'],'D05.1.edge':['present','absent'],
'D05.2.label':['achieved','partial','not_achieved','incomplete'],'D05.4.verdict':['pass','reject'],
'D05.5.member':['include','exclude'],'U1.1.change':['change','keep'],'U3.1.status':['pending','achieved'],
'D06.P.review.verdict':['pass','reject'],'D04.1.next':['constraint','end'],'D04.1.covered':['covered','missing'],
'D01.1.kind':['locations','items','characters','end'],'D01.1.slot_next':['slot','end'],
'D01.2.relation':['under','above','beside','in_front_of','behind'],
'D01.4.next':['task','end'],'D07.1.next':['candidate','end'],
'D08.1.boundary':['elapsed','instant'],'D08.2.time.boundary':['elapsed','instant'],
'D08.1.unit':['second','minute','hour','day','month','year'],
'D08.2.time.unit':['second','minute','hour','day','month','year'],
'D08.2.next_kind':['normal','instant','linked','end'],'D08.2.actor':['include','exclude'],
'U1.2.slot_mode':['none','select'],'U1.2.relative_mode':['none','select'],
'U1.2.relation':['under','above','beside','in_front_of','behind'],'U1.2.audit':['pass','reject'],
'U2.1.next_op':['keep','remove','add','replace','end'],'U5.1.next_op':['keep','remove','add','replace','end'],
'U2.1.record_more':['more','end'],'U5.1.record_more':['more','end'],
'U2.1.audit':['pass','reject'],'U5.1.audit':['pass','reject'],
'D06.P.mapping.kind':['state','unchanged','transient','gap'],
'D06.P.mapping.more':['more','end'],'D06.P.mapping.audit':['pass','reject']}

# This is the full runtime primitive contract, including branches not exercised
# by any current authored scene. A zero-row task must remain visible in coverage.
REFERENCES = {
 'D01.1.protagonist','D01.2.parent','D01.2.container','D01.2.slot','D01.2.relative',
 'D01.4.parent','D02.4.issue_fragment','D02.5.issue_fragment','D07.1.character',
 'U1.2.container','U1.2.slot','U1.2.relative_entity','U2.1.record','U5.1.record',
 'D06.P.mapping.target'}
TEXT = {'D01.1.name','D01.1.slot_label','D01.3','D01.4.goal','D01.5',
 'D02.2.text','D04.1.text','D05.3.text','D07.1.text','D08.1.amount','D08.2.time.amount',
 'U2.2','U4.2','U5.2'}
NUMBERS = {'D01.6','U4.1.count','U6.1'}
DIRECT_LABELS = {'D02.1':['act','skip','incomplete'],'D07.2':['likely','unlikely'],
                 'D07.3':['related','unrelated']}


def runtime_catalog():
    return {**{name:{'kind':'label','labels':labels} for name,labels in {**LABELS,**DIRECT_LABELS}.items()},
            **{name:{'kind':'reference'} for name in REFERENCES},
            **{name:{'kind':'text'} for name in TEXT},
            **{name:{'kind':'number'} for name in NUMBERS}}


def catalog_coverage(rows):
    catalog=runtime_catalog();observed={row['component'] for row in rows if row['kind']!='annotation_only'}
    return {'runtimePrimitiveCount':len(catalog),'tasks':catalog,
            'untrainedMissingTasks':sorted(set(catalog)-observed),
            'notRuntimeTasks':sorted(observed-set(catalog)),
            'allRuntimeTasksHaveTrainingRows':all(any(r['component']==name and r['split']=='train' for r in rows) for name in catalog),
            'coverageMeaning':'presence of authored supervision only, not trained or semantically validated capability'}


def authored_audit_counterexamples(rows):
    """Explicit same-source review labels; never part of the runtime predictor."""
    out=[]
    for original in rows:
        task=original['component'];group=original['sourceGroup'];row=None
        if task=='U1.2.audit':
            row=copy.deepcopy(original)
            # The proposed position names the moved entity itself as container.
            position=row['input']['semanticQuery']['positions'][0]
            position['position']={'containerId':position['entityId']}
            reason='self_containment_position_is_invalid'
        elif task=='U2.1.audit' and group.endswith(':buoy'):
            row=copy.deepcopy(original)
            ops=row['input']['semanticQuery']['operations']
            for op in ops:
                if op['entityId']=='a':op.update(op='keep',recordIds=[])
                elif op['entityId']=='b':op.update(op='add',recordIds=[])
            reason='oil_fact_names_actor_a_not_companion_b'
        elif task=='U5.1.audit' and group.endswith(':swap'):
            row=copy.deepcopy(original)
            ops=row['input']['semanticQuery']['operations']
            for op in ops:
                if op['entityId']=='a':op.update(op='keep',recordIds=[])
                elif op['entityId']=='off':op.update(op='add',recordIds=[])
            reason='remote_character_has_no_experience_supporting_new_preference'
        elif task=='D06.P.mapping.audit' and group.endswith(':buoy'):
            row=copy.deepcopy(original)
            mappings=row['input']['semanticQuery']['mappings']
            with_targets=[x for x in mappings if x['targets']]
            if len(with_targets)<2:continue
            with_targets[0]['targets'],with_targets[1]['targets']=with_targets[1]['targets'],with_targets[0]['targets']
            reason='oil_and_unrepaired_wire_consequences_are_swapped'
        if row is None:continue
        row['exampleId']+=':authored-audit-reject';row['target']='reject'
        row['inputProvenance']='authored_counterexample_same_source'
        # Review explanation is metadata and must never enter model input.
        row['authorRationale']=reason
        row['contentSha256']=digest({k:v for k,v in row.items() if k!='contentSha256'})
        out.append(row)
    return out


def project_annotations(rows):
    output=[];checks=[]
    for row in rows:
        if row['kind']!='annotation_only':continue
        component=row['component'];gold=json.loads(row['target']);derived=[]
        if component not in (NARROW_COMPOSITES | LIFE | UPDATE):continue
        def teach(task,payload):
            q=payload.get('semanticQuery',{});value=None
            if component in ('D02.2','D05.3'):
                value=gold['kind'] if task.endswith('.next') else gold['text']
            elif component=='D02.3':
                if task.endswith('.verdict'):value=gold['verdict']
                else:
                    m=q['mention'];value='present' if any(r['role']==q['role'] and all(r[k]==m[k] for k in ('entityId','start','end')) for r in gold['references']) else 'absent'
            elif component in ('D02.4','D02.5'):
                value=gold['checks'][q['check']] if task.endswith('.check') else gold['issues'][0]['fragmentId']
            elif component=='D03.1':value=next(r['relation'] for r in gold if r['candidateId']==q['candidateId'])
            elif component in ('D03.2','D05.4','D06.P.review'):value=gold['verdict']
            elif component=='D04.1':
                if task.endswith('.next'):value='constraint' if not q['constraints'] else 'end'
                elif task.endswith('.text'):value=gold['constraint']
                else:value='covered' if q['sourceId'] in gold['threatSourceIds'] else 'missing'
            elif component=='D05.1':value='present' if any(e['sourceId']==q['sourceId'] and e['targetId']==q['targetId'] and e['kind']==q['relation'] for e in gold['relations']) else 'absent'
            elif component=='D05.2':value=next(x['label'] for x in gold['judgments'] if x['attemptId']==q['attemptId'])
            elif component=='D05.5':value='include' if q['memberId'] in next(f['memberIds'] for f in gold['facts'] if f['factId']==q['factId']) else 'exclude'
            elif component=='U1.1':value='change' if next(x['change'] for x in gold['decisions'] if x['entityId']==q['entityId']) else 'keep'
            elif component=='U3.1':value=next(x['label'] for x in gold['decisions'] if x['taskId']==q['taskId'])
            elif component=='U4.1':value=next(x['count'] for x in gold['needs'] if x['parentTaskId']==q['parentTaskId'])
            elif component=='D01.1':
                index=len(payload.get('proposedEntities',[]))
                if task.endswith('.kind'):value=gold['entities'][index]['kind'] if index<len(gold['entities']) else 'end'
                elif task.endswith('.name'):value=gold['entities'][index]['name']
                elif task.endswith('.slot_next'):
                    slots=gold['entities'][index].get('slots',[]);value='slot' if len(payload['proposedSlots'])<len(slots) else 'end'
                elif task.endswith('.slot_label'):value=gold['entities'][index]['slots'][len(payload['proposedSlots'])]
                elif task.endswith('.protagonist'):value=str(gold['protagonistIndex'])
            elif component=='D01.2':
                choice=gold[payload['entityId']]
                if task.endswith('.parent'):value=choice if choice is not None else '__none__'
                elif task.endswith('.container'):value=choice['containerId']
                elif task.endswith('.slot'):value=choice.get('slotId') or '__none__'
                elif task.endswith('.relative'):value=(choice.get('relativeTo') or {}).get('entityId','__none__')
                elif task.endswith('.relation'):value=choice['relativeTo']['relation']
            elif component=='D01.4':
                if task.endswith('.next'):value=gold['kind']
                elif task.endswith('.parent'):value=gold['parentTaskId'] or '__none__'
                else:value=gold['goal']
            elif component=='D07.1':
                if task.endswith('.next'):value=gold['kind']
                elif task.endswith('.character'):value=gold['characterId']
                else:value=gold['text']
            elif component in ('D08.1','D08.2'):
                current=gold if component=='D08.1' else gold[len(payload['proposedSegments'])] if len(payload['proposedSegments'])<len(gold) else None
                if task.endswith('.next_kind'):value=current['kind'] if current else 'end'
                elif task.endswith('.actor'):value='include' if payload['actorId'] in current['actorIds'] else 'exclude'
                else:
                    time=current if component=='D08.1' else current['timeAdvance']
                    if task.endswith('.boundary'):value=time['boundary']
                    elif task.endswith('.amount'):value=str(time['duration']['amount'])
                    else:value=time['duration']['unit']
            elif component=='U1.2':
                if task.endswith('.audit'):value='pass'
                else:
                    pos=next(r['position'] for r in gold['positions'] if r['entityId']==q['entityId'])
                    if task.endswith('.container'):value=pos['containerId']
                    elif task.endswith('.slot_mode'):value='select' if pos.get('slotId') is not None else 'none'
                    elif task.endswith('.slot'):value=pos['slotId']
                    elif task.endswith('.relative_mode'):value='select' if pos.get('relativeTo') is not None else 'none'
                    elif task.endswith('.relative_entity'):value=pos['relativeTo']['entityId']
                    elif task.endswith('.relation'):value=pos['relativeTo']['relation']
            elif component in ('U2.1','U5.1'):
                if task.endswith('.audit'):value='pass'
                else:
                    ops=[x for x in gold['operations'] if x['entityId']==q['entityId']]
                    finished=sum(x['entityId']==q['entityId'] for x in q['operations'])
                    current=ops[finished] if finished<len(ops) else None
                    if task.endswith('.next_op'):value=current['op'] if current else 'end'
                    elif task.endswith('.record_more'):value='more' if len(q['selectedRecordIds'])<len(current['recordIds']) else 'end'
                    elif task.endswith('.record'):value=current['recordIds'][len(q['selectedRecordIds'])]
            elif component=='D06.P.mapping':
                if task.endswith('.audit'):value=gold['verdict']
                else:
                    current=next(x for x in gold['mappings'] if x['factId']==q['factId'])
                    if task.endswith('.kind'):value=current['kind']
                    elif task.endswith('.more'):value='more' if len(q['selectedTargets'])<len(current['targets']) else 'end'
                    elif task.endswith('.target'):value='candidate:'+digest(current['targets'][len(q['selectedTargets'])])
            if value is None:raise ValueError('missing authored primitive: '+task)
            kind='label' if task in LABELS else 'number' if task=='U4.1.count' else 'reference' if task.endswith(('.issue_fragment','.protagonist','.parent','.container','.slot','.relative','.character','.relative_entity','.record','.target')) else 'text'
            if kind=='reference' and value not in [c['id'] for c in payload['candidates']]:raise ValueError('author reference outside bridge candidates')
            item={k:copy.deepcopy(v) for k,v in row.items() if k not in ('target','input','contentSha256','kind','labels','outputCodec')}
            item.update(exampleId=row['exampleId']+':primitive:'+str(len(derived)+1),component=task,kind=kind,
              outputCodec='text' if kind=='text' else 'scalar',input=copy.deepcopy(payload),target=value,
              derivedFromAnnotation=row['exampleId'],derivedFromSha256=row['contentSha256'])
            if kind=='label':item['labels']=LABELS[task]
            item['contentSha256']=digest(item);derived.append(item)
            return result(value)
        if component in LIFE:assembled=assemble_lifecycle_head(teach,component,row['input'])
        elif component in UPDATE:assembled=assemble_update_head(teach,component,row['input'])
        else:assembled=result(compose_narrow(teach,component,row['input']))
        # Deliberate rejection examples may be rejected by a strict bridge after
        # all supervision needed for their reject label has been captured.
        expected_gap=(component=='D06.P.mapping' and row.get('inputProvenance')=='authored_same_source_interface_gap_diagnostic'
                      and row.get('expectedProgramCompletion')=='incomplete' and row.get('expectedProgramReason')=='interface_gap'
                      and any(item.get('kind')=='gap' for item in gold.get('mappings',[]))
                      and 'interface_gap' in str(assembled.reason))
        if assembled.status!='result' and not expected_gap and not (isinstance(gold,dict) and gold.get('verdict')=='reject'):
            raise ValueError(row['exampleId']+': author bridge failed: '+str(assembled.reason))
        if assembled.status=='result':
            def normalized(value):
                if isinstance(value,dict):return {k:normalized(v) for k,v in value.items() if not (k in ('slotId','relativeTo') and v is None)}
                if isinstance(value,list):return [normalized(v) for v in value]
                return value
            actual=normalized(assembled.value);expected=normalized(gold)
            if component in ('D02.4','D02.5'):
                actual['issues']=sorted({x['fragmentId'] for x in actual['issues']})
                expected['issues']=sorted({x['fragmentId'] for x in expected['issues']})
            if actual!=expected:raise ValueError(row['exampleId']+': primitive packaging differs from authored semantic fields')
        checks.append({'annotationId':row['exampleId'],'primitiveExamples':len(derived),'packagingStatus':assembled.status,'expectedInterfaceGap':expected_gap,
                       'scope':'author_reference_packaging_only_no_model'})
        output.extend(derived)
    return output,checks
