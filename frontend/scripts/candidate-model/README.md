# Candidate-model scripts (A route: local instruct models)

Real-device tooling for the model/runtime half of the A route. The product
model code is in `frontend/src/lib/world-engine/local/narration-candidates/model-runtime/`.

## `gguf-meta.mjs`

Reads the GGUF metadata block (no weights loaded) and prints the fields a
foreign checkpoint needs: architecture, context length, tokenizer identity and
the exact `tokenizer.chat_template`.

```bash
node scripts/candidate-model/gguf-meta.mjs --file <path.gguf> --out ../.local/candidate-model/meta/<name>.json
```

Use it before adding a checkpoint to the catalog. A checkpoint without
`tokenizer.chat_template` cannot be driven as a chat model.

## `probe-models.mjs`

One real browser run per catalog model:

1. verifies the exact file size + SHA-256 against the catalog on the host;
2. loads the GGUF through `loadCandidateModel` (WebGPU first, CPU fallback
   recorded with its error);
3. generates one frozen committed point (`林川 走廊→门厅`, 2 minutes, POV
   周宁) through `generateCandidate`;
4. records load time, first readable character, per-call llama.cpp timings
   (prompt/predicted tokens), the model's full text, the alignment verdict and
   the GPU memory peak sampled from the host.

```bash
# from frontend/, with the inference lease held
python ../../.local/parallel-local-game/resource_lease.py acquire --lane 08-runtime --purpose "candidate model probe"
node scripts/candidate-model/probe-models.mjs \
  --model qwen2.5-1.5b-instruct-q4km --model qwen3-1.7b-q4km \
  --out ../.local/candidate-model/probe.json
python ../../.local/parallel-local-game/resource_lease.py release --lane 08-runtime
```

Model files are found read-only in the shared directories
(`--models-dir` repeatable; defaults: the narration worktree's `public/models`,
the main tree's `public/models`, `.local/models`). Nothing is copied.

Useful flags: `--max-tokens`, `--threads`, `--context`, `--force-cpu`,
`--cpu-compare <catalog-id>` (same model on CPU, for an honest backend
comparison), `--channel`, `--out`.

## Split GGUF (browser whole-file limit)

wllama 3.8.1 materialises a model through `fetch().arrayBuffer()`, so a single
file of 2.5 GB (Qwen3-4B Q4_K_M) fails to load even though the HTTP fetch and
Range requests work. The supported workaround is a real GGUF split, not a byte
split:

```bash
D:/others/Jity/.local/llama-cpp/llama-gguf-split.exe --split --split-max-size 1300M   <model>.gguf <out>/<model>.gguf
```

This writes `<model>.gguf-00001-of-00002.gguf` (1.22 GiB) and
`...-00002-of-00002.gguf` (1.11 GiB). Shard 1 keeps the metadata and chat
template; shard 2 keeps the remaining tensors. Native validation with
`llama-cli -m <shard1> -c 2048 -ngl 0` is the quickest way to prove the split
is loadable before asking 09 for a browser window.

`WllamaInferenceEngine` accepts `modelUrls: string[]` or a single first-shard
`modelUrl`; it expands `-00001-of-00002.gguf` to all siblings, fetches every
shard in the direct-blob path and passes the blobs in order. wllama renames
them to its canonical `model-00001-of-00002.gguf` names and llama.cpp opens the
siblings. The non-blob `loadModelFromUrl` path rejects a split (wllama's URL
API only accepts one file).

## `probe-two-shards.mjs`

Loads no model and runs no inference. It answers whether the browser can hold
the **aggregate** of two shards at once, which is what wllama's Blob loader
requires. Fresh-page result for the 4B split (2.5 GB total): the first 1.3 GB
shard became a Blob, the second failed with `TypeError: Failed to fetch`, while
`navigator.storage.quota` was 10 GiB and the JS heap was ~1 MB — the Blob
store, not disk or heap, is the limit. The same two shards in `arraybuffer`
mode fit (2.38 GB of a 4.19 GB heap) but took 142 s + 140 s to fetch, already
over the whole-point budget before compile. Do not propose a >2 GB total model
on this loader.

```bash
node scripts/candidate-model/probe-two-shards.mjs --dir ../.local/models/qwen3-4b-split --mode blob --out ../.local/candidate-model/two-shards-blob.json
```

## Honest backend reporting

wllama has no public "which ggml backend ran" flag. The probe therefore
reports, separately:

- `webgpuAvailable` (the browser exposes `navigator.gpu`);
- the load attempts (`backend: webgpu|cpu`, `gpuLayers`, error);
- llama.cpp timing fields (`prompt_n`, `predicted_n`, `predicted_ms`) so
  throughput can be computed from the model's own counters;
- page console lines matching `webgpu|ggml|backend|vulkan|cuda|adapter`;
- the host-side GPU memory peak during the run.

`backend: 'webgpu'` means the engine loaded with `n_gpu_layers=99999` after
the WebGPU attempt succeeded. It is not a claim about layer placement; the
GPU-memory sample and the CPU comparison are the supporting evidence.

## 先确认是哪个 GPU（不加载模型）

```bash
python ../../.local/parallel-local-game/resource_lease.py acquire --lane 08-runtime --purpose "adapter probe"
node scripts/candidate-model/probe-adapter.mjs --out ../.local/candidate-model/adapter.json
python ../../.local/parallel-local-game/resource_lease.py release --lane 08-runtime
```

连续启动两次浏览器：一次 `--force_high_performance_gpu`，一次
`--force_low_power_gpu`，各打印 `requestAdapter()` / `requestAdapter({powerPreference:
'high-performance'})` 的 vendor/architecture/limits。`backend:'webgpu'` 只说明
WebGPU 路径可用；到底是独显还是核显，看这里的 vendor，以及运行日志里的
`ggml_webgpu: adapter_info:`。

## 大模型能不能读进来（不推理）

```bash
node scripts/candidate-model/probe-fetch.mjs --file Qwen3-4B-Instruct-2507-Q4_K_M.gguf
```

在真实浏览器里对模型 URL 做 HEAD、`Range: bytes=0-1023`、读 1 MiB 流、再
`arrayBuffer()`。2026-11-10 的结果：前三项都正常（200/206/1 MiB），
`arrayBuffer()` 对 2.5 GB 的 4B 返回 **Failed to fetch**；1.1 GB 的 1.7B 成功。
wllama 3.8.1 的加载路径最后就是整文件 `arrayBuffer()`，所以 2.5 GB 单文件
**在 WebGPU 和 CPU 上都进不来**。要上 4B 得换小于 2 GB 的量化、真正的 GGUF
分片（`llama-gguf-split`），或流式写 OPFS 的加载器。

脚本的模型服务用 `gguf-server.mjs`，支持 `Accept-Ranges` 和 206；生产模型
服务器也应如此（换加载器时是前提）。
