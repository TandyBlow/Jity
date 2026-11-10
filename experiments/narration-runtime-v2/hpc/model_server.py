# -*- coding: utf-8 -*-
"""HTTP model server for offline batches driven by a local engine.

The page's TypeScript engine build and apply logic cannot run on the cluster (no
node), and the product engine cannot run without a model. So the split is:

    local node + vite SSR (real product modules)  <--HTTP-->  this server (GPU)

Endpoint contract (one request at a time, model stays loaded):

    POST /complete {"prompt": str, "maxNew": int, "temperature": float, "seed": int}
      -> {"text": str, "ms": int, "promptChars": int, "newTokens": int,
          "finishReason": "stop"|"length"}

    GET /health -> {"ok": true, "model": ..., "device": ..., "dtype": ...}

The server never edits, judges or rewrites a prompt: it applies the Qwen chat
template exactly like wllama does and returns raw text plus timings. Any
interpretation belongs to the caller (lane 04) and to 01's checks.

    python hpc/model_server.py --model ~/qwen15b --port 18080 --dtype float16
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATE = {"model": None, "tokenizer": None, "device": "cpu", "dtype": "float32",
         "modelPath": "", "system": "You are Qwen, created by Alibaba Cloud. You are a helpful assistant.",
         "lock": threading.Lock()}


def load(model_path: str, dtype: str, device: str) -> None:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    STATE["tokenizer"] = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    torch_dtype = {"float16": torch.float16, "bfloat16": torch.bfloat16,
                   "float32": torch.float32}[dtype]
    model = AutoModelForCausalLM.from_pretrained(
        model_path, local_files_only=True, torch_dtype=torch_dtype)
    model = model.to(device)
    model.eval()
    STATE.update({"model": model, "device": device, "dtype": dtype, "modelPath": model_path})


def generate(prompt: str, max_new: int, temperature: float, seed: int | None) -> dict:
    import torch

    model = STATE["model"]
    tokenizer = STATE["tokenizer"]
    system = STATE["system"]
    chat = (f"<|im_start|>system\n{system}<|im_end|>\n"
            f"<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n")
    encoded = tokenizer(chat, return_tensors="pt").to(STATE["device"])
    with STATE["lock"]:
        if seed is not None:
            torch.manual_seed(int(seed))
        started = time.time()
        with torch.no_grad():
            out = model.generate(
                **encoded, max_new_tokens=max_new,
                do_sample=temperature > 0,
                temperature=max(temperature, 1e-5), top_p=0.9,
                pad_token_id=tokenizer.eos_token_id)
        seconds = time.time() - started
    new_tokens = int(out.shape[1] - encoded["input_ids"].shape[1])
    text = tokenizer.decode(out[0][encoded["input_ids"].shape[1]:], skip_special_tokens=True)
    finish = "length" if new_tokens >= max_new else "stop"
    return {"text": text, "ms": int(seconds * 1000), "promptChars": len(prompt),
            "promptTokens": int(encoded["input_ids"].shape[1]),
            "newTokens": new_tokens, "finishReason": finish}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # keep the job log readable
        sys.stderr.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"ok": STATE["model"] is not None, "model": STATE["modelPath"],
                             "device": STATE["device"], "dtype": STATE["dtype"]})
        else:
            self._send(404, {"error": "not_found"})

    def do_POST(self):
        if self.path != "/complete":
            self._send(404, {"error": "not_found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            request = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception as error:  # noqa: BLE001 - report, do not crash
            self._send(400, {"error": f"bad_json: {error}"})
            return
        prompt = request.get("prompt")
        if not isinstance(prompt, str) or not prompt:
            self._send(400, {"error": "prompt_required"})
            return
        try:
            result = generate(prompt, int(request.get("maxNew", 240)),
                              float(request.get("temperature", 0.4)),
                              request.get("seed"))
        except Exception as error:  # noqa: BLE001 - surface the failure to the caller
            self._send(500, {"error": f"generate_failed: {error}"})
            return
        self._send(200, result)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--dtype", default="float16", choices=("float16", "bfloat16", "float32"))
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    load(os.path.expanduser(args.model), args.dtype, args.device)
    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print(json.dumps({"ready": True, "port": args.port, "device": args.device,
                      "dtype": args.dtype, "model": STATE["modelPath"]}), flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
