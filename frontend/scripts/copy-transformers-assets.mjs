// Copies the Transformers.js web build plus the ONNX Runtime Web wasm
// binaries and glue modules into public/ so they are served same-origin
// (the classifier trial imports them at runtime, same pattern as wllama).
// Runs via the predev/prebuild hooks because node_modules can be recreated
// by npm ci.
import { cp, mkdir, readdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const transformersDist = path.join(frontendRoot, "node_modules", "@huggingface", "transformers", "dist");
const ortDist = path.join(frontendRoot, "node_modules", "onnxruntime-web", "dist");

const jobs = [
  {
    // transformers.js 的 web 构建带两个裸模块说明符，浏览器无法解析：
    // - static import of Tensor from "onnxruntime-common" → 指到 ORT bundle
    //   的同名导出（保证 Tensor 实现唯一）；
    // - static import * from "onnxruntime-web/webgpu" → ORT webgpu bundle。
    source: path.join(transformersDist, "transformers.web.min.js"),
    targetDir: path.join(frontendRoot, "public", "transformers"),
    targetName: "transformers.web.min.js",
    rewrites: [
      ['import{Tensor as nk}from"onnxruntime-common"', 'import{Tensor as nk}from"/transformers/ort/ort.webgpu.bundle.min.mjs"'],
      ['from"onnxruntime-web/webgpu"', 'from"/transformers/ort/ort.webgpu.bundle.min.mjs"'],
    ],
  },
  {
    sourceDir: ortDist,
    targetDir: path.join(frontendRoot, "public", "transformers", "ort"),
    // ort.bundle.min.mjs：直接用 ORT 的推理入口（transformers.js v4 的
    // web 构建在其 dev-JSEP ORT 上会话创建挂死，分类器试验改为直驱）。
    extraFiles: ["ort.bundle.min.mjs", "ort.webgpu.bundle.min.mjs"],
  },
];

for (const job of jobs) {
  await mkdir(job.targetDir, { recursive: true });
  if (job.sourceDir) {
    let copied = 0;
    for (const entry of await readdir(job.sourceDir)) {
      const wanted =
        job.extraFiles?.includes(entry) ||
        entry.endsWith(".wasm") ||
        entry.startsWith("ort-wasm-");
      if (!wanted) continue;
      await cp(path.join(job.sourceDir, entry), path.join(job.targetDir, entry));
      copied += 1;
    }
    console.log(`copied ${copied} files -> ${path.relative(frontendRoot, job.targetDir)}`);
  } else {
    const target = path.join(job.targetDir, job.targetName);
    await stat(job.source);
    let content = await readFile(job.source, "utf8");
    for (const [from, to] of job.rewrites ?? []) {
      if (!content.includes(from)) throw new Error(`rewrite source not found: ${from}`);
      content = content.replaceAll(from, to);
    }
    await writeFile(target, content);
    console.log(`copied -> ${path.relative(frontendRoot, target)}`);
  }
}
