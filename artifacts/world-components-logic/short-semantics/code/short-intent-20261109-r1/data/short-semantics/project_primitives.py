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
'D02.3.verdict':['pass','reject'],'D02.3.role':['present','absent'],
'D02.4.check':['pass','fail'],'D02.5.check':['pass','fail'],'D03.1.relation':['target','none'],
'D03.2.verdict':['pass','reject'],'D05.1.edge':['present','absent'],
'D05.2.label':['achieved','partial','not_achieved'],'D05.4.verdict':['pass','reject'],
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


def project_annotations(rows):
    output=[];checks=[]
    for row in rows:
        if row['kind']!='annotation_only':continue
        component=row['component'];gold=json.loads(row['target']);derived=[]
        if component not in (NARROW_COMPOSITES | LIFE | UPDATE):continue
        def teach(task,payload):
            q=payload.get('semanticQuery',{});value=None
            if component=='D02.3':
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
        if assembled.status!='result' and not (isinstance(gold,dict) and gold.get('verdict')=='reject'):
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
        checks.append({'annotationId':row['exampleId'],'primitiveExamples':len(derived),'packagingStatus':assembled.status,
                       'scope':'author_reference_packaging_only_no_model'})
        output.extend(derived)
    return output,checks
