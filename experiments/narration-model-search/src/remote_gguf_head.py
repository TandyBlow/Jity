# -*- coding: utf-8 -*-
"""Read a remote GGUF's metadata/tensor table through an HTTP range request.

Why: the full candidate file is ~1 GB and this lane must not download/run it
locally. But the GGUF header, metadata (including the chat template) and the
tensor table are at the front of the file, so a bounded range request can prove:

  * the actual `general.architecture` string (not the model card's claim),
  * the actual quantisation/tensor types (an unsupported type would show up),
  * the embedded chat template and its sha256,
  * the declared size label / licence metadata.

What this does NOT prove: that the weights are intact (the Hugging Face LFS
sha256 of the full file remains the identity) or that the model loads. Loading
is the HPC preflight and lane 09's browser run.

The prefix is written to a temp file, parsed, then deleted; only the summary is
kept. The response's ETag/Content-Range is recorded.

Usage:
    python -X utf8 src/remote_gguf_head.py --model-id hunyuan-1.8b-instruct
    python -X utf8 src/remote_gguf_head.py --model-id qwen25-1.5b-instruct --start-bytes 8388608
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import pathlib
import sys
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
CANDIDATES = ROOT / "models/candidates.json"
OUT = ROOT / "models/remote-heads"
TMP = OUT / ".tmp"
sys.path.insert(0, str(HERE))
from gguf_probe import read_gguf  # noqa: E402


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def fetch_prefix(url: str, length: int, destination: pathlib.Path) -> dict:
    request = urllib.request.Request(url, headers={
        "User-Agent": "jity-narration-model-search/1.0 (range probe)",
        "Range": f"bytes=0-{length - 1}",
        "Accept-Encoding": "identity",
    })
    with urllib.request.urlopen(request, timeout=120) as response:
        status = response.status
        headers = {key.lower(): value for key, value in response.headers.items()}
        if status == 200 and headers.get("content-length") and int(headers["content-length"]) > length:
            raise SystemExit("server ignored Range and would return the whole file; aborting")
        data = response.read()
    destination.write_bytes(data)
    return {
        "status": status,
        "url": url,
        "requestedBytes": length,
        "receivedBytes": len(data),
        "contentRange": headers.get("content-range"),
        "contentType": headers.get("content-type"),
        "etag": headers.get("etag"),
        "xLinkedEtag": headers.get("x-linked-etag"),
        "fetchedAt": now(),
        "prefixSha256": hashlib.sha256(data).hexdigest(),
        "note": "prefix hash is not the file hash; the full-file LFS sha256 in candidates.json is the identity",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--start-bytes", type=int, default=8 * 1024 * 1024)
    parser.add_argument("--max-bytes", type=int, default=192 * 1024 * 1024)
    args = parser.parse_args()

    registry = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    row = next((entry for entry in registry["candidates"] if entry["id"] == args.model_id), None)
    if row is None:
        raise SystemExit(f"unknown candidate id: {args.model_id}")
    gguf = row["gguf"]
    if not gguf.get("downloadUrl") and not gguf.get("repo"):
        raise SystemExit("candidate has no remote GGUF URL")
    url = gguf.get("downloadUrl") or (
        f"https://huggingface.co/{gguf['repo']}/resolve/{gguf['revision']}/{gguf['file']}")
    OUT.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    target = TMP / f"{args.model_id}.gguf"
    attempt = args.start_bytes
    last_error = None
    while attempt <= args.max_bytes:
        try:
            head = fetch_prefix(url, attempt, target)
            report = read_gguf(target)
            summary = report["summary"]
            template = report["metadata"].get("tokenizer.chat_template")
            if isinstance(template, str):
                template_path = OUT / f"{args.model_id}.template.txt"
                template_path.write_text(template, encoding="utf-8", newline="\n")
            verdict = {
                "candidateId": args.model_id,
                "fetchedAt": now(),
                "http": head,
                "fileIdentity": {
                    "repo": gguf["repo"],
                    "revision": gguf["revision"],
                    "file": gguf["file"],
                    "bytes": gguf["bytes"],
                    "lfsSha256": gguf["lfsSha256"],
                },
                "gguf": summary,
                "metadataSubset": {key: report["metadata"].get(key) for key in (
                    "general.architecture", "general.name", "general.license",
                    "general.license.name", "general.license.link",
                    "general.quantized_by", "general.file_type",
                    "tokenizer.chat_template",
                )},
                "chatTemplateFile": str(OUT / f"{args.model_id}.template.txt")
                    if isinstance(template, str) else None,
                "tensorTypeCount": summary["tensorTypes"],
                "createdAtSource": "range request against the pinned Hugging Face revision",
            }
            out = OUT / f"{args.model_id}.json"
            tmp = out.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(verdict, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            tmp.replace(out)
            print(json.dumps({
                "candidateId": args.model_id,
                "architecture": summary["architecture"],
                "name": summary["name"],
                "quantization": summary["quantization"],
                "tensorTypes": summary["tensorTypes"],
                "chatTemplateSha256": summary["chatTemplateSha256"],
                "contextLength": summary["contextLength"],
                "estimatedParameters": summary["estimatedParameters"],
                "receivedBytes": head["receivedBytes"],
                "contentRange": head["contentRange"],
                "etag": head["etag"] or head["xLinkedEtag"],
            }, ensure_ascii=False, indent=1))
            return 0
        except (ValueError, EOFError, OSError) as error:
            last_error = f"{type(error).__name__}: {error}"
            print(f"[{args.model_id}] {attempt} bytes not enough: {last_error}", file=sys.stderr)
            attempt *= 2
        finally:
            if target.exists():
                target.unlink()
    print(f"[{args.model_id}] failed after {args.max_bytes} bytes: {last_error}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
