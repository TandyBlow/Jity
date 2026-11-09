"""Loopback-only raw diagnostic collector. No D provider, state, or world routes."""
import argparse,json,secrets,threading,time,sys
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse
import numpy as np
from short_qwen_diagnostic import verify,read,entry,check,save,SETTINGS
from short_qwen_export import array_identity
from run_pilot import digest
from lab import sha256_file


def received_logits(raw,vocabulary_size,destination,case_index,step):
    """Retain the first malformed/nonfinite tensor before rejecting its slot."""
    value=np.frombuffer(raw,dtype='<f4').copy() if len(raw)%4==0 else None
    if value is None or value.size!=vocabulary_size or not np.isfinite(value).all():
        stem=Path(destination)/f'{case_index}.fixed.step-{step}.rejected-logits'
        binary=stem.with_suffix(stem.suffix+'.bin')
        if not binary.exists():
            with binary.open('xb') as stream:stream.write(raw)
            save(stem.with_suffix(stem.suffix+'.json'),{'raw':entry(binary),'expectedElements':vocabulary_size,
                 'actualElements':None if value is None else int(value.size),
                 'nonfiniteElements':None if value is None else int((~np.isfinite(value)).sum()),
                 'qualification':'conversion_unqualified','worldWriteAllowed':False,'accepted':False})
        raise ValueError('invalid logits; first rejected bytes retained')
    return value


def serve(plan_path,port=0):
    plan=verify(plan_path);root=Path(plan_path).parent;dest=root/'runs/webgpu';dest.mkdir(parents=True,exist_ok=False)
    assets=read(root/'trained/assets.json')
    if assets['schema']!='jity-qwen-unqualified-diagnostic-assets-v1' or assets['worldWriteAllowed'] is not False:raise ValueError('diagnostic assets required')
    for item in assets['files']:check(item)
    runtime=Path.home()/'.cache/jity-d-short-semantics-20261109/webgpu/runtime-r2/served'
    base=Path(__file__).parent/'short_webgpu'
    model=root/'trained/webgpu'
    paths={'/':base/'diagnostic.html','/diagnostic.mjs':base/'diagnostic.mjs','/core.mjs':base/'core.mjs',
           '/ort.mjs':root/'ort.mjs','/runtime/transformers.web.min.js':runtime/'transformers.web.min.js'}
    for directory,prefix in [(model,'/model/qwen/'),(runtime/'ort','/runtime/ort/')]:
        for f in directory.rglob('*'):
            if f.is_file():paths[prefix+str(f.relative_to(directory))]=f
    paths={k:{**entry(v),'mtime':v.stat().st_mtime_ns} for k,v in paths.items()}
    save(dest/'served-assets.json',{'plan':entry(plan_path),'files':paths,'qualification':'conversion_unqualified'})
    token=secrets.token_urlsafe(32);finished=threading.Event();logits={};completed=set();lock=threading.RLock()
    config={'planSha256':sha256_file(plan_path),'cases':plan['cases'],'settings':SETTINGS,
            'modelConfig':read(model/'config.json'),'generation':plan['generation'],
            'modelSha256':sha256_file(model/'onnx/model_q4f16.onnx'),
            'qualification':'conversion_unqualified','worldWriteAllowed':False}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,status,body,kind='application/json'):
            self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store');self.send_header('Cross-Origin-Opener-Policy','same-origin');self.send_header('Cross-Origin-Embedder-Policy','require-corp');self.end_headers();self.wfile.write(body)
        def authorized(self):
            return self.headers.get('X-Diagnostic-Token')==token and self.headers.get('Origin',f'http://127.0.0.1:{self.server.server_port}')==f'http://127.0.0.1:{self.server.server_port}'
        def do_GET(self):
            route=urlparse(self.path).path
            if route=='/config':
                if not self.authorized():return self.reply(403,b'{}')
                return self.reply(200,json.dumps(config,ensure_ascii=False).encode())
            item=paths.get(route)
            if not item:return self.reply(404,b'{}')
            p=Path(item['path'])
            if p.stat().st_mtime_ns!=item['mtime'] or p.stat().st_size!=item['bytes']:return self.reply(409,b'{}')
            types={'.mjs':'text/javascript','.js':'text/javascript','.html':'text/html; charset=utf-8','.wasm':'application/wasm','.json':'application/json'}
            self.send_response(200);self.send_header('Content-Type',types.get(p.suffix,'application/octet-stream'));self.send_header('Content-Length',str(item['bytes']));self.send_header('Cache-Control','no-store');self.end_headers()
            with p.open('rb') as f:
                while chunk:=f.read(1024*1024):self.wfile.write(chunk)
        def do_POST(self):
            if not self.authorized():return self.reply(403,b'{}')
            try:
                route=urlparse(self.path).path;size=int(self.headers.get('Content-Length','0'))
                if not 0<size<8*1024*1024:raise ValueError('invalid payload size')
                raw=self.rfile.read(size)
                with lock:
                    if route.startswith('/logits/'):
                        _,_,ci,step=route.split('/');ci=int(ci);step=int(step)
                        if not 0<=ci<len(plan['cases']) or not 0<=step<=len(plan['cases'][ci]['fixedTokenIds']):raise ValueError('unknown slot')
                        if (ci,step) in logits:raise ValueError('duplicate logits')
                        value=received_logits(raw,config['modelConfig']['vocab_size'],dest,ci,step)
                        logits[ci,step]=value.reshape(1,1,-1)
                    elif route=='/result':
                        value=json.loads(raw);ci=value['caseIndex'];mode=value['mode'];key=(ci,mode)
                        if type(ci)!=int or not 0<=ci<len(plan['cases']) or mode not in ('fixed','free') or key in completed:raise ValueError('unknown or repeated slot')
                        case=plan['cases'][ci]
                        if value['planSha256']!=config['planSha256'] or value['modelSha256']!=config['modelSha256']:raise ValueError('identity mismatch')
                        if value['inputIds']!=case['inputIds'] or value['qualification']!='conversion_unqualified' or value['worldWriteAllowed'] is not False:raise ValueError('scope mismatch')
                        evidence=value['gpuEvidence']
                        if evidence['positiveWeightKernelCount']<1 or value['device']['runtimeDeviceVerified'] is not True:raise ValueError('missing actual GPU evidence')
                        if mode=='fixed':
                            expected=len(case['fixedTokenIds'])+1
                            if value['rawTokenIds']!=case['fixedTokenIds'] or any((ci,s) not in logits for s in range(expected)):raise ValueError('fixed coverage mismatch')
                            with (dest/f'{ci}.fixed.logits.npz').open('xb') as f:np.savez(f,**{f'step_{s}':logits.pop((ci,s)) for s in range(expected)})
                        value['caseId']=case['caseId'];value['engine']='webgpu'
                        save(dest/f'{ci}.{mode}.json',value);completed.add(key)
                        print('BROWSER_CASE',ci,mode,len(value['rawTokenIds']),value['eosReached'],flush=True)
                    elif route=='/event':
                        value=json.loads(raw)
                        with (dest/'events.jsonl').open('a') as f:f.write(json.dumps(value,ensure_ascii=False)+'\n')
                        if value.get('kind')=='failed':print('BROWSER_FAILED',value,flush=True);finished.set()
                        if value.get('kind')=='complete':
                            if len(completed)!=len(plan['cases'])*2:raise ValueError('incomplete browser slots')
                            save(dest/'summary.json',{'completedSlots':len(completed),'plan':entry(plan_path),
                                 'qualification':'conversion_unqualified','worldWriteAllowed':False});finished.set()
                    else:raise ValueError('diagnostic route only')
                self.reply(200,b'{"ok":true}')
            except Exception as error:self.reply(400,json.dumps({'error':str(error)}).encode())
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    print(f'DIAGNOSTIC_URL=http://127.0.0.1:{server.server_port}/#{token}',flush=True)
    finished.wait(SETTINGS['maxWallSeconds'])
    # Leave the observed final page available briefly; no background task survives.
    server.shutdown();server.server_close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('plan',type=Path);a=p.parse_args();serve(a.plan)
