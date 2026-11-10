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
