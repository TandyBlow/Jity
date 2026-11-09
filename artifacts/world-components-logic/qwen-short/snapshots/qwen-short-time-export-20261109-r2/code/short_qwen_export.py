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


def freeze(run_id,*,model_manifest):
    path,out=paths(run_id)
    if path.exists() or out.exists():raise FileExistsError('preserve original export; use a new identity')
    model=common.read_json(model_manifest);training=common.read_json(model['recordPath'])
    if model['schema']!='jity-qwen-short-trained-source-v1' or training['status']!='diagnostic_completed':raise ValueError('completed actual Qwen training/merge required')
    if training['modelManifest']['sha256']!=sha256_file(model_manifest):raise ValueError('training model manifest identity mismatch')
    if training['planSha256']!=model['planSha256']:raise ValueError('training lineage drift')
    training_codec_identity(model)
    disk=disk_state(LOCAL/'exports'/run_id,CONFIG,initial=True)
    directory=ART/'snapshots'/run_id;directory.mkdir(parents=True,exist_ok=False);code={}
    for name in CODE:
        destination=directory/'code'/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(BASE/name,destination);code[name]=sha256_file(destination)
    source=directory/'trained-source-model.json';shutil.copyfile(model_manifest,source)
    plan={'schema':'jity-qwen-export-plan-v1','runId':run_id,'preparedAt':timestamp(),'config':copy.deepcopy(CONFIG),
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
    if plan['config']!=CONFIG:raise ValueError('export config drift')
    if sha256_file(plan['modelManifest']['path'])!=plan['modelManifest']['sha256']:raise ValueError('trained manifest drift')
    for item in plan['model']['merged']['files']:
        if sha256_file(Path(plan['model']['merged']['directory'])/item['path'])!=item['sha256']:raise ValueError('merged model/tokenizer drift')
    if sha256_file(plan['model']['planPath'])!=plan['model']['planSha256']:raise ValueError('source training plan drift')
    for name,expected in plan['codeSha256'].items():
        if sha256_file(BASE/name)!=expected or sha256_file(Path(plan['codeSnapshot'])/name)!=expected:raise ValueError('export source drift:'+name)
    if sys.version!=plan['environment']['pythonVersion']:raise ValueError('Python drift')
    for name,expected in plan['environment']['versions'].items():
        if importlib.metadata.version(name)!=expected:raise ValueError('export dependency drift:'+name)


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


def validate_float(model,config,graph,export_config):
    """Full named-output comparison, using official config input/patch helpers.

    Unlike Optimum's top-level export wrapper, numerical mismatch is fatal.
    The reference explicitly uses eager attention, avoiding a different fused
    SDPA reference arithmetic path from the ONNX attention operators.
    """
    import torch,numpy as np,onnxruntime as ort
    torch.manual_seed(export_config['validationSeed'])
    inputs=config.generate_dummy_inputs(framework='pt',batch_size=1,
        sequence_length=export_config['traceSequenceLength'])
    options=ort.SessionOptions();options.intra_op_num_threads=1;options.inter_op_num_threads=1
    options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
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
    actual=session.run(names,arrays);mapping={v:k for k,v in config.torch_to_onnx_output_map.items()}
    checks=[compare_output(name,refs[mapping.get(name,name)].detach().cpu().numpy(),value,export_config)
            for name,value in zip(names,actual)]
    receipt={'schema':'jity-qwen-onnx-strict-validation-v1','scope':'float_export_numerical',
      'status':'passed' if all(x['valuesClose'] for x in checks) else 'failed',
      'expectedOutputNames':names,'checks':checks,'referenceAttention':export_config['referenceAttention'],
      'validationSeed':export_config['validationSeed'],'optimization':export_config['validationOptimization'],
      'inputShapes':{k:list(v.shape) for k,v in arrays.items()},
      'inputArraysSha256':{k:__import__('hashlib').sha256(v.tobytes()).hexdigest() for k,v in arrays.items()}}
    exclusive(Path(graph).parent/'strict-float-validation.json',receipt)
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
    constructor=TasksManager.get_exporter_config_constructor(model=model,exporter='onnx',task=config['task'])
    onnx_config=constructor(model.config,use_past=True,use_past_in_inputs=True)
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
