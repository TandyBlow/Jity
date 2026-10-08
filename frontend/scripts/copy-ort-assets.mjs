// Copies the stable ONNX Runtime Web browser bundle and its wasm runtime
// into public/ so they are served same-origin. The classifier/labeler trial
// scripts import the bundle directly at runtime (Transformers.js v4's web
// build was evaluated and rejected — see run-classifier-trial.mjs header).
// Runs via the predev/prebuild hooks because node_modules can be recreated
// by npm ci.
import { cp, mkdir, readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const ortDist = path.join(frontendRoot, "node_modules", "onnxruntime-web", "dist");
const targetDir = path.join(frontendRoot, "public", "ort");

await mkdir(targetDir, { recursive: true });
let copied = 0;
for (const entry of await readdir(ortDist)) {
  const wanted = entry === "ort.bundle.min.mjs" || entry.startsWith("ort-wasm-");
  if (!wanted) continue;
  await cp(path.join(ortDist, entry), path.join(targetDir, entry));
  copied += 1;
}
console.log(`copied ${copied} files -> ${path.relative(frontendRoot, targetDir)}`);
