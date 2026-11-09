/* Build the pinned ORT diagnostic entry, without executing any model. */
import {createRequire} from 'node:module';
import {readFile,writeFile,access} from 'node:fs/promises';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
const directory=resolve(process.argv[2]),out=resolve(process.argv[3]);
try{await access(out);throw Error('preserve existing bundle; use a new output path');}catch(e){if(e.code!=='ENOENT')throw e;}
const require=createRequire(directory+'/package.json'),esbuild=require('esbuild');
const pkg=JSON.parse(await readFile(directory+'/node_modules/onnxruntime-web/package.json','utf8'));
if(esbuild.version!=='0.25.5'||pkg.version!=='1.22.0-dev.20250409-89f8206ba4')throw Error('unregistered build dependencies');
const result=await esbuild.build({stdin:{contents:"export * from 'onnxruntime-web/webgpu';",resolveDir:directory},outfile:out,
 platform:'browser',format:'esm',target:'es2022',bundle:true,minify:true,metafile:true});
if(Object.values(result.metafile.outputs).flatMap(x=>x.imports).some(x=>x.external))throw Error('unresolved imports');
const sha=x=>createHash('sha256').update(x).digest('hex');
await writeFile(out+'.build.json',JSON.stringify({esbuild:esbuild.version,ort:pkg.version,
 lockSha256:sha(await readFile(directory+'/package-lock.json')),bundleSha256:sha(await readFile(out)),metafile:result.metafile}),{flag:'wx'});
