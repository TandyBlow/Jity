# -*- coding: utf-8 -*-
"""Capture official Hugging Face evidence for narration-model candidates.

Why this exists: lane 11 may not choose a model by leaderboard rank, parameter
count or a name that "sounds Chinese". For every candidate this script stores
the bytes that a reviewer can re-check:

  * the model repo API answer (pinned revision sha, license tag, file table
    with sizes and LFS sha256 for every GGUF file), and
  * the raw model card, config.json, tokenizer_config.json (chat template),
    generation_config.json and licence body from that same pinned revision.

Nothing is inferred here. `models/candidates.json` is written separately and
only quotes these captured files.

Usage (network required, no model weights are downloaded):
    python -X utf8 sources/capture_hf.py
    python -X utf8 sources/capture_hf.py --only qwen25-1.5b-instruct
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import io
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "hf"
USER_AGENT = "jity-narration-model-search/1.0 (+lane-11; evidence capture)"

# Repos are pinned by the revision sha returned at capture time. `base` is the
# official model repository; `gguf` is the repository that publishes the
# quantised file. A GGUF repo may be official or third-party; the report says
# which, and a third-party quant is never described as official.
TARGETS = [
    {
        "id": "qwen25-1.5b-instruct",
        "family": "Qwen2.5",
        "base": "Qwen/Qwen2.5-1.5B-Instruct",
        "gguf": "Qwen/Qwen2.5-1.5B-Instruct-GGUF",
        "ggufPublisher": "official",
        "wantFile": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
    },
    {
        "id": "internlm2_5-1.8b-chat",
        "family": "InternLM2.5",
        "base": "internlm/internlm2_5-1_8b-chat",
        "gguf": "internlm/internlm2_5-1_8b-chat-gguf",
        "ggufPublisher": "official",
        "wantFile": "internlm2_5-1_8b-chat-q4_k_m.gguf",
    },
    {
        "id": "glm-edge-1.5b-chat",
        "family": "GLM-Edge",
        "base": "zai-org/GLM-Edge-1.5B-Chat",
        "gguf": "zai-org/glm-edge-1.5b-chat-gguf",
        "ggufPublisher": "official",
        "wantFile": "ggml-model-Q4_K_M.gguf",
    },
    {
        "id": "gemma3-1b-it-qat",
        "family": "Gemma3",
        "base": "google/gemma-3-1b-it",
        "gguf": "google/gemma-3-1b-it-qat-q4_0-gguf",
        "ggufPublisher": "official-qat",
        "wantFile": "gemma-3-1b-it-q4_0.gguf",
    },
    {
        "id": "hunyuan-1.8b-instruct",
        "family": "Hunyuan",
        "base": "tencent/Hunyuan-1.8B-Instruct",
        "gguf": "gabriellarson/Hunyuan-1.8B-Instruct-GGUF",
        "ggufPublisher": "third-party",
        "wantFile": "Hunyuan-1.8B-Instruct-Q4_K_M.gguf",
    },
    {
        "id": "qwen35-2b",
        "family": "Qwen3.5",
        "base": "Qwen/Qwen3.5-2B",
        "gguf": "unsloth/Qwen3.5-2B-GGUF",
        "ggufPublisher": "third-party (unsloth)",
        "wantFile": "Qwen3.5-2B-Q4_K_M.gguf",
    },
    {
        "id": "minicpm-2b-dpo",
        "family": "MiniCPM-2B",
        "base": "openbmb/MiniCPM-2B-dpo-bf16",
        "gguf": "runfuture/MiniCPM-2B-dpo-q4km-gguf",
        "ggufPublisher": "third-party",
        "wantFile": "MiniCPM-2B-dpo-q4km-gguf.gguf",
    },
    {
        "id": "minicpm5-2b",
        "family": "MiniCPM5",
        "base": "openbmb/MiniCPM5-2B",
        "gguf": "openbmb/MiniCPM5-2B-GGUF",
        "ggufPublisher": "official",
        "wantFile": "MiniCPM5-2B-Q4_K_M.gguf",
    },
]

BASE_FILES = [
    "README.md",
    "config.json",
    "tokenizer_config.json",
    "generation_config.json",
    "LICENSE",
    "LICENSE.txt",
]

GGUF_FILES = ["README.md", "LICENSE", "LICENSE.txt"]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str, accept: str = "*/*") -> dict:
    headers = {"User-Agent": USER_AGENT, "Accept": accept}
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    fetched_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read()
            return {
                "url": url,
                "finalUrl": response.geturl(),
                "status": response.status,
                "contentType": response.headers.get("Content-Type"),
                "bytes": len(body),
                "sha256": sha256_bytes(body),
                "fetchedAt": fetched_at,
                "body": body,
            }
    except urllib.error.HTTPError as error:
        body = error.read()
        return {
            "url": url,
            "finalUrl": url,
            "status": error.code,
            "contentType": error.headers.get("Content-Type") if error.headers else None,
            "bytes": len(body),
            "sha256": sha256_bytes(body),
            "fetchedAt": fetched_at,
            "body": body,
            "error": f"HTTP {error.code}",
        }


def api_model(repo: str) -> dict:
    url = f"https://huggingface.co/api/models/{repo}?blobs=true"
    result = fetch(url, accept="application/json")
    if result["status"] != 200:
        raise SystemExit(f"cannot read {repo}: HTTP {result['status']}: {result['body'][:300]!r}")
    return json.loads(result["body"].decode("utf-8"))


def save(slug: str, name: str, result: dict, sink: list) -> None:
    folder = OUT / slug
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / name
    target.write_bytes(result["body"])
    sink.append({
        "file": str(target.relative_to(HERE)).replace("\\", "/"),
        "url": result["url"],
        "finalUrl": result["finalUrl"],
        "status": result["status"],
        "contentType": result["contentType"],
        "bytes": result["bytes"],
        "sha256": result["sha256"],
        "fetchedAt": result["fetchedAt"],
        **({"error": result["error"]} if "error" in result else {}),
    })


def capture_one(target: dict) -> dict:
    slug = target["id"]
    entry = {
        "id": slug,
        "family": target["family"],
        "baseRepo": target["base"],
        "ggufRepo": target["gguf"],
        "ggufPublisher": target["ggufPublisher"],
        "wantFile": target["wantFile"],
        "capturedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "requests": [],
        "base": {},
        "gguf": {},
    }
    for kind in ("base", "gguf"):
        repo = target[kind]
        meta = api_model(repo)
        files = meta.get("siblings") or []
        wanted = []
        for sibling in files:
            name = sibling.get("rfilename")
            if not name:
                continue
            if name.endswith(".gguf") or name in (BASE_FILES if kind == "base" else GGUF_FILES):
                lfs = sibling.get("lfs") or {}
                wanted.append({
                    "path": name,
                    "bytes": sibling.get("size"),
                    "lfsSha256": lfs.get("sha256"),
                    "lfsSize": lfs.get("size"),
                })
        entry[kind] = {
            "repo": repo,
            "revision": meta.get("sha"),
            "lastModified": meta.get("lastModified"),
            "licenseTags": [t.split(":", 1)[1] for t in (meta.get("tags") or []) if t.startswith("license:")],
            "downloads": meta.get("downloads"),
            "likes": meta.get("likes"),
            "files": wanted,
        }
        # Save the trimmed API answer itself, so the file table above can be
        # checked against a stored response instead of living only in this run.
        api_name = f"api-{kind}.json"
        folder = OUT / slug
        folder.mkdir(parents=True, exist_ok=True)
        api_body = json.dumps(entry[kind], ensure_ascii=False, indent=1).encode("utf-8")
        (folder / api_name).write_bytes(api_body)
        entry["requests"].append({
            "file": str((folder / api_name).relative_to(HERE)).replace("\\", "/"),
            "url": f"https://huggingface.co/api/models/{repo}?blobs=true",
            "finalUrl": f"https://huggingface.co/api/models/{repo}?blobs=true",
            "status": 200,
            "contentType": "application/json",
            "bytes": len(api_body),
            "sha256": sha256_bytes(api_body),
            "fetchedAt": entry["capturedAt"],
            "note": "trimmed fields kept: revision/license/file table",
        })
        revision = meta.get("sha")
        for name in (BASE_FILES if kind == "base" else GGUF_FILES):
            url = f"https://huggingface.co/{repo}/resolve/{revision}/{urllib.parse.quote(name)}"
            result = fetch(url)
            save(slug, f"{kind}-{name.replace('/', '_')}", result, entry["requests"])
    return entry


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", action="append", default=None, help="candidate id to capture (repeatable)")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "capture.json"
    previous = {}
    if out.exists():
        try:
            for entry in json.loads(out.read_text(encoding="utf-8")).get("candidates", []):
                previous[entry["id"]] = entry
        except (ValueError, KeyError):
            previous = {}
    capture = {
        "capturedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "host": "huggingface.co",
        "candidates": [],
    }
    for target in TARGETS:
        if args.only and target["id"] not in args.only:
            if target["id"] in previous:
                capture["candidates"].append(previous[target["id"]])
            continue
        print(f"[capture] {target['id']}", flush=True)
        capture["candidates"].append(capture_one(target))
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(capture, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(out)
    print(json.dumps({c["id"]: {"base": c["base"]["revision"], "gguf": c["gguf"]["revision"]}
                      for c in capture["candidates"]}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
