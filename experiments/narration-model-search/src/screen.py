# -*- coding: utf-8 -*-
"""Run one frozen prompt batch against one GGUF on llama.cpp (llama-server).

Where this runs: lane 10's HPC only. This repository lane never starts a local
GPU/browser model run; lane 09 owns the real Edge+wllama product run. The same
prompts therefore go through the model's own GGUF chat template on llama-server
(`--jinja`), which is the closest offline equivalent of wllama applying the
template in the browser.

What is recorded per case, not just the text:
  * the exact HTTP request body (messages, sampling, seed),
  * the raw response JSON (usage, timings, finish_reason),
  * wall-clock milliseconds, prompt/predicted token counts and token/s,
  * the server stderr tail for architecture/backend lines and errors.

The server is started once per model and reused for every case, so load time is
measured once and generation time is not mixed with it.

Usage (plan only, safe without a model):
    python -X utf8 src/screen.py --dry-run --model-id qwen25-1.5b-instruct

Real run (only on the HPC worker):
    python -X utf8 src/screen.py \
      --prompts evidence/frozen/prompts.jsonl \
      --prompt-manifest evidence/frozen/prompts.manifest.json \
      --model-id internlm2_5-1.8b-chat \
      --model-path /scratch/models/internlm2_5-1_8b-chat-q4_k_m.gguf \
      --expect-sha256 <lfs sha256> \
      --llama-server /scratch/llama.cpp/build/bin/llama-server \
      --out evidence/runs/batch-1/internlm2_5-1.8b-chat
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import pathlib
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
CANDIDATES = ROOT / "models/candidates.json"


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def http_json(url: str, payload: dict | None = None, timeout: float = 30.0) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            return response.status, json.loads(body.decode("utf-8")) if body else {}
    except urllib.error.HTTPError as error:
        body = error.read()
        try:
            parsed = json.loads(body.decode("utf-8"))
        except ValueError:
            parsed = {"raw": body.decode("utf-8", errors="replace")}
        return error.code, parsed


def wait_health(port: int, process: subprocess.Popen, timeout_s: float, log_path: pathlib.Path) -> float:
    started = time.monotonic()
    url = f"http://127.0.0.1:{port}/health"
    while time.monotonic() - started < timeout_s:
        if process.poll() is not None:
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:] if log_path.exists() else ""
            raise SystemExit(f"llama-server exited before health ({process.returncode}):\n{tail}")
        try:
            status, body = http_json(url, timeout=3.0)
            if status == 200:
                return time.monotonic() - started
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(0.5)
    raise SystemExit(f"llama-server did not become healthy within {timeout_s}s")


def load_prompts(prompts_path: pathlib.Path, manifest_path: pathlib.Path, allow_provisional: bool) -> tuple[list, dict]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("frozen") and not allow_provisional:
        raise SystemExit("prompt manifest is not frozen (01's package/rubric not pinned); refusing to run")
    prompts = [json.loads(line) for line in prompts_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    recorded_sha = manifest.get("promptsSha256")
    actual_sha = sha256_file(prompts_path)
    if recorded_sha and recorded_sha != actual_sha:
        raise SystemExit(f"prompts sha256 mismatch: on disk {actual_sha}, manifest {recorded_sha}")
    return prompts, manifest


def candidate_row(model_id: str) -> dict | None:
    if not CANDIDATES.exists():
        return None
    data = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    for row in data.get("candidates", []):
        if row["id"] == model_id:
            return row
    for row in data.get("baselines", []):
        if row["id"] == model_id:
            return row
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompts", type=pathlib.Path, default=None)
    parser.add_argument("--prompt-manifest", type=pathlib.Path, default=None)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--model-path", type=pathlib.Path, default=None,
                        help="default: the local path recorded in models/candidates.json")
    parser.add_argument("--expect-sha256", default=None)
    parser.add_argument("--llama-server", default="llama-server")
    parser.add_argument("--ngl", type=int, default=0, help="GPU layers; 0 = CPU")
    parser.add_argument("--threads", type=int, default=0)
    parser.add_argument("--context", type=int, default=8192)
    parser.add_argument("--out", type=pathlib.Path, default=None)
    parser.add_argument("--load-timeout", type=float, default=600.0)
    parser.add_argument("--case-timeout", type=float, default=600.0)
    parser.add_argument("--template-kwargs", default=None,
                        help="JSON for llama-server chat_template_kwargs; default: the candidate "
                             "row's chatTemplateKwargs (Hunyuan/Qwen3.5 need enable_thinking=false)")
    parser.add_argument("--allow-provisional", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="debug only: first N prompts")
    args = parser.parse_args()

    row = candidate_row(args.model_id)
    model_path = args.model_path
    if model_path is None and row:
        local = (row.get("gguf") or {}).get("local") or row.get("path")
        if isinstance(local, dict):
            local = local.get("path")
        if local:
            model_path = pathlib.Path(local)

    plan = {
        "modelId": args.model_id,
        "modelPath": str(model_path) if model_path else None,
        "candidateRowFound": row is not None,
        "prompts": str(args.prompts) if args.prompts else None,
        "promptManifest": str(args.prompt_manifest) if args.prompt_manifest else None,
        "sampling": (json.loads(args.prompt_manifest.read_text(encoding="utf-8")).get("sampling")
                     if args.prompt_manifest and args.prompt_manifest.exists() else None),
        "backend": "llama-server --jinja (the GGUF's own chat template)",
        "ngl": args.ngl,
        "context": args.context,
        "templateKwargs": (json.loads(args.template_kwargs) if args.template_kwargs is not None
                           else (row or {}).get("chatTemplateKwargs") or {}),
        "note": "This lane never runs this: lane 10 executes the HPC batch, lane 09 runs the browser acceptance.",
    }
    if args.dry_run:
        print(json.dumps(plan, ensure_ascii=False, indent=1))
        return 0

    if not args.prompts or not args.prompt_manifest:
        raise SystemExit("--prompts and --prompt-manifest are required unless --dry-run")
    if not model_path or not model_path.exists():
        raise SystemExit(f"model file missing: {model_path}")
    prompts, prompt_manifest = load_prompts(args.prompts, args.prompt_manifest, args.allow_provisional)
    if args.limit:
        prompts = prompts[: args.limit]
    sampling = prompt_manifest["sampling"]
    template_kwargs = (json.loads(args.template_kwargs) if args.template_kwargs is not None
                       else (row or {}).get("chatTemplateKwargs") or {})

    model_sha = sha256_file(model_path)
    if args.expect_sha256 and model_sha.lower() != args.expect_sha256.lower():
        raise SystemExit(f"model sha256 mismatch: file {model_sha}, expected {args.expect_sha256}")

    out = args.out or (ROOT / "evidence/runs" / args.model_id)
    out.mkdir(parents=True, exist_ok=True)
    log_path = out / "llama-server.log"
    port = free_port()
    command = [
        args.llama_server, "-m", str(model_path),
        "-c", str(args.context), "-ngl", str(args.ngl), "-np", "1",
        "--jinja", "--host", "127.0.0.1", "--port", str(port), "--no-webui",
    ]
    if args.threads:
        command.extend(["-t", str(args.threads)])
    log_handle = open(log_path, "w", encoding="utf-8", newline="\n")
    started_at = now_iso()
    process = subprocess.Popen(command, stdout=log_handle, stderr=subprocess.STDOUT)
    results = []
    load_seconds = None
    fatal = None
    try:
        load_seconds = wait_health(port, process, args.load_timeout, log_path)
        for index, prompt in enumerate(prompts):
            payload = {
                "messages": [
                    {"role": "system", "content": prompt["system"]},
                    {"role": "user", "content": prompt["user"]},
                ],
                "temperature": sampling["temperature"],
                "top_k": sampling["topK"],
                "top_p": sampling["topP"],
                "seed": sampling["seed"],
                "max_tokens": sampling["maxTokens"],
                "stop": sampling["stop"],
                "stream": False,
                "cache_prompt": False,
                **({"chat_template_kwargs": template_kwargs} if template_kwargs else {}),
            }
            started = time.monotonic()
            status, body = http_json(f"http://127.0.0.1:{port}/v1/chat/completions",
                                     payload, timeout=args.case_timeout)
            wall_ms = round((time.monotonic() - started) * 1000)
            choice = (body.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            timings = body.get("timings") or {}
            record = {
                "caseId": prompt["caseId"],
                "inputSha256": prompt["inputSha256"],
                "promptSha256": prompt["promptSha256"],
                "modelId": args.model_id,
                "modelSha256": model_sha,
                "request": payload,
                "httpStatus": status,
                "text": message.get("content"),
                "finishReason": choice.get("finish_reason"),
                "usage": body.get("usage"),
                "timings": timings,
                "wallMs": wall_ms,
                "error": body.get("error") if status != 200 else None,
                "recordedAt": now_iso(),
            }
            results.append(record)
            (out / f"{prompt['caseId']}.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            print(f"[{index + 1}/{len(prompts)}] {prompt['caseId']} http={status} "
                  f"chars={len(record['text'] or '')} wall={wall_ms}ms", flush=True)
    except BaseException as error:  # keep the manifest truthful even on Ctrl-C
        fatal = f"{type(error).__name__}: {error}"
        raise
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
        log_handle.close()
        stderr_tail = log_path.read_text(encoding="utf-8", errors="replace")[-6000:]
        run_manifest = {
            "modelId": args.model_id,
            "modelPath": str(model_path),
            "modelSha256": model_sha,
            "candidateRow": row,
            "promptManifest": prompt_manifest,
            "promptManifestPath": str(args.prompt_manifest),
            "samplingUsed": sampling,
            "chatTemplateKwargs": template_kwargs,
            "llamaServer": args.llama_server,
            "command": command,
            "startedAt": started_at,
            "finishedAt": now_iso(),
            "loadSeconds": load_seconds,
            "ngl": args.ngl,
            "context": args.context,
        "templateKwargs": (json.loads(args.template_kwargs) if args.template_kwargs is not None
                           else (row or {}).get("chatTemplateKwargs") or {}),
            "threads": args.threads or None,
            "caseCount": len(results),
            "completed": sum(1 for r in results if r["httpStatus"] == 200 and (r["text"] or "").strip()),
            "fatal": fatal,
            "serverLogTail": stderr_tail,
            "environment": {"python": sys.version.split()[0], "platform": sys.platform},
        }
        (out / "run-manifest.json").write_text(
            json.dumps(run_manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out), "loadSeconds": load_seconds, "cases": len(results)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
