"""Frozen, supervised export of a trained Qwen merge to local WebGPU assets.

The standard Optimum Qwen3 exporter and ORT weight quantizer are used. Conversion
and numerical validation are not a semantic or browser-quality pass.
"""
from __future__ import annotations

import argparse
import copy
import importlib.metadata
import json
from pathlib import Path
import shutil
import sys
import time

import experiment as common
from lab import sha256_file
from run_pilot import exclusive,save,timestamp

ROOT=Path(__file__).resolve().parents[2];BASE=Path(__file__).resolve().parent
ART=ROOT/'artifacts/world-components-logic/qwen-short'
LOCAL=Path.home()/'.cache/jity-d-short-semantics-20261109/qwen'
ARM=('qwen_onnx_export',)
CONFIG={'attemptsPerCase':1,'processWallSeconds':1800,'maxResidentMiB':11000,'threads':1,
 'device':'cpu','task':'text-generation-with-past','opset':18,'dtype':'fp32','batchSize':1,
 'traceSequenceLength':8,'validateFloatExport':True,'validationAtol':0.0001,
 'validationRtol':0.00001,'validationSeed':7,'referenceAttention':'eager',
 'validationOptimization':'ORT_ENABLE_BASIC','strictValidationRequired':True,
 'quantization':'q4f16','blockSize':32,'symmetric':True,'keepIoTypes':True,
 'targetRuntime':'transformers.js@3.8.1','targetFile':'model_q4f16.onnx','retries':0,
 'maxAdditionalDiskBytes':8*1024**3,'minFreeDiskBytes':6*1024**3}
from short_qwen_training import CODE as TRAIN_CODE
CODE=('short_qwen_export.py',*TRAIN_CODE)
VERSIONS=('torch','transformers','numpy','optimum','optimum-onnx','onnx','onnxruntime','onnxscript')


def disk_state(directory,config,*,initial=False):
    root=Path(directory);anchor=root
    while not anchor.exists():anchor=anchor.parent
    usage=shutil.disk_usage(anchor)
    observed=sum(p.stat().st_size for p in root.rglob('*') if p.is_file()) if root.exists() else 0
    required=config['minFreeDiskBytes']+(config['maxAdditionalDiskBytes'] if initial else 0)
    if usage.free<required:raise ValueError('insufficient_registered_export_disk_reserve')
    if observed>config['maxAdditionalDiskBytes']:raise ValueError('export_workspace_budget_exceeded')
    return {'directory':str(root),'filesystemFreeBytes':usage.free,'observedWorkspaceBytes':observed,
            'maxAdditionalDiskBytes':config['maxAdditionalDiskBytes'],'minFreeDiskBytes':config['minFreeDiskBytes'],
            'measurement':'stage_boundary_filesystem_and_workspace_bytes_not_continuous_peak'}


def paths(run_id):
    from short_qwen_training import paths as valid
    valid(run_id)
    return ART/(run_id+'.export-plan.json'),ART/(run_id+'.export-record.json')


def training_codec_identity(model):
    """Use the actual training identity; export cannot relabel a prompt recipe."""
    training_plan=common.read_json(model['planPath'])
    if sha256_file(model['planPath'])!=model['planSha256']:
        raise ValueError('source training plan drift')
    name='short_qwen_codec.py'
    expected=model['codeSha256'].get(name)
    if not expected or training_plan['codeSha256'].get(name)!=expected:
        raise ValueError('training codec source identity mismatch')
    if training_plan['config']['codec']!=model['codec']:
        raise ValueError('training codec version mismatch')
    return {'codec':model['codec'],'codecSha256':expected,
            'trainingCodeSha256':copy.deepcopy(model['codeSha256'])}


def replay_input_config(graph):
    import struct,hashlib
    receipt=common.read_json(Path(graph).parent/'strict-float-validation.json')
    shape=receipt['inputShapes']['attention_mask']
    if shape[0]!=1:raise ValueError('unsupported historical validation mask batch')
    expected=receipt['inputArraysSha256']['attention_mask'];matches=[]
    # Official dummy masks are contiguous padding, with optional past-cache
    # prefix ones. Recover by byte digest only; no prediction or tolerance is
    # consulted, and multiple/no matches abort before running the model.
    candidates={tuple([1]*shape[-1])}
    for start in range(shape[-1]):
        for stop in range(start+1,shape[-1]+1):
            candidates.add(tuple([1]*start+[0]*(stop-start)+[1]*(shape[-1]-stop)))
    for candidate in candidates:
        values=list(candidate)
        if hashlib.sha256(struct.pack('<'+'q'*len(values),*values)).hexdigest()==expected:matches.append(values)
    if len(matches)!=1:raise ValueError('historical validation mask cannot be uniquely recovered by exact bytes')
    return {'validationAttentionMask':[matches[0]],'expectedInputArraysSha256':receipt['inputArraysSha256']}


def freeze(run_id,*,model_manifest,float_graph=None):
    path,out=paths(run_id)
    if path.exists() or out.exists():raise FileExistsError('preserve original export; use a new identity')
    model=common.read_json(model_manifest);training=common.read_json(model['recordPath'])
    if model['schema']!='jity-qwen-short-trained-source-v1' or training['status']!='diagnostic_completed':raise ValueError('completed actual Qwen training/merge required')
    if training['modelManifest']['sha256']!=sha256_file(model_manifest):raise ValueError('training model manifest identity mismatch')
    if training['planSha256']!=model['planSha256']:raise ValueError('training lineage drift')
    training_codec_identity(model)
    config=copy.deepcopy(CONFIG);source_float=None
    if float_graph is not None:
        graph=Path(float_graph).resolve()
        config.update(validationOptimization='ORT_DISABLE_ALL',maxAdditionalDiskBytes=2*1024**3,**replay_input_config(graph))
        source_float={'path':str(graph),'files':[{'path':str(p),'sha256':sha256_file(p),'bytes':p.stat().st_size} for p in sorted(graph.parent.iterdir()) if p.is_file()]}
    disk=disk_state(LOCAL/'exports'/run_id,config,initial=True)
    directory=ART/'snapshots'/run_id;directory.mkdir(parents=True,exist_ok=False);code={}
    for name in CODE:
        destination=directory/'code'/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(BASE/name,destination);code[name]=sha256_file(destination)
    source=directory/'trained-source-model.json';shutil.copyfile(model_manifest,source)
    plan={'schema':'jity-qwen-export-plan-v1','runId':run_id,'preparedAt':timestamp(),'config':config,'sourceFloatGraph':source_float,
      'cases':[{'caseId':'trained_qwen_merge'}],'modelManifest':{'path':str(source),'sha256':sha256_file(source)},
      'model':model,'codeSha256':code,'codeSnapshot':str(directory/'code'),
      'environment':{'venvExecutableRelativePath':sys.executable,'pythonVersion':sys.version,
        'versions':{name:importlib.metadata.version(name) for name in VERSIONS}},
      'sourceDocumentation':['https://huggingface.co/docs/optimum-onnx/onnx/usage_guides/export_a_model',
        'https://github.com/huggingface/transformers.js/blob/3.8.1/scripts/quantize.py'],
      'diskPreflight':disk,
      'readiness':'ready_conversion','formalEvaluationAllowed':False,'webgpuValidated':False}
    exclusive(path,plan);verify(plan);return path


def verify(plan):
    training_codec_identity(plan['model'])
    expected=copy.deepcopy(CONFIG)
    if plan.get('sourceFloatGraph'):
        expected.update(validationOptimization='ORT_DISABLE_ALL',maxAdditionalDiskBytes=2*1024**3,**replay_input_config(plan['sourceFloatGraph']['path']))
        for item in plan['sourceFloatGraph']['files']:
            if sha256_file(item['path'])!=item['sha256']:raise ValueError('inherited float graph bytes drift')
    if plan['config']!=expected:raise ValueError('export config drift')
    if sha256_file(plan['modelManifest']['path'])!=plan['modelManifest']['sha256']:raise ValueError('trained manifest drift')
    for item in plan['model']['merged']['files']:
        if sha256_file(Path(plan['model']['merged']['directory'])/item['path'])!=item['sha256']:raise ValueError('merged model/tokenizer drift')
    if sha256_file(plan['model']['planPath'])!=plan['model']['planSha256']:raise ValueError('source training plan drift')
    for name,expected in plan['codeSha256'].items():
        if sha256_file(BASE/name)!=expected or sha256_file(Path(plan['codeSnapshot'])/name)!=expected:raise ValueError('export source drift:'+name)
    if sys.version!=plan['environment']['pythonVersion']:raise ValueError('Python drift')
    for name,expected in plan['environment']['versions'].items():
        if importlib.metadata.version(name)!=expected:raise ValueError('export dependency drift:'+name)


def qwen_onnx_config(model,task):
    # Registration is explicit even when reusing a graph in a fresh worker.
    from optimum.exporters.onnx import convert
    from optimum.exporters.tasks import TasksManager
    constructor=TasksManager.get_exporter_config_constructor(model=model,exporter='onnx',task=task,library_name='transformers')
    return constructor(model.config,use_past=True,use_past_in_inputs=True)


def compare_output(name,reference,actual,config):
    import numpy as np
    finite=bool(np.isfinite(reference).all() and np.isfinite(actual).all())
    same=reference.shape==actual.shape
    close=bool(same and finite and np.allclose(reference,actual,
        atol=config['validationAtol'],rtol=config['validationRtol']))
    return {'name':name,'atol':config['validationAtol'],'rtol':config['validationRtol'],
      'finite':finite,'shapesEqual':same,'valuesClose':close,
      'referenceShape':list(reference.shape),'actualShape':list(actual.shape),
      'maxAbsError':float(np.max(np.abs(reference-actual))) if same and finite else None}


def require_strict_validation(receipt):
    names=receipt.get('expectedOutputNames',[]);checks=receipt.get('checks',[])
    if (not names or len(names)!=len(set(names)) or len(checks)!=len(names)
        or {x.get('name') for x in checks}!=set(names)
        or any(any(x.get(k) is not True for k in ('finite','shapesEqual','valuesClose')) for x in checks)):
        raise ValueError('strict_float_export_numerical_validation_failed')
    return receipt


def validate_float(model,config,graph,export_config,receipt_path=None):
    """Full named-output comparison, using official config input/patch helpers.

    Unlike Optimum's top-level export wrapper, numerical mismatch is fatal.
    The reference explicitly uses eager attention, avoiding a different fused
    SDPA reference arithmetic path from the ONNX attention operators.
    """
    import torch,numpy as np,onnxruntime as ort
    torch.manual_seed(export_config['validationSeed']);__import__('random').seed(export_config['validationSeed']);np.random.seed(export_config['validationSeed'])
    inputs=config.generate_dummy_inputs(framework='pt',batch_size=1,
        sequence_length=export_config['traceSequenceLength'])
    if 'validationAttentionMask' in export_config:
        inputs['attention_mask']=torch.tensor(export_config['validationAttentionMask'],dtype=inputs['attention_mask'].dtype)
    options=ort.SessionOptions();options.intra_op_num_threads=1;options.inter_op_num_threads=1
    options.graph_optimization_level=getattr(ort.GraphOptimizationLevel,export_config['validationOptimization'])
    session=ort.InferenceSession(str(graph),sess_options=options,providers=['CPUExecutionProvider'])
    names=[v.name for v in session.get_outputs()]
    if set(names)!=set(config.outputs):raise ValueError('strict validation output-name mismatch')
    copied=config.rename_ambiguous_inputs(copy.deepcopy(inputs))
    with config.patch_model_for_export(model):
        with torch.inference_mode():reference=model(**copied)
    refs={}
    for name,value in reference.items():
        name='present' if name=='past_key_values' else name
        if isinstance(value,(list,tuple)):
            refs.update(config.flatten_output_collection_property(config.torch_to_onnx_output_map.get(name,name),value))
        else:refs[name]=value
    ort_inputs=config.generate_dummy_inputs_for_validation(inputs,[v.name for v in session.get_inputs()])
    flattened={}
    for name,value in ort_inputs.items():
        if isinstance(value,(list,tuple)):flattened.update(config.flatten_output_collection_property(name,value))
        elif isinstance(value,dict):flattened.update(value)
        else:flattened[name]=value
    arrays={name:value.detach().cpu().numpy() for name,value in flattened.items()}
    hashes={k:__import__('hashlib').sha256(v.tobytes()).hexdigest() for k,v in arrays.items()}
    if export_config.get('expectedInputArraysSha256') is not None and hashes!=export_config['expectedInputArraysSha256']:
        raise ValueError('historical validation actual inputs differ')
    array_path=Path(receipt_path or Path(graph).parent/'strict-float-validation.json').with_suffix('.inputs.npz')
    with array_path.open('xb') as out:np.savez(out,**arrays)
    actual=session.run(names,arrays);mapping={v:k for k,v in config.torch_to_onnx_output_map.items()}
    checks=[compare_output(name,refs[mapping.get(name,name)].detach().cpu().numpy(),value,export_config)
            for name,value in zip(names,actual)]
    receipt={'schema':'jity-qwen-onnx-strict-validation-v1','scope':'float_export_numerical',
      'status':'passed' if all(x['valuesClose'] for x in checks) else 'failed',
      'expectedOutputNames':names,'checks':checks,'referenceAttention':export_config['referenceAttention'],
      'validationSeed':export_config['validationSeed'],'optimization':export_config['validationOptimization'],
      'inputShapes':{k:list(v.shape) for k,v in arrays.items()},
      'inputArraysSha256':hashes,'inputArraysArchive':{'path':str(array_path),'sha256':sha256_file(array_path)}}
    exclusive(receipt_path or Path(graph).parent/'strict-float-validation.json',receipt)
    require_strict_validation(receipt)
    return receipt


def export_float(source,destination,config):
    import torch
    from transformers import AutoModelForCausalLM
    from optimum.exporters.onnx.convert import onnx_export_from_model
    from optimum.exporters.tasks import TasksManager
    model=AutoModelForCausalLM.from_pretrained(str(source),local_files_only=True,trust_remote_code=False,
      weights_only=True,torch_dtype=torch.float32,attn_implementation=config['referenceAttention']).eval()
    torch.manual_seed(config['validationSeed'])
    onnx_export_from_model(model,destination,task=config['task'],opset=config['opset'],device='cpu',
      do_validation=False,no_post_process=True,batch_size=1,sequence_length=config['traceSequenceLength'])
    models=list(Path(destination).glob('*.onnx'))
    if len(models)!=1:raise ValueError('expected one causal decoder-with-past graph; inspect actual exported graphs')
    onnx_config=qwen_onnx_config(model,config['task'])
    validate_float(model,onnx_config,models[0],config)
    return models[0]


def quantize_q4f16(source,destination,config):
    import onnx
    from onnxruntime.quantization.matmul_nbits_quantizer import MatMulNBitsQuantizer
    from onnxruntime.transformers.float16 import convert_float_to_float16
    from onnxruntime.transformers.onnx_model import OnnxModel
    model=onnx.load(source,load_external_data=True)
    quantizer=MatMulNBitsQuantizer(model,block_size=config['blockSize'],is_symmetric=config['symmetric'],op_types_to_quantize=('MatMul',))
    quantizer.process()
    model=convert_float_to_float16(quantizer.model.model,keep_io_types=config['keepIoTypes'],disable_shape_infer=True)
    # The fp16 converter appends I/O casts; sort existing nodes by their actual
    # data dependencies before checker/runtime load. No operators are rewritten.
    OnnxModel(model).topological_sort()
    onnx.checker.check_model(model)
    # A single file is the same public layout as the verified baseline. If the
    # graph is >2GiB, external bytes are explicitly indexed rather than dropped.
    if model.ByteSize()<2_000_000_000:onnx.save_model(model,str(destination))
    else:onnx.save_model(model,str(destination),save_as_external_data=True,all_tensors_to_one_file=True,location=destination.name+'_data',size_threshold=1024)
    def shape(value):
        tensor=value.type.tensor_type
        return {'name':value.name,'dtype':onnx.TensorProto.DataType.Name(tensor.elem_type),
          'shape':[d.dim_param or d.dim_value for d in tensor.shape.dim]}
    operators=dict(__import__('collections').Counter(n.op_type for n in model.graph.node))
    if operators.get('MatMulNBits',0)==0:raise ValueError('no actual four-bit matmul nodes produced')
    return {'inputs':[shape(v) for v in model.graph.input],'outputs':[shape(v) for v in model.graph.output],
      'operators':operators,'opsets':[{ 'domain':x.domain,'version':x.version} for x in model.opset_import]}


def bind_cache_dtype(packaged,graph):
    """Bind the browser cache allocation to actual exported I/O, not weight dtype."""
    types={x['dtype'] for x in graph['inputs'] if x['name'].startswith('past_key_values.')}
    if len(types)!=1 or not types.issubset({'FLOAT','FLOAT16'}):
        raise ValueError('unsupported or inconsistent exported cache input dtype')
    dtype={'FLOAT':'float32','FLOAT16':'float16'}[next(iter(types))]
    path=Path(packaged)/'config.json';value=json.loads(path.read_text())
    value.setdefault('transformers.js_config',{}).setdefault('kv_cache_dtype',{})['q4f16']=dtype
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    return dtype


def worker(path):
    plan=common.read_json(path);verify(plan);_,out=paths(plan['runId']);slots=common.planned_slots(plan,ARM)
    report={'schema':'jity-qwen-export-record-v1','runId':plan['runId'],'planSha256':sha256_file(path),'status':'running',
      'attempts':[],'attemptSlots':slots,'activeAttempt':None,'stages':[],'checkpointStorage':common.CHECKPOINT_STORAGE,
      'formalEvaluationAllowed':False,'semanticQualityApproved':False,'webgpuValidated':False}
    exclusive(out,report)
    with common.AppendJournal(out.with_suffix('.journal.jsonl'),report['planSha256']) as journal:
        journal.append('begin',{'runId':plan['runId'],'slots':slots,'checkpointStorage':common.CHECKPOINT_STORAGE})
        attempt={**slots[0],'status':'started','startedMonotonicNs':time.monotonic_ns(),'checkpoints':[]}
        report['activeAttempt']=attempt;journal.append('attempt_start',attempt)
        def event(name,payload):
            data={k:attempt[k] for k in ('arm','caseId','repeat')};data.update(name=name,payload=payload)
            ref=common.append_checkpoint(journal,data);attempt['checkpoints'].append(ref)
        try:
            import torch
            torch.set_num_threads(1);torch.set_num_interop_threads(1)
            directory=LOCAL/'exports'/plan['runId'];directory.mkdir(parents=True,exist_ok=False)
            event('export_disk_preflight',disk_state(directory,plan['config'],initial=True))
            start=time.perf_counter();event('float_export_started',{'source':plan['model']['merged'],'config':plan['config']})
            if plan.get('sourceFloatGraph'):
                from transformers import AutoModelForCausalLM
                from optimum.exporters.tasks import TasksManager
                raw=Path(plan['sourceFloatGraph']['path'])
                model=AutoModelForCausalLM.from_pretrained(plan['model']['merged']['directory'],local_files_only=True,trust_remote_code=False,weights_only=True,torch_dtype=torch.float32,attn_implementation=plan['config']['referenceAttention']).eval()
                onnx_config=qwen_onnx_config(model,plan['config']['task'])
                strict=validate_float(model,onnx_config,raw,plan['config'],receipt_path=directory/'strict-float-validation.json')
                del model
            else:
                raw=export_float(plan['model']['merged']['directory'],directory/'float',plan['config'])
                strict=common.read_json(raw.parent/'strict-float-validation.json')
            require_strict_validation(strict)
            event('float_export_validated',{'strictValidation':strict,'elapsedMs':(time.perf_counter()-start)*1000,'graph':str(raw),'disk':disk_state(directory,plan['config'])})
            packaged=directory/'webgpu';(packaged/'onnx').mkdir(parents=True)
            for name in ('config.json','generation_config.json','tokenizer.json','tokenizer_config.json','special_tokens_map.json','chat_template.jinja'):
                source=Path(plan['model']['merged']['directory'])/name
                if source.exists():shutil.copyfile(source,packaged/name)
            # Transformers can save the template separately. The browser port
            # also accepts the JSON field; copy exact bytes, never rewrite it.
            config_file=packaged/'tokenizer_config.json';tokenizer=json.loads(config_file.read_text())
            if 'chat_template' not in tokenizer and (packaged/'chat_template.jinja').exists():
                tokenizer['chat_template']=(packaged/'chat_template.jinja').read_text();config_file.write_text(json.dumps(tokenizer,ensure_ascii=False,indent=2)+'\n')
            start=time.perf_counter();event('quantize_started',{'sourceGraph':str(raw),'config':plan['config']})
            graph=quantize_q4f16(raw,packaged/'onnx'/CONFIG['targetFile'],plan['config'])
            cache_dtype=bind_cache_dtype(packaged,graph)
            event('quantize_finished',{'elapsedMs':(time.perf_counter()-start)*1000,'graph':graph,'kvCacheDtype':cache_dtype,'disk':disk_state(directory,plan['config'])})
            files=[{'path':str(p.relative_to(packaged)),'sha256':sha256_file(p),'bytes':p.stat().st_size} for p in sorted(packaged.rglob('*')) if p.is_file()]
            proof={**strict,'planSha256':sha256_file(path),'sourceTrainingPlanSha256':plan['model']['planSha256'],
              **training_codec_identity(plan['model']),'validatedFloatGraph':{'path':str(raw),'bytes':raw.stat().st_size,'sha256':sha256_file(raw),
                 'externalFiles':[{'path':str(p),'bytes':p.stat().st_size,'sha256':sha256_file(p)} for p in sorted(raw.parent.iterdir()) if p.is_file() and p!=raw and p.name!='strict-float-validation.json']},
              'finalAssets':files,'quantization':plan['config']}
            proof_path=ART/(plan['runId']+'.strict-validation.json');exclusive(proof_path,proof)
            strict_identity={'schema':proof['schema'],'scope':proof['scope'],'status':proof['status'],
                             'proofPath':str(proof_path),'proofSha256':sha256_file(proof_path)}
            manifest={'schema':'jity-qwen-finetuned-webgpu-assets-v1','runId':plan['runId'],'directory':str(packaged),'files':files,
              'graph':graph,'kvCacheDtype':cache_dtype,'provenance':{'originalModel':'Qwen/Qwen3-0.6B','sourceRevision':plan['model']['sourceModel']['revision'],
                'sourceModel':plan['model']['sourceModel'],'trainingRunId':plan['model']['runId'],
                'trainingSteps':plan['model']['training']['steps'],'trainedComponents':plan['model']['trainedComponents'],
                'trainingStepMeaning':'current registered batch; cumulative optimizer history is separate',
                'optimizerCumulativeSteps':plan['model']['training'].get('optimizerCumulativeSteps',plan['model']['training']['steps']),
                'currentBatchTrainedComponents':plan['model'].get('currentBatchTrainedComponents',plan['model']['trainedComponents']),
                'taskTrainingLineage':plan['model'].get('taskTrainingLineage'),
                'inheritedModel':plan['model'].get('inheritedModel'),
                'allTaskModelIdentityChanged':plan['model'].get('allTaskModelIdentityChanged',True),
                'datasetSha256':plan['model']['dataset']['supervision.jsonl.gz']['sha256'],
                'checkpointSha256':plan['model']['training']['checkpoint']['sha256'],'adapter':plan['model']['training']['checkpoint'],
                'merge':plan['model']['merged'],'export':{'planPath':str(path),'planSha256':sha256_file(path),'config':plan['config'],'codeSha256':plan['codeSha256']},
                **training_codec_identity(plan['model']),'strictValidation':strict_identity,'capability':'trained_exploratory_semantics_unapproved'},
              'webgpuValidated':False,'formalEvaluationAllowed':False,'semanticQualityApproved':False}
            target=ART/(plan['runId']+'.webgpu-model.json');exclusive(target,manifest)
            attempt.update(status='complete',modelManifest={'path':str(target),'sha256':sha256_file(target)},assets=files)
        except Exception as error:attempt.update(status='failed',completion='incomplete',error={'type':type(error).__name__,'message':str(error)})
        from short_qwen_training import settle_timing
        settle_timing(journal,attempt,report,out)
    report['status']='diagnostic_completed' if attempt['status']=='complete' else 'failed';save(out,report)
    return 0 if report['status']=='diagnostic_completed' else 1


def execute(path):return common.execute_plan(Path(path),paths=paths,verify=verify,worker_script=Path(__file__),settle_stages=lambda r,s:None,arms=ARM)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--worker',type=Path,required=True);a=p.parse_args();raise SystemExit(worker(a.worker))


# Diagnostic helpers deliberately do not call require_strict_validation or
# create a qualified asset manifest. Failed original receipts remain immutable.
def array_identity(value):
    import numpy as np, hashlib
    value=np.asarray(value)
    return {'shape':list(value.shape),'dtype':str(value.dtype),
            'sha256':hashlib.sha256(memoryview(np.ascontiguousarray(value)).cast('B') if value.size else b'').hexdigest()}


def compare_diagnostic(name,reference,actual,config=CONFIG):
    import numpy as np
    reference=np.asarray(reference);actual=np.asarray(actual)
    same=reference.shape==actual.shape
    result={'name':name,'atol':config['validationAtol'],'rtol':config['validationRtol'],
      'finite':True,'shapesEqual':same,'valuesClose':same,
      'referenceShape':list(reference.shape),'actualShape':list(actual.shape),
      'reference':array_identity(reference),'actual':array_identity(actual),'maxAbsError':0.0}
    if not same:
        result.update(finite=bool(np.isfinite(reference).all() and np.isfinite(actual).all()),maxAbsError=None)
        return result
    flat_a=reference.reshape(-1);flat_b=actual.reshape(-1);total=squares=0.;outside=0
    # Whole-vocabulary prefill logits can exceed 1 GiB. Bound all temporary
    # arrays, preserving the original np.allclose(reference, actual) convention.
    for start in range(0,flat_a.size,65536):
        a=flat_a[start:start+65536];b=flat_b[start:start+65536]
        part=compare_output(name,a,b,config)
        result['finite'] &= part['finite'];result['valuesClose'] &= part['valuesClose']
        if part['maxAbsError'] is not None:result['maxAbsError']=max(result['maxAbsError'],part['maxAbsError'])
        delta=np.abs(a.astype('float64')-b.astype('float64'))
        total+=float(delta.sum());squares+=float(np.square(delta).sum())
        # The legacy gate uses the second np.allclose operand for its rtol.
        outside+=int(np.count_nonzero(~np.isclose(a,b,atol=config['validationAtol'],rtol=config['validationRtol'])))
    if not result['finite']:result['maxAbsError']=None
    elif reference.size:
        result.update(meanAbsError=total/reference.size,rmsError=float(np.sqrt(squares/reference.size)),
                      outsideTolerance=outside,elements=int(reference.size),rtolOperand='actual (legacy np.allclose convention)')
        if name=='logits':
            a=reference.reshape(-1,reference.shape[-1])[-1];b=actual.reshape(-1,actual.shape[-1])[-1]
            top=np.argsort(a)[-2:][::-1]
            result.update(referenceTop1=int(top[0]),actualTop1=int(b.argmax()),
                          top1Equal=bool(top[0]==b.argmax()),referenceMargin=float(a[top[0]]-a[top[1]]))
    return result


def diagnostic_taps(graph,layers):
    """Explicit Qwen3 module/output correspondence; fail on unknown exports.

    Order is forward order, not alphabetical order. No inferred 'last layer'
    cause: preserve the first breach and all later observations separately.
    """
    nodes={n.name:n for n in graph.graph.node};taps=[]
    def add(module,suffix):
        name='/'+module.replace('model.layers.','model/layers.').replace('.self_attn.','/self_attn/').replace('.mlp.','/mlp/')
        if module.startswith('model.layers.'):
            name=name.replace('.input_layernorm','/input_layernorm').replace('.post_attention_layernorm','/post_attention_layernorm')
        else:name='/'+module.replace('.','/')
        key=name+'/'+suffix
        if key not in nodes:raise ValueError('unmapped_diagnostic_node:'+key)
        taps.append({'module':module,'output':nodes[key].output[0],'node':key})
    add('model.embed_tokens','Gather')
    for i in range(layers):
        root=f'model.layers.{i}'
        for tail,op in [('input_layernorm','Mul_1'),('self_attn.q_proj','MatMul'),
                        ('self_attn.q_norm','Mul_1'),('self_attn.k_proj','MatMul'),
                        ('self_attn.k_norm','Mul_1'),('self_attn.v_proj','MatMul'),
                        ('self_attn.o_proj','MatMul'),('post_attention_layernorm','Mul_1'),
                        ('mlp.gate_proj','MatMul'),('mlp.up_proj','MatMul'),('mlp.down_proj','MatMul')]:
            add(root+'.'+tail,op)
        add(root,'Add_1')
    add('model.norm','Mul_1')
    return taps


def diagnostic_graph(source,destination,layers):
    """Expose existing intermediates without modifying weights or operators."""
    import onnx
    graph=onnx.load(str(source),load_external_data=False)
    taps=diagnostic_taps(graph,layers)
    # Tied weights can also live in Constant tensor attributes. ONNX requires
    # relative external locations for those attributes: link immutable bytes
    # beside the diagnostic graph rather than inventing absolute locations.
    import os
    from onnx.external_data_helper import _get_all_tensors
    linked={}
    for tensor in _get_all_tensors(graph):
        for entry in tensor.external_data:
            if entry.key=='location':
                original=(Path(source).parent/entry.value).resolve()
                if original not in linked:
                    name=f'trace-data-{len(linked)}.bin'
                    os.link(original,Path(destination).parent/name)
                    linked[original]=name
                entry.value=linked[original]
    for tap in taps:
        rank=4 if tap['module'].endswith(('q_norm','k_norm')) else 3
        graph.graph.output.append(onnx.helper.make_tensor_value_info(tap['output'],onnx.TensorProto.FLOAT,[None]*rank))
    onnx.save_model(graph,str(destination))
    return taps


def capture_modules(model,taps):
    """Return hook handles plus ordered CPU arrays; caller always removes hooks."""
    values={};handles=[]
    for tap in taps:
        name=tap['module']
        def hook(module,args,output,name=name):
            if isinstance(output,tuple):output=output[0]
            values[name]=output.detach().float().cpu().numpy().copy()
        handles.append(model.get_submodule(name).register_forward_hook(hook))
    return handles,values
