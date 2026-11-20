# -*- coding: utf-8 -*-
"""Preview each candidate's embedded chat template with our frozen messages.

This is not inference and not the runtime renderer. It answers a narrower
question before HPC/browser work: does the GGUF's own template accept the
[system, user] message list we froze, and does it end with an assistant turn?

The renderer here is Python Jinja2 3.1.4, while the browser/llama.cpp use
minja. Whitespace and a few filters can differ, so the output is labelled a
preview; `screen.py` on the HPC and lane 09's browser run remain authoritative.

Usage:
    python -X utf8 src/preview_templates.py
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

import jinja2

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "evidence/template-previews"
PROMPTS = ROOT / "evidence/prompts-dev-v1/prompts.jsonl"

# Minimal special tokens; the GGUF template only interpolates them as text.
TOKENS = {"bos_token": "<s>", "eos_token": "</s>", "unk_token": "<unk>", "pad_token": "<pad>"}


def main() -> int:
    candidates = json.loads((ROOT / "models/candidates.json").read_text(encoding="utf-8"))["candidates"]
    prompts = [json.loads(line) for line in PROMPTS.read_text(encoding="utf-8").splitlines() if line.strip()]
    sample = prompts[0]
    OUT.mkdir(parents=True, exist_ok=True)
    environment = jinja2.Environment(trim_blocks=True, lstrip_blocks=False, autoescape=False)
    summary = []
    for row in candidates:
        template_file = (row.get("operatorEvidence") or {}).get("chatTemplateFile")
        if not template_file or not pathlib.Path(template_file).exists():
            summary.append({"id": row["id"], "rendered": False, "reason": "no captured GGUF template"})
            continue
        template_text = pathlib.Path(template_file).read_text(encoding="utf-8")
        kwargs = row.get("chatTemplateKwargs") or {}
        try:
            template = environment.from_string(template_text)
            messages = [
                {"role": "system", "content": sample["system"]},
                {"role": "user", "content": sample["user"]},
            ]
            rendered = template.render(
                messages=messages, add_generation_prompt=True, tools=None,
                **TOKENS, **kwargs,
            )
        except Exception as error:  # noqa: BLE001 - report the template's real failure
            summary.append({"id": row["id"], "rendered": False,
                            "reason": f"{type(error).__name__}: {error}"})
            continue
        out = OUT / f"{row['id']}.txt"
        out.write_text(rendered, encoding="utf-8", newline="\n")
        has_assistant_tail = any(marker in rendered[-120:] for marker in
                                 ("assistant", "<|assistant|>", "<|im_start|>assistant",
                                  "<｜hy_Assistant｜>", "助手"))
        summary.append({
            "id": row["id"],
            "rendered": True,
            "chars": len(rendered),
            "sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
            "templateKwargs": kwargs,
            "hasAssistantTail": has_assistant_tail,
            "literalTemplateLeft": "{{" in rendered or "{%" in rendered,
            "containsBodyMarker": "【正文】" in rendered,
            "containsSystemText": sample["system"] in rendered,
            "head": rendered[:160],
            "tail": rendered[-160:],
            "file": str(out),
        })
    report = {
        "engine": "jinja2 3.1.4",
        "warning": "preview only: llama.cpp/minja and browser wllama are authoritative. "
                   "Whitespace/filter differences are possible.",
        "sampleCaseId": sample["caseId"],
        "promptSha256": sample["promptSha256"],
        "results": summary,
    }
    (OUT / "preview.manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    attempted = [entry for entry in summary if entry.get("rendered") is not None
                 and "no captured GGUF template" not in str(entry.get("reason", ""))]
    ok = bool(attempted) and all(
        entry.get("rendered") and not entry.get("literalTemplateLeft")
        and entry.get("containsBodyMarker") and entry.get("containsSystemText")
        for entry in attempted
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
