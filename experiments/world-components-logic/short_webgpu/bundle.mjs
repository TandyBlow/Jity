/* Build only. Does not import the generated model runtime or execute a model. */
import {createRequire} from 'node:module';
import {resolve} from 'node:path';
import {writeFile} from 'node:fs/promises';

const directory = resolve(process.argv[2]);
const require = createRequire(resolve(directory, 'package.json'));
const esbuild = require('esbuild');
if (esbuild.version !== '0.25.5') throw Error('unregistered_bundler_version');
const result = await esbuild.build({
  absWorkingDir: directory,
  entryPoints: ['node_modules/@huggingface/transformers/dist/transformers.web.min.js'],
  outfile: resolve(directory, 'built/transformers.web.min.js'),
  platform: 'browser', format: 'esm', target: 'es2022', bundle: true,
  minify: true, sourcemap: false, metafile: true, legalComments: 'inline',
  logLevel: 'warning',
});
const external = Object.values(result.metafile.outputs).flatMap(v => v.imports).filter(v => v.external);
if (external.length) throw Error('unresolved_runtime_imports:' + JSON.stringify(external));
await writeFile(resolve(directory, 'built/metafile.json'), JSON.stringify(result.metafile, null, 2) + '\n', {flag: 'wx'});
