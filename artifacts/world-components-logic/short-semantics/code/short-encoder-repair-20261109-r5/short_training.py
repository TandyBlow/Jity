"""Trainable short semantic tasks; no model download, rule answer, or silent truncation.

This module imports neural dependencies only in explicitly executed train/infer
paths. Draft supervision is exploratory evidence, never human-reviewed truth.
"""
from __future__ import annotations

import copy
import json
import math
import os
import time
from pathlib import Path

from lab import canonical_bytes, sha256_file
from run_pilot import digest

KINDS = {'label', 'reference', 'number', 'text', 'annotation_only'}
SPLITS = {'train', 'development', 'test'}
END = '【结束】'


def training_schedule(rows, config):
    """Freeze task/label/source-balanced exposure without using held-out rows.

    Classification targets (and end/text for generation) alternate within each
    task. Source groups alternate within each target bucket before another row
    from the same source is selected. Repeated examples keep their identities.
    """
    rows=[r for r in rows if r['split']=='train' and r['kind']!='annotation_only']
    if not rows:raise ValueError('no training rows for schedule')
    buckets={}
    for row in rows:
        category=(str(row['target']) if row['kind']=='label' else
                  ('multiple_candidates' if len(row['input']['candidates'])>1 else 'single_candidate') if row['kind']=='reference' else
                  ('end' if row['target']==END else 'text') if row['kind']=='text' else 'value')
        buckets.setdefault(row['component'],{}).setdefault(category,{}).setdefault(row['sourceGroup'],[]).append(row)
    components=sorted(buckets);counts={c:0 for c in components};selected=[];exposure={c:{} for c in components}
    for index in range(config['steps']*config['batchSize']):
        component=components[index%len(components)];offset=counts[component];categories=sorted(buckets[component])
        category=categories[offset%len(categories)];sources=buckets[component][category];groups=sorted(sources)
        bucket_visit=offset//len(categories);source=groups[bucket_visit%len(groups)]
        candidates=sources[source];row=candidates[(bucket_visit//len(groups))%len(candidates)]
        selected.append(row['exampleId']);counts[component]+=1
        exposure[component][category]=exposure[component].get(category,0)+1
    missing={c:sorted(set(buckets[c])-set(exposure[c])) for c in components if set(buckets[c])-set(exposure[c])}
    if missing:raise ValueError('training budget leaves task/observed-label buckets untrained:'+str(missing))
    return {'exampleIds':selected,'sha256':digest(selected),'taskExposures':counts,
            'observedLabelExposures':exposure,'policy':'task_then_label_or_reference_choice_then_source_v2'}


def validate_rows(rows, *, require_all_splits=True):
    """Validate provenance and group isolation before looking at a model."""
    if not isinstance(rows, list) or not rows:
        raise ValueError('empty supervision packet')
    groups, seen, content_groups = {}, set(), {}
    for row in rows:
        required = {'exampleId','sourceGroup','split','component','kind','input',
                    'target','annotationStatus','sourceStatus','contentSha256'}
        if not required <= set(row):
            raise ValueError('missing supervision fields')
        if row['exampleId'] in seen:
            raise ValueError('duplicate example identity')
        seen.add(row['exampleId'])
        if row['kind'] not in KINDS or row['split'] not in SPLITS:
            raise ValueError('invalid task kind/split')
        if row['annotationStatus'] not in ('assistant_draft','human_reviewed'):
            raise ValueError('unknown annotation provenance')
        if row['sourceStatus'] not in ('unverified','verified'):
            raise ValueError('unknown source verification')
        group = row['sourceGroup']
        if group in groups and groups[group] != row['split']:
            raise ValueError('source group crosses splits, including name variants')
        groups[group] = row['split']
        payload = {k:v for k,v in row.items() if k != 'contentSha256'}
        if digest(payload) != row['contentSha256']:
            raise ValueError('supervision content hash mismatch')
        full_input = digest(row['input'])
        if full_input in content_groups and content_groups[full_input] != group:
            raise ValueError('identical full context falsely registered as new source')
        content_groups[full_input] = group
        if not isinstance(row['input'],dict):
            raise ValueError('complete task input required')
        # D01 begins with a brief; later tasks carry full world/draft context.
        context = row['input'].get('context',row['input'])
        if not row['component'].startswith('D01.') and 'world' not in context and 'world' not in row['input']:
            raise ValueError('full world context required')
        forbidden = {'expected','gold','draftTarget','reviewDraft','humanReview','answer'}
        def check_input(value):
            if isinstance(value,dict):
                if any(k in forbidden or k.replace('_','').replace('-','').lower().startswith(('expected','gold','futureanswer','drafttarget','reviewdraft','rubric','answer')) for k in value):
                    raise ValueError('answer/review leakage into model input')
                for item in value.values(): check_input(item)
            elif isinstance(value,list):
                for item in value: check_input(item)
        check_input(row['input'])
        target = row['target']
        if row['kind'] == 'number' and (type(target) is not int or not 0 <= target <= 100):
            raise ValueError('numeric supervision must be an integer in 0..100')
        if row['kind'] == 'label':
            labels = row.get('labels')
            if not labels or len(set(labels)) != len(labels) or target not in labels:
                raise ValueError('label outside frozen vocabulary')
        if row['kind'] == 'reference':
            candidates = row['input'].get('candidates')
            if not candidates or not all(isinstance(c,dict) and c.get('id') for c in candidates):
                raise ValueError('reference supervision requires all registered candidates')
            ids = [c['id'] for c in candidates]
            if len(ids) != len(set(ids)) or target not in ids:
                raise ValueError('reference target invalid or duplicate candidate')
        if row['kind']=='text' and row.get('outputCodec') not in ('text','fragment_or_end','fact_or_end'):
            raise ValueError('short generators cannot train aggregate JSON codecs')
        if row['kind'] == 'text' and (not isinstance(target,str) or not target.strip()):
            raise ValueError('short text or explicit END is required')
    if require_all_splits and set(groups.values()) != SPLITS:
        raise ValueError('train/development/test source groups required')
    return {'examples':len(rows),'sourceGroups':len(groups),
            'splitGroups':{s:sum(v == s for v in groups.values()) for s in sorted(SPLITS)},
            'assistantDrafts':sum(r['annotationStatus']=='assistant_draft' for r in rows),
            'humanReviewed':sum(r['annotationStatus']=='human_reviewed' for r in rows),
            'sourceVerified':sum(r['sourceStatus']=='verified' for r in rows),
            'semanticIndependence':'not_established_by_hashes'}


def task_specs(rows):
    specs = {}
    for row in rows:
        spec = {'kind':row['kind'],'outputCodec':row.get('outputCodec','scalar')}
        if row['kind'] == 'label': spec['labels'] = row['labels']
        if row['component'] in specs and specs[row['component']] != spec:
            raise ValueError('inconsistent component supervision schema')
        specs[row['component']] = spec
    return specs


def complete_tokens(tokenizer, text, limit, *, require_eos=False, vocab_size=None):
    ids = tokenizer.encode(text, add_special_tokens=True, truncation=False)
    if not ids or len(ids) > limit:
        raise ValueError('complete context/target exceeds frozen token limit; no truncation')
    if vocab_size is not None and any(type(i) is not int or i<0 or i>=vocab_size for i in ids):raise ValueError('token id outside frozen model vocabulary')
    if require_eos and ids[-1] != tokenizer.eos_token_id:
        raise ValueError('missing EOS in complete target')
    return ids


def input_text(component, payload):
    envelope={'component':component,'context':payload};prefix=''
    if component in ('D02.2.text','D04.1.text'):
        context=payload.get('context',{})
        identity=payload.get('memberId') if component=='D04.1.text' else context.get('actorId')
        characters=context.get('world',{}).get('initial',{}).get('characters',{})
        person=characters.get(identity)
        if isinstance(person,dict) and isinstance(person.get('name'),str):
            executor={'id':identity,'name':person['name'],'role':'reactor' if component=='D04.1.text' else 'actor'}
            prefix=canonical_bytes({'currentExecutor':executor}).decode('utf-8')+'\n'
    return prefix+canonical_bytes(envelope).decode('utf-8')


def encode_complete(torch, model, tokenizer, component, payload, config, checkpoint):
    """All atomic facts reach the encoder; no label-based retrieval or cache."""
    from fact_windows import make_windows
    _, windows = make_windows(payload, tokenizer, component, config['encoderTokenLimit'])
    pieces, weights = [], []
    for index, window in enumerate(windows):
        event = {'component':component,'windowIndex':index,'inputIds':window['inputIds'],
                 'tokenTypeIds':window['tokenTypeIds'],'factIds':window['factIds']}
        checkpoint('encoder_forward_started',event)
        begin = time.perf_counter()
        ids = torch.tensor([window['inputIds']],dtype=torch.long)
        types = torch.tensor([window['tokenTypeIds']],dtype=torch.long)
        with torch.no_grad():
            hidden = model(input_ids=ids,token_type_ids=types,
                           attention_mask=torch.ones_like(ids)).last_hidden_state
        pieces.append(hidden.mean(dim=1).squeeze(0)); weights.append(window['payloadTokens'])
        checkpoint('encoder_forward_settled',{**event,'elapsedMs':(time.perf_counter()-begin)*1000})
    if not pieces or sum(weights) <= 0:
        raise ValueError('incomplete encoder coverage')
    return sum(v*w for v,w in zip(pieces,weights))/sum(weights)


def build_heads(torch, width, specs):
    """Reference head scores candidate-conditioned context, not a fixed ID vocabulary."""
    heads = {}
    for component,spec in specs.items():
        if spec['kind'] in ('text','annotation_only'): continue
        size = len(spec['labels']) if spec['kind']=='label' else 101 if spec['kind']=='number' else 1
        heads[component] = torch.nn.Linear(width*(3 if spec['kind']=='reference' else 1),size)
    return heads


def head_logits(torch, head, spec, context, candidates=None):
    if spec['kind'] != 'reference': return head(context).reshape(1,-1)
    if not candidates: raise ValueError('complete candidate features required')
    features = torch.stack([torch.cat((context,c,context*c)) for c in candidates])
    return head(features).reshape(1,-1)


def class_index(row):
    if row['kind']=='number': return row['target']
    if row['kind']=='label': return row['labels'].index(row['target'])
    return [c['id'] for c in row['input']['candidates']].index(row['target'])


def prepare_features(torch,model,tokenizer,rows,config,checkpoint):
    features = {}
    for row in rows:
        context = encode_complete(torch,model,tokenizer,row['component'],row['input'],config,checkpoint)
        candidates = None
        if row['kind']=='reference':
            candidates = [encode_complete(torch,model,tokenizer,row['component']+':candidate',
                                          c,config,checkpoint) for c in row['input']['candidates']]
        features[row['exampleId']] = (context,candidates)
    return features


def evaluate_heads(torch,model,tokenizer,heads,rows,specs,config,checkpoint):
    outputs = []
    for row in rows:
        begin=time.perf_counter()
        checkpoint('head_prediction_started',{'exampleId':row['exampleId'],'component':row['component'],'split':row['split']})
        # Each measured inference re-encodes its entire actual input. Training
        # feature reuse is never reported as inference latency.
        context,candidates = prepare_features(torch,model,tokenizer,[row],config,checkpoint)[row['exampleId']]
        with torch.no_grad():
            logits=head_logits(torch,heads[row['component']],specs[row['component']],context,candidates)
        values=logits.squeeze(0).tolist()
        if not all(math.isfinite(v) for v in values): raise ValueError('nonfinite head logits')
        index=int(logits.argmax(dim=1).item())
        value = index if row['kind']=='number' else row['labels'][index] if row['kind']=='label' else row['input']['candidates'][index]['id']
        output={'exampleId':row['exampleId'],'sourceGroup':row['sourceGroup'],'split':row['split'],
                'component':row['component'],'input':row['input'],'rawLogits':values,'output':value,
                'draftTarget':row['target'],'exactDraftMatch':value==row['target'],
                'semanticStatus':'pending_human_review','elapsedMs':(time.perf_counter()-begin)*1000}
        reference=checkpoint('head_prediction',output)
        outputs.append({k:v for k,v in output.items() if k not in ('input','rawLogits')}|{'rawCheckpoint':reference})
    return outputs


def train_heads(torch,model,tokenizer,rows,config,destination,checkpoint):
    """Real frozen encoder + learned classifier/pointer/integer heads."""
    from m01_probe import tensor_hash
    rows=[r for r in rows if r['kind'] in ('label','reference','number')]; specs=task_specs(rows)
    train=[r for r in rows if r['split']=='train']
    if not train or not specs: raise ValueError('no encoder training tasks')
    for component in specs:
        if not any(r['component']==component for r in train): raise ValueError('untrained task head forbidden')
    for p in model.parameters(): p.requires_grad_(False)
    model.eval(); base_hash=tensor_hash(model.state_dict())
    heads=build_heads(torch,model.config.hidden_size,specs)
    initial_head_hashes={c:tensor_hash(h.state_dict()) for c,h in heads.items()}
    parameters=[p for head in heads.values() for p in head.parameters()]
    optimizer=torch.optim.AdamW(parameters,lr=config['learningRate'],weight_decay=config['weightDecay'])
    # Full-context features may be reused only during fit, bound to this frozen
    # run/model/tokenizer/input; evaluation below always performs real forwards.
    schedule=training_schedule(train,config);by_id={r['exampleId']:r for r in train}
    # Fit only the preregistered sampled examples; each retains its full context.
    # Held-out inference still covers every registered example below.
    selected=[by_id[key] for key in dict.fromkeys(schedule['exampleIds'])]
    features=prepare_features(torch,model,tokenizer,selected,config,checkpoint)
    losses=[];exposures={component:0 for component in specs};data_gradient_steps={component:0 for component in specs}
    label_gradient_exposures={component:{} for component in specs}
    for step in range(config['steps']):
        batch=[by_id[key] for key in schedule['exampleIds'][step*config['batchSize']:(step+1)*config['batchSize']]]
        for row in batch:exposures[row['component']]+=1
        checkpoint('training_step_started',{'step':step+1,'exampleIds':[r['exampleId'] for r in batch]})
        optimizer.zero_grad(set_to_none=True)
        loss=sum(torch.nn.functional.cross_entropy(
            head_logits(torch,heads[r['component']],specs[r['component']],*features[r['exampleId']]),
            torch.tensor([class_index(r)],dtype=torch.long)) for r in batch)/len(batch)
        if not torch.isfinite(loss): raise ValueError('nonfinite head loss')
        loss.backward()
        nonzero=[component for component in {r['component'] for r in batch}
                 if any(p.grad is not None and bool(torch.any(p.grad!=0)) for p in heads[component].parameters())]
        for component in nonzero:data_gradient_steps[component]+=1
        for row in batch:
            if row['component'] in nonzero and row['kind']=='label':
                counts=label_gradient_exposures[row['component']];counts[row['target']]=counts.get(row['target'],0)+1
        norm=torch.nn.utils.clip_grad_norm_(parameters,config['maxGradNorm'])
        if not torch.isfinite(norm): raise ValueError('nonfinite head gradient')
        optimizer.step();losses.append(float(loss.detach()))
        checkpoint('training_step_settled',{'step':step+1,'loss':losses[-1],'gradientNorm':float(norm),'nonzeroDataGradientComponents':sorted(nonzero)})
    if tensor_hash(model.state_dict())!=base_hash: raise ValueError('encoder base changed')
    changed={c:tensor_hash(h.state_dict())!=initial_head_hashes[c] for c,h in heads.items()}
    weights={component:head.state_dict() for component,head in heads.items()}
    destination.mkdir(parents=True,exist_ok=False);path=destination/'heads.pt'
    with path.open('xb') as stream:
        torch.save(weights,stream);stream.flush();os.fsync(stream.fileno())
    saved_hash=sha256_file(path)
    restored=build_heads(torch,model.config.hidden_size,specs)
    loaded=torch.load(path,map_location='cpu',weights_only=True)
    for component,head in restored.items():
        head.load_state_dict(loaded[component],strict=True)
        if tensor_hash(head.state_dict())!=tensor_hash(heads[component].state_dict()):
            raise ValueError('head reload differs')
    checkpoint('head_checkpoint_reloaded',{'path':str(path),'sha256':saved_hash,'specs':specs})
    trained={c for c in specs if changed[c] and data_gradient_steps[c]>0}
    predictions=evaluate_heads(torch,model,tokenizer,restored,[r for r in rows if r['split']!='train' and r['component'] in trained],specs,config,checkpoint)
    return {'steps':len(losses),'losses':losses,'checkpoint':{'path':str(path),'sha256':saved_hash},
            'specs':specs,'sourceWeightsUnchanged':True,'predictions':predictions,
            'trainedHeadComponents':sorted(trained),'headParameterChanged':changed,'componentGradientExposures':exposures,
            'componentNonzeroDataGradientSteps':data_gradient_steps,'componentLabelDataGradientExposures':label_gradient_exposures,
            'trainingSchedule':schedule,'semanticQualityApproved':False}


def train_generator(torch,model,tokenizer,rows,config,destination,checkpoint):
    """77M independent short generation task, sharing the established LoRA loop."""
    from plan_training import (install_lora,base_state,fit_encoded_adapter,save_reload_adapter)
    from m01_probe import tensor_hash
    rows=[r for r in rows if r['kind']=='text']
    train=[r for r in rows if r['split']=='train']
    if not train: raise ValueError('no short text training supervision')
    components={r['component'] for r in rows}
    if components!={r['component'] for r in train}:raise ValueError('generator component without train supervision')
    exposure={c:0 for c in components};by_id={r['exampleId']:r['component'] for r in train}
    def training_checkpoint(name,payload):
        if name=='training_step_settled':
            for identity in training_checkpoint.active:exposure[by_id[identity]]+=1
        elif name=='training_step_started':training_checkpoint.active=payload['annotationIds']
        checkpoint(name,payload)
    training_checkpoint.active=[]
    source_hash=tensor_hash(model.state_dict())
    forward_counts={'top':0,'encoder':0}
    def counted(name):
        def increment(*_):forward_counts[name]+=1
        return increment
    hooks=[model.register_forward_pre_hook(counted('top')),model.get_encoder().register_forward_pre_hook(counted('encoder'))]
    install_lora(torch,model,config['rank'],config['alpha'])
    examples=[]
    for row in train:
        examples.append({'annotationId':row['exampleId'],'sourceGroup':row['sourceGroup'],
          'inputIds':complete_tokens(tokenizer,input_text(row['component'],row['input']),config['maxInputTokens'],vocab_size=model.config.vocab_size),
          'labels':complete_tokens(tokenizer,row['target'],config['maxTargetTokens'],require_eos=True,vocab_size=model.config.vocab_size)})
    schedule=training_schedule(train,config)
    losses=fit_encoded_adapter(torch,model,examples,tokenizer.pad_token_id,
                               {**config,'allowGroupedExamples':True,'exampleSchedule':schedule['exampleIds']},training_checkpoint)
    if not all(exposure.values()):raise ValueError('untrained generator task: '+','.join(k for k,v in exposure.items() if not v))
    identity=save_reload_adapter(torch,model,destination,source_hash,checkpoint)
    predictions=[]
    for row in [r for r in rows if r['split']!='train']:
        start=time.perf_counter()
        ids=complete_tokens(tokenizer,input_text(row['component'],row['input']),config['maxInputTokens'],vocab_size=model.config.vocab_size)
        checkpoint('generation_started',{'exampleId':row['exampleId'],'input':row['input'],'inputIds':ids})
        with torch.no_grad():
            tokens=model.generate(input_ids=torch.tensor([ids]),attention_mask=torch.ones((1,len(ids)),dtype=torch.long),
                do_sample=False,num_beams=1,max_new_tokens=config['maxNewTokens'])[0].tolist()
        eos=tokenizer.eos_token_id in tokens[1:]
        raw=tokenizer.decode(tokens,skip_special_tokens=True)
        output={'exampleId':row['exampleId'],'sourceGroup':row['sourceGroup'],'split':row['split'],
                'component':row['component'],'input':row['input'],'inputIds':ids,'rawTokenIds':tokens,
                'rawText':raw,'completion':'result' if eos else 'incomplete','error':None if eos else 'truncated',
                'draftTarget':row['target'],'exactDraftMatch':eos and raw==row['target'],
                'semanticStatus':'pending_human_review','elapsedMs':(time.perf_counter()-start)*1000}
        reference=checkpoint('generation_output',output)
        predictions.append({k:v for k,v in output.items() if k not in ('input','inputIds','rawTokenIds')}|{'rawCheckpoint':reference})
    if tensor_hash(base_state(model))!=source_hash: raise ValueError('generator base changed')
    for hook in hooks:hook.remove()
    checkpoint('generator_forward_accounting',forward_counts)
    return {'steps':len(losses),'losses':losses,'checkpoint':identity,'predictions':predictions,
            'sourceWeightsUnchanged':True,'actualForwardCalls':forward_counts,'trainedComponents':sorted(exposure),'componentGradientExposures':exposure,'trainingSchedule':schedule,'semanticQualityApproved':False}


def load_neural(torch,role,directory,config):
    """One explicit tokenizer/derived-encoder loading path for fit and inference."""
    from transformers import AutoModel,AutoTokenizer,T5ForConditionalGeneration,T5Tokenizer
    torch.set_num_threads(config['threads'])
    if config.get('promptCodec')!='complete_json_executor_binding_v2':raise ValueError('prompt codec requires its frozen implementation')
    if role=='encoder':
        if config.get('encoderPooling') is not False:raise ValueError('unused pooler is not part of this derived encoder identity')
        tokenizer=AutoTokenizer.from_pretrained(directory,local_files_only=True,trust_remote_code=False)
        model=AutoModel.from_pretrained(directory,local_files_only=True,trust_remote_code=False,weights_only=True,add_pooling_layer=False).float().eval()
        layers=config['encoderLayers']
        if layers!=[0,1] or len(model.encoder.layer)<2:raise ValueError('unregistered MiniRBT derived layer selection')
        model.encoder.layer=torch.nn.ModuleList([model.encoder.layer[i] for i in layers])
        model.config.num_hidden_layers=len(layers)
    else:
        if config['generatorTokenizer']!={'extra_ids':0,'legacy':True}:raise ValueError('tokenizer option drift')
        tokenizer=T5Tokenizer.from_pretrained(directory,local_files_only=True,**config['generatorTokenizer'])
        model=T5ForConditionalGeneration.from_pretrained(directory,local_files_only=True,trust_remote_code=False,weights_only=True).float().eval()
    return model,tokenizer


class LocalSemanticProvider:
    """Real trained local task backend for ModelSession; untrained tasks fail closed.

    A registry binds each primitive task to its trained checkpoint and codec.
    Short text is only wrapped, never rewritten. Aggregate outputs are assembled
    by programs from trained primitive outputs; there is no JSON generation fallback.
    """
    def __init__(self, manifest, *, checkpoint=None, retain_observations=True):
        self.manifest=copy.deepcopy(manifest);self.checkpoint=checkpoint or (lambda *_:None)
        if type(retain_observations) is not bool:raise ValueError('observation retention flag must be boolean')
        self.loaded={};self.observations=[];self.manifest_hash=digest(manifest)
        self.retain_observations=retain_observations;self.primitive_calls=0
        if manifest.get('schema')!='jity-d-short-trained-provider-v1':
            raise ValueError('trained provider manifest required')
        if not manifest.get('datasetSha256') or not manifest.get('codeSha256'):
            raise ValueError('missing trained identity')
        for component,task in manifest.get('tasks',{}).items():
            if task['kind']=='annotation_only':continue
            if task['kind']=='text' and task.get('outputCodec') not in ('text','fragment_or_end','fact_or_end'):
                raise ValueError('aggregate JSON generation is not an active semantic backend')
            role='generator' if task['kind']=='text' else 'encoder'
            model=manifest.get('models',{}).get(role,{})
            if component in model.get('trainedComponents',[]) and model.get('taskSpecs',{}).get(component)!=task:
                raise ValueError('trained task/vocabulary/codec identity mismatch')

    def predict_many(self,requests):
        """Complete batch envelope, ordered replies; currently sequential forwards.

        Loaded immutable weights are shared, encoder features/output caches are
        disabled. This is not claimed as tensor-batched inference or a speedup.
        """
        if not isinstance(requests,list):raise ValueError('request batch required')
        started=time.perf_counter();before=self.primitive_calls
        answers=[self(component,payload) for component,payload in requests]
        self.checkpoint('batch_finished',{'requests':len(requests),'primitiveCalls':self.primitive_calls-before,
          'elapsedMs':(time.perf_counter()-started)*1000,'execution':'sequential_shared_weights','featureCache':False})
        return answers

    def _load(self,role):
        if role in self.loaded:return self.loaded[role]
        import torch
        from transformers import AutoModel,AutoTokenizer,T5ForConditionalGeneration,T5Tokenizer
        from m01_probe import tensor_hash
        from plan_training import install_lora,restore_adapter
        spec=self.manifest['models'][role]
        if spec.get('trainingSteps',0)<=0:raise ValueError('untrained checkpoint')
        path=Path(spec['checkpoint']['path'])
        if not path.is_absolute():path=Path(__file__).resolve().parents[2]/path
        if sha256_file(path)!=spec['checkpoint']['sha256']:raise ValueError('checkpoint byte identity mismatch')
        for file in spec['files']:
            if sha256_file(Path(spec['directory'])/file['path'])!=file['observedSha256']:
                raise ValueError('model or tokenizer byte identity mismatch')
        begin=time.perf_counter()
        model,tokenizer=load_neural(torch,role,spec['directory'],self.manifest['config'])
        heads=None
        state=torch.load(path,map_location='cpu',weights_only=True)
        if role=='encoder':
            heads=build_heads(torch,model.config.hidden_size,spec['taskSpecs'])
            if set(heads)!=set(state):raise ValueError('trained head coverage mismatch')
            for component,head in heads.items():head.load_state_dict(state[component],strict=True);head.eval()
        else:
            install_lora(torch,model,self.manifest['config']['rank'],self.manifest['config']['alpha'])
            restore_adapter(model,state)
        self.checkpoint('request_model_load',{'role':role,'elapsedMs':(time.perf_counter()-begin)*1000})
        self.loaded[role]=(torch,model,tokenizer,heads)
        return self.loaded[role]

    def __call__(self,component,payload):
        from short_contracts import result,incomplete
        from lab import _parse_json
        if digest(self.manifest)!=self.manifest_hash:return incomplete('provider_identity_changed_recreate_required')
        from short_heads_lifecycle import COMPONENTS as LIFECYCLE,assemble_lifecycle_head
        from short_heads_updates import COMPONENTS as UPDATES,assemble_update_head
        if component in LIFECYCLE:return assemble_lifecycle_head(self,component,payload)
        if component in UPDATES:return assemble_update_head(self,component,payload)
        task=self.manifest.get('tasks',{}).get(component)
        if component in NARROW_COMPOSITES:
            try:
                value=compose_narrow(self,component,payload)
                if component=='D05.2':
                    unresolved=[row['attemptId'] for row in value['judgments'] if row['label']=='incomplete']
                    if unresolved:
                        self.checkpoint('semantic_joint_incomplete',{'component':component,'inputSha256':digest(payload),
                          'judgments':value['judgments'],'incompleteAttemptIds':unresolved})
                        return incomplete('semantic_incomplete:D05.2:'+','.join(unresolved))
                return result(value)
            except Exception as error:return incomplete('narrow_composite:'+str(error))
        if task is None or task['kind']=='annotation_only':return incomplete('unconnected_or_untrained_component:'+component)
        role='generator' if task['kind']=='text' else 'encoder'
        spec=self.manifest['models'].get(role,{})
        if spec.get('trainingSteps',0)<=0 or component not in spec.get('trainedComponents',[]):
            return incomplete('untrained_component:'+component)
        if role=='encoder' and (spec.get('componentNonzeroDataGradientSteps') or {}).get(component,0)<=0:
            return incomplete('untrained_no_nonzero_data_gradient:'+component)
        self.primitive_calls+=1
        begin=time.perf_counter();event={'component':component,'input':copy.deepcopy(payload),'inputSha256':digest(payload),'role':role}
        self.checkpoint('semantic_call_started',event)
        try:
            torch,model,tokenizer,heads=self._load(role);config=self.manifest['config']
            if role=='generator':
                ids=complete_tokens(tokenizer,input_text(component,payload),config['maxInputTokens'],vocab_size=model.config.vocab_size)
                tensors={'input_ids':torch.tensor([ids]),'attention_mask':torch.ones((1,len(ids)),dtype=torch.long)}
                self.checkpoint('generator_forward_started',{'component':component,'inputIds':ids})
                compute_started=time.perf_counter()
                with torch.no_grad():
                    tokens=model.generate(**tensors,do_sample=False,num_beams=1,max_new_tokens=config['maxNewTokens'])[0].tolist()
                self.checkpoint('generator_forward_settled',{'component':component,'elapsedMs':(time.perf_counter()-compute_started)*1000,'rawTokenIds':tokens})
                raw=tokenizer.decode(tokens,skip_special_tokens=True)
                event.update(inputIds=ids,rawTokenIds=tokens,rawText=raw)
                if tokenizer.eos_token_id not in tokens[1:]:raise ValueError('truncated_no_eos')
                if not raw.strip():raise ValueError('empty_generation')
                codec=task['outputCodec']
                if codec in ('fragment_or_end','fact_or_end'):
                    value={'kind':'end'} if raw==END else {'kind':'fragment' if codec=='fragment_or_end' else 'fact','text':raw}
                elif codec=='text':value=raw
                else:raise ValueError('unregistered_output_codec')
            else:
                context=encode_complete(torch,model,tokenizer,component,payload,config,self.checkpoint)
                candidates=None
                if task['kind']=='reference':
                    rows=payload.get('candidates')
                    if not rows or len({r['id'] for r in rows})!=len(rows):raise ValueError('incomplete_reference_candidates')
                    candidates=[encode_complete(torch,model,tokenizer,component+':candidate',r,config,self.checkpoint) for r in rows]
                with torch.no_grad():
                    logits=head_logits(torch,heads[component],task,context,candidates)
                values=logits.squeeze(0).tolist();event['rawLogits']=values
                if not all(math.isfinite(v) for v in values):raise ValueError('nonfinite_logits')
                index=int(logits.argmax(1).item())
                if task['kind']=='number':value=index
                elif task['kind']=='label':value=task['labels'][index]
                else:value=payload['candidates'][index]['id']
                known_support=(spec.get('componentLabelDataGradientExposures') or {}).get(component)
                if task['kind']=='label' and known_support is not None and known_support.get(value,0)<=0:
                    event['rawLabel']=value
                    raise ValueError('untrained_positive_label:'+component+':'+value)
            event.update(completion='result',value=value)
            if component=='D02.1' and value=='incomplete':
                event.update(completion='incomplete',rawLabel=value,error='semantic_incomplete:D02.1')
                return incomplete('semantic_incomplete:D02.1')
            return result(value)
        except Exception as error:
            event.update(completion='incomplete',error={'type':type(error).__name__,'message':str(error)})
            return incomplete('local_backend:'+str(error))
        finally:
            event['elapsedMs']=(time.perf_counter()-begin)*1000
            if self.retain_observations:self.observations.append(copy.deepcopy(event))
            self.checkpoint('semantic_call_finished',event)


NARROW_COMPOSITES={'D03.1','D05.1','D05.2','D05.4','D05.5','U1.1','U3.1','U4.1','D06.P.review'}


def primitive_input(payload,query):
    return {**copy.deepcopy(payload),'semanticQuery':copy.deepcopy(query)}


def _compose_group_heads(provider,component,payload):
    """Program packages model labels; never substitutes a missing model decision."""
    def choose(task,query):
        answer=provider(task,primitive_input(payload,query))
        if answer.status!='result':raise ValueError(task+':'+str(answer.reason or answer.status))
        return answer.value
    if component=='D03.1':
        return [{'candidateId':key,'relation':choose('D03.1.relation',{'candidateId':key})} for key in payload['candidateIds']]
    if component=='D05.1':
        ids=payload['context']['group']['memberIds'];edges=[]
        for a in ids:
            for b in ids:
                if a==b:continue
                for relation in ('obstructs','supports','contests','depends'):
                    value=choose('D05.1.edge',{'sourceId':a,'targetId':b,'relation':relation})
                    if value not in ('present','absent'):raise ValueError('invalid relation presence')
                    if value=='present':edges.append({'sourceId':a,'targetId':b,'kind':relation})
        return {'checkedActionIds':ids,'relations':edges}
    if component=='D05.2':
        return {'judgments':[{'attemptId':a['attemptId'],'label':choose('D05.2.label',{'attemptId':a['attemptId']})} for a in payload['attempts']]}
    if component=='D05.4':
        verdict=choose('D05.4.verdict',{})
        return {'verdict':verdict,'checkedActionIds':payload['context']['group']['memberIds'],
                'checkedFactIds':[f['id'] for f in payload['candidates']],
                'checkedRollIds':[r['rollId'] for r in payload['context']['group']['judgments']]}
    if component=='D05.5':
        members=payload['context']['group']['memberIds'];rows=[]
        for fact in payload['candidates']:
            selected=[]
            for member in members:
                label=choose('D05.5.member',{'factId':fact['id'],'memberId':member})
                if label not in ('include','exclude'):raise ValueError('invalid fact association')
                if label=='include':selected.append(member)
            rows.append({'factId':fact['id'],'memberIds':selected})
        return {'facts':rows,'checkedMemberIds':members}
    if component=='U1.1':
        decisions=[]
        for key in payload['entityIds']:
            label=choose('U1.1.change',{'entityId':key})
            if label not in ('change','keep'):raise ValueError('invalid position label')
            decisions.append({'entityId':key,'change':label=='change'})
        return {'decisions':decisions}
    if component=='U3.1':
        return {'checkedCharacterIds':payload['characterIds'],'decisions':[{'taskId':key,'label':choose('U3.1.status',{'taskId':key})} for key in payload['taskIds']]}
    if component=='U4.1':
        needs=[]
        for key in payload['parentTaskIds']:
            value=choose('U4.1.count',{'parentTaskId':key})
            if type(value) is not int or value<0:raise ValueError('invalid subtask count')
            needs.append({'parentTaskId':key,'count':value})
        return {'checkedParentTaskIds':payload['parentTaskIds'],'checkedCharacterIds':payload['characterIds'],'needs':needs}
    if component=='D06.P.review':
        return {'verdict':choose('D06.P.review.verdict',{}),'checkedEntityIds':list(payload['proposed']['changes'])}
    raise ValueError('unconnected_composite:'+component)


def mention_candidates(payload):
    """All exact registered-name/marker spans; semantics come from role heads."""
    world=payload['context']['world'];entities={}
    if 'initial' in world:
        entities={key:e for rows in world['initial'].values() if isinstance(rows,dict) for key,e in rows.items() if isinstance(e,dict) and 'name' in e}
    else:entities={e['id']:e for k in ('places','items','characters') for e in world[k]}
    rows=[];text=payload['text']
    for key,e in entities.items():
        surface='[['+key+']]' if payload.get('representation')=='references' else e['name']
        offset=0
        while True:
            index=text.find(surface,offset)
            if index<0:break
            rows.append({'entityId':key,'start':index,'end':index+len(surface),'surface':surface});offset=index+1
    return rows


NARROW_COMPOSITES.update({'D02.2','D05.3','D02.3','D02.4','D02.5','D03.2','D04.1'})


def compose_narrow(provider,component,payload):
    def choose(task,query,candidates=None):
        context=primitive_input(payload,query)
        if candidates is not None:context['candidates']=candidates
        answer=provider(task,context)
        if answer.status!='result':raise ValueError(task+':'+str(answer.reason or answer.status))
        return answer.value
    if component in ('D02.2','D05.3'):
        kind='fragment' if component=='D02.2' else 'fact'
        decision=choose(component+'.next',{})
        if decision=='end':return {'kind':'end'}
        if decision!=kind:raise ValueError('invalid short sequence continuation label')
        text=choose(component+'.text',{})
        if not isinstance(text,str) or not text.strip():raise ValueError('empty short semantic text')
        return {'kind':kind,'text':text}
    if component=='D02.3':
        verdict=choose('D02.3.verdict',{})
        if verdict not in ('pass','reject'):raise ValueError('invalid binding verdict')
        refs=[]
        for mention in mention_candidates(payload):
            for role in ('subject','object','tool','recipient','destination'):
                value=choose('D02.3.role',{'mention':mention,'role':role})
                if value not in ('present','absent'):raise ValueError('invalid role presence')
                if value=='present':refs.append({k:mention[k] for k in ('entityId','start','end')}|{'role':role})
        return {'verdict':verdict,'references':refs}
    if component in ('D02.4','D02.5'):
        names=('dependencies','conditions','requirements') if component=='D02.4' else ('actor','tools','objects','qualifiers','attempt')
        checks={};issues=[];fragments=[f['fragmentId'] for f in payload['fragments']]
        for key in names:
            value=choose(component+'.check',{'check':key})
            if value not in ('pass','fail'):raise ValueError('invalid audit label')
            checks[key]=value
            if value=='fail':
                selected=choose(component+'.issue_fragment',{'check':key},[{'id':f['fragmentId'],'text':f['text']} for f in payload['fragments']])
                if selected not in fragments:raise ValueError('unknown issue fragment')
                issues.append({'fragmentId':selected,'code':key})
        return {'verdict':'pass' if not issues else 'reject','fragmentIds':fragments,'checks':checks,'issues':issues}
    if component=='D04.1':
        constraints=[]
        for index in range(33):
            decision=choose('D04.1.next',{'constraints':constraints})
            if decision=='end':break
            if decision!='constraint' or index==32:raise ValueError('reaction_constraint_budget_or_label')
            text=choose('D04.1.text',{'constraints':constraints})
            if not isinstance(text,str) or not text.strip():raise ValueError('empty_reaction_constraint')
            constraints.append(text)
        if not constraints:raise ValueError('admitted_reaction_has_no_constraint')
        sources=[]
        for threat in payload['threats']:
            source=threat['memberId']
            value=choose('D04.1.covered',{'constraints':constraints,'sourceId':source})
            if value!='covered':raise ValueError('reaction_constraint_missing_threat')
            sources.append(source)
        return {'threatSourceIds':sources,'constraint':'\n'.join(constraints)}
    if component=='D03.2':
        verdict=choose('D03.2.verdict',{})
        if verdict not in ('pass','reject'):raise ValueError('invalid target audit')
        return {'verdict':verdict,'candidateIds':payload['candidateIds'],'targetIds':payload['targetIds']}
    return _compose_group_heads(provider,component,payload)
