"""Prepare a complete paired review; never infer semantic success from loss."""
import argparse
import hashlib
import json
from pathlib import Path
import short_qwen_final_training as final


def prepare(path):
    q=final.q;plan,rows=final.verify(path);root=Path(path).parent
    record=q.common.read_json(root/'record.json')
    if record['status']!='completed_pending_semantic_review':raise ValueError('run incomplete')
    if record['planSha256']!=q.sha256_file(path):raise ValueError('record identity drift')
    if len(record['units'])!=len(plan['executionUnits']):raise ValueError('unit coverage')
    by_id={r['exampleId']:r for r in rows}
    previous_path=q.ART/'qwen-short-time-20261109-r5.assistant-review.json'
    previous=q.common.read_json(previous_path)
    old={r['rowId']:r for r in previous['reviews'] if r['arm']=='qwen_after'}
    reviews=[];seen=set();all_inputs={}
    for actual,expected in zip(record['units'],plan['executionUnits']):
        if actual['status']!='complete' or actual['unitId']!=expected['unitId']:raise ValueError('unit incomplete or reordered')
        if q.sha256_file(actual['resultPath'])!=actual['sha256']:raise ValueError('unit result changed')
        if expected['arm']=='qwen_train':continue
        predictions={p['exampleId']:p for p in q.common.read_json(actual['resultPath'])['predictions']}
        event_path=root/(expected['unitId']+'.events.jsonl')
        events=[json.loads(line) for line in event_path.read_text().splitlines()]
        events=[e['payload'] for e in events if e['name']=='qwen_generation_finished']
        if {e['exampleId'] for e in events}!=set(expected['exampleIds']) or len(events)!=len(expected['exampleIds']):raise ValueError('first output coverage')
        for e in events:
            if predictions[e['exampleId']]['rawCheckpoint']['sha256Payload']!=q.digest(e):raise ValueError('raw checkpoint drift')
            key=(expected['arm'],e['exampleId'])
            if key in seen:raise ValueError('duplicate first output')
            seen.add(key);row=by_id[e['exampleId']];packet=q.prompt_packet(row['component'],row['input'])
            if e['inputSha256']!=packet['inputSha256'] or e['messagesSha256']!=packet['messagesSha256']:raise ValueError('input identity drift')
            input_ids=q.digest(e['promptIds']);prior_ids=all_inputs.setdefault(e['exampleId'],input_ids)
            if prior_ids!=input_ids:raise ValueError('paired tokenization drift')
            raw=e.get('rawText','');raw_hash=hashlib.sha256(raw.encode()).hexdigest();prior=old[e['exampleId']]
            reuse=(e['status']=='result' and e['inputSha256']==prior['inputSha256'] and
                   e['messagesSha256']==prior['messagesSha256'] and raw_hash==prior['outputSha256Utf8'])
            reviews.append({'arm':expected['arm'],'rowId':e['exampleId'],'component':row['component'],
                'sourceGroup':row['sourceGroup'],'split':row['split'],'inputSha256':e['inputSha256'],
                'messagesSha256':e['messagesSha256'],'promptIdsSha256':input_ids,'rawText':raw,
                'rawTokenIds':e.get('rawTokenIds',[]),'outputSha256Utf8':raw_hash,'status':e['status'],
                'eosReached':bool(e.get('rawTokenIds') and e['rawTokenIds'][-1] in e.get('legalEosTokenIds',[])),
                'rawSource':{'path':str(event_path),'sha256':q.sha256_file(event_path)},
                'category':prior['category'] if reuse else 'incomplete' if e['status']!='result' else 'pending_review',
                'reasonZh':prior['reasonZh'] if reuse else e.get('reason'),
                'reuse':{'path':str(previous_path),'sha256':q.sha256_file(previous_path),'rowId':e['exampleId'],'arm':'qwen_after'} if reuse else None,
                'criticalErrors':None,'newCriticalComparedWithBaseline':None})
    if len(reviews)!=2*len(plan['evaluationExampleIds']):raise ValueError('evaluation coverage')
    result={'schema':'jity-qwen-final-paired-review-v1','runId':plan['runId'],
            'plan':{'path':str(path),'sha256':q.sha256_file(path)},
            'record':{'path':str(root/'record.json'),'sha256':q.sha256_file(root/'record.json')},
            'reviewer':'assistant_only','humanSigned':False,'formalAcceptance':False,
            'independentGeneralization':False,'webgpuEvidence':False,'reviews':reviews}
    out=root/'review-worklist.json';q.exclusive(out,result);return out


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('plan',type=Path)
    print(prepare(parser.parse_args().plan))
