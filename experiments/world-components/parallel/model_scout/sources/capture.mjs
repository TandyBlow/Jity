// Capture the primary sources cited by the MNN-Pocket-0.3B scout report.
//
// For each URL we store the exact response bytes and record: status code,
// fetch time, content-type, byte length and sha256. The report only cites
// claims that can be re-derived from these captured bytes, so a later reader
// never has to trust a search snippet.
//
// A second pass sends HEAD to the three weight files and keeps Hugging Face's
// X-Linked-ETag / X-Linked-Size, which the report compares against the locally
// downloaded GGUF files.
//
// Downloads go through the system curl because Node's fetch does not pick up
// the proxy settings this machine needs (curl does).
//
//   node sources/capture.mjs
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const SOURCES = [
  ['hf-api-base', 'https://huggingface.co/api/models/taobao-mnn/MNN-Pocket-0.3B'],
  ['hf-api-gguf', 'https://huggingface.co/api/models/taobao-mnn/MNN-Pocket-0.3B-GGUF?blobs=true'],
  ['hf-card-base', 'https://huggingface.co/taobao-mnn/MNN-Pocket-0.3B/raw/main/README.md'],
  ['hf-card-gguf', 'https://huggingface.co/taobao-mnn/MNN-Pocket-0.3B-GGUF/raw/main/README.md'],
  ['hf-config-base', 'https://huggingface.co/taobao-mnn/MNN-Pocket-0.3B/raw/main/config.json'],
  ['hf-license-gguf', 'https://huggingface.co/taobao-mnn/MNN-Pocket-0.3B-GGUF/raw/main/LICENSE.txt'],
  ['mnn-github-readme', 'https://raw.githubusercontent.com/alibaba/MNN/master/README.md'],
  ['mnn-github-readme-cn', 'https://raw.githubusercontent.com/alibaba/MNN/master/README_CN.md'],
];

const report = { capturedAt: new Date().toISOString(), tool: 'curl (system proxy)', entries: [] };
for (const [name, url] of SOURCES) {
  const file = `${name}.body`;
  const started = Date.now();
  const meta = spawnSync('curl', ['-sS', '-L', '--max-time', '90', '--retry', '2',
    '-o', resolve(here, file), '-w', '%{http_code}\\n%{content_type}\\n%{url_effective}', url], { encoding: 'utf8' });
  if (meta.status !== 0) throw new Error(`curl failed for ${url}: ${meta.stderr}`);
  // curl -w prints exactly what we asked for, one field per line: a content
  // type such as "text/plain; charset=utf-8" contains spaces, so splitting on
  // spaces silently shifted every field (found in review of 84e4ca8).
  const [status, contentType, finalUrl] = meta.stdout.trim().split(String.fromCharCode(10)).map((field) => field.trim());
  const body = readFileSync(resolve(here, file));
  report.entries.push({
    name, url, file, status: Number(status), finalUrl, contentType,
    bytes: body.length, ms: Date.now() - started,
    sha256: createHash('sha256').update(body).digest('hex'),
  });
  console.log(`${status} ${body.length}B ${name}`);
  if (name === 'mnn-github-readme' || name === 'mnn-github-readme-cn') {
    const hits = body.toString('utf8').split('\n').filter((line) => /Pocket/.test(line));
    report.entries.at(-1).pocketMentions = hits.slice(0, 10);
  }
}
writeFileSync(resolve(here, 'capture.json'), JSON.stringify(report, null, 2) + '\n');

const HEADS = ['MNN-Pocket-0.3B-Instruct-F16.gguf', 'MNN-Pocket-0.3B-Instruct-Q8_0.gguf',
  'MNN-Pocket-0.3B-Instruct-Q4_1.gguf'];
const heads = { checkedAt: new Date().toISOString(), entries: [] };
for (const name of HEADS) {
  const url = `https://huggingface.co/taobao-mnn/MNN-Pocket-0.3B-GGUF/resolve/main/${name}`;
  const head = spawnSync('curl', ['-sSI', '--max-time', '60', url], { encoding: 'utf8' }).stdout;
  const lines = head.split(String.fromCharCode(10)).map((line) => line.replace(String.fromCharCode(13), ''));
  const header = (key) => lines.find((line) => line.toLowerCase().startsWith(key.toLowerCase()))?.split(':')[1]?.trim() ?? null;
  const statusLine = lines.find((line) => line.startsWith('HTTP/')) ?? null;
  heads.entries.push({ name, url, status: statusLine ? Number(statusLine.split(' ')[1]) : null,
    linkedEtag: header('x-linked-etag')?.replaceAll('"', '') ?? null, linkedSize: Number(header('x-linked-size')) || null });
  console.log(`HEAD ${name} ${heads.entries.at(-1).linkedEtag} ${heads.entries.at(-1).linkedSize}`);
}
writeFileSync(resolve(here, 'heads.json'), JSON.stringify(heads, null, 2) + '\n');
