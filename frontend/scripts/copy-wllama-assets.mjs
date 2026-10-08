// Copies the built wllama ESM bundle and its wasm runtime into public/ so
// they are served same-origin. The package resolves to its TypeScript source
// under webpack (its "main" points at a missing index.js), so the benchmark
// loads the built bundle at runtime instead of importing it at build time.
// Runs via the predev/prebuild hooks because node_modules can be recreated
// by npm ci.
import { copyFile, mkdir, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const packageRoot = path.join(frontendRoot, "node_modules", "@wllama", "wllama", "esm");

const files = [
  {
    source: path.join(packageRoot, "wasm", "wllama.wasm"),
    targetDir: path.join(frontendRoot, "public", "wasm"),
    targetName: "wllama.wasm",
  },
  {
    source: path.join(packageRoot, "index.min.js"),
    targetDir: path.join(frontendRoot, "public", "wllama"),
    targetName: "index.min.js",
  },
];

for (const file of files) {
  const target = path.join(file.targetDir, file.targetName);
  try {
    const [sourceStats, targetStats] = await Promise.all([
      stat(file.source),
      stat(target).catch(() => null),
    ]);
    if (targetStats && targetStats.size === sourceStats.size) continue;
    await mkdir(file.targetDir, { recursive: true });
    await copyFile(file.source, target);
    console.log(`copied ${file.targetName} -> public/${path.basename(file.targetDir)}/`);
  } catch (error) {
    if (error.code === "ENOENT") {
      console.warn(
        `${file.source} not found (is @wllama/wllama installed?); skipping`,
      );
      continue;
    }
    throw error;
  }
}
