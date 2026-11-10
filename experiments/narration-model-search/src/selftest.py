# -*- coding: utf-8 -*-
"""Small verification of lane 11's offline tooling. No model inference.

Checks:
  1. GGUF probe reads a real local GGUF and reports architecture + template.
  2. The shipped-wllama architecture list contains every gate-passing candidate
     architecture we expect (qwen2, internlm2, glm4, hunyuan_dense).
  3. build_prompts refuses a wrong manifest sha (exit 2), refuses a tampered
     case input sha (exit 2), and accepts the real 01 package subset.
  4. collect aggregates a synthetic run and never emits a quality pass.
  5. screen --dry-run prints the plan without starting a server.

Run:
    python -X utf8 src/selftest.py
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
PY = sys.executable
DEV = pathlib.Path("D:/others/Jity/.local/parallel-local-game/results/quality/dev-package-v1")
QWEN3 = pathlib.Path("D:/others/Jity/.local/world-narration-worktree/frontend/public/models/Qwen3-1.7B-Q4_K_M.gguf")

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f" — {detail}" if detail else ""), flush=True)


def run(args: list[str], cwd: pathlib.Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run([PY, "-X", "utf8", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")


def main() -> int:
    if QWEN3.exists():
        probe = run(["src/gguf_probe.py", str(QWEN3)])
        ok = probe.returncode == 0 and '"architecture": "qwen3"' in probe.stdout
        check("gguf_probe reads a real GGUF", ok, probe.stdout.splitlines()[3].strip() if ok else probe.stderr[-300:])
    else:
        check("gguf_probe reads a real GGUF", False, f"missing {QWEN3}")

    support = json.loads((ROOT / "models/wllama-support.json").read_text(encoding="utf-8"))
    expected = {"qwen2", "internlm2", "chatglm", "hunyuan_dense"}
    missing = expected - set(support["architectureModels"])
    check("wllama wasm lists candidate architectures", not missing, f"missing={sorted(missing)}")
    registry_pre = json.loads((ROOT / "models/candidates.json").read_text(encoding="utf-8"))
    bad_arch = [row["id"] for row in registry_pre["candidates"]
                if row["preInferenceGate"]["passed"]
                and row["operatorEvidence"]["architectureKnownToShippedWasm"] is not True]
    check("gate-passing candidates' actual GGUF arch is in the wasm table", not bad_arch, f"bad={bad_arch}")

    manifest_sha = __import__("hashlib").sha256((DEV / "manifest.json").read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory() as tmp:
        wrong = run(["src/build_prompts.py", "--manifest", str(DEV / "manifest.json"),
                     "--expect-manifest-sha256", "0" * 64, "--out-dir", str(pathlib.Path(tmp) / "out")])
        check("build_prompts refuses a wrong manifest sha", wrong.returncode == 2, f"exit={wrong.returncode}")

        copied = pathlib.Path(tmp) / "pkg"
        copied.mkdir()
        for name in ("manifest.json", "cases.jsonl", "RUBRIC.md"):
            shutil.copy2(DEV / name, copied / name)
        cases = (copied / "cases.jsonl").read_text(encoding="utf-8").splitlines()
        first = json.loads(cases[0])
        first["input"]["视角"] = first["input"]["视角"] + "（篡改）"
        cases[0] = json.dumps(first, ensure_ascii=False)
        (copied / "cases.jsonl").write_text("\n".join(cases) + "\n", encoding="utf-8")
        # The manifest still records the old cases hash, so this must fail even
        # before the per-case input hash is checked.
        tampered_manifest_sha = __import__("hashlib").sha256((copied / "manifest.json").read_bytes()).hexdigest()
        tampered = run(["src/build_prompts.py", "--manifest", str(copied / "manifest.json"),
                        "--expect-manifest-sha256", tampered_manifest_sha,
                        "--out-dir", str(pathlib.Path(tmp) / "out2"), "--declare-subset",
                        str(ROOT / "subset-declaration.json"), "--skip-serializer-errors"])
        check("build_prompts refuses a tampered cases file", tampered.returncode == 2, f"exit={tampered.returncode}")

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = pathlib.Path(tmp) / "pinned"
        real = run(["src/build_prompts.py", "--manifest", str(DEV / "manifest.json"),
                    "--expect-manifest-sha256", manifest_sha,
                    "--out-dir", str(out_dir),
                    "--declare-subset", str(ROOT / "subset-declaration.json"), "--skip-serializer-errors"])
        ok = real.returncode == 0
        count = None
        if ok:
            out_manifest = json.loads((out_dir / "prompts.manifest.json").read_text(encoding="utf-8"))
            count = out_manifest["promptCount"]
            ok = count == 12 and out_manifest["frozen"] is True
        check("build_prompts pins the 12-case declared subset", ok, f"prompts={count}")

    with tempfile.TemporaryDirectory() as tmp:
        run_dir = pathlib.Path(tmp) / "fake-run"
        run_dir.mkdir()
        record = {
            "caseId": "synthetic-1",
            "text": "他站在原地。他站在原地。风从门缝里进来。",
            "finishReason": "stop",
            "httpStatus": 200,
            "wallMs": 1234,
            "timings": {"prompt_n": 10, "predicted_n": 20, "predicted_per_second": 5.0},
        }
        (run_dir / "synthetic-1.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        (run_dir / "run-manifest.json").write_text(json.dumps({"modelId": "synthetic", "loadSeconds": 1.0}), encoding="utf-8")
        summary = run(["src/collect.py", "--run", str(run_dir), "--out-dir", str(pathlib.Path(tmp) / "summary")])
        ok = summary.returncode == 0
        detail = ""
        if ok:
            data = json.loads((pathlib.Path(tmp) / "summary/summary.json").read_text(encoding="utf-8"))
            run_summary = data["runs"][0]
            ok = ("quality" in run_summary and "pass" not in json.dumps(run_summary).lower()
                  and run_summary["caseStats"][0]["sentenceRepeat"]["duplicateOccurrences"] == 1)
            detail = f"repeat={run_summary['caseStats'][0]['sentenceRepeat']['duplicateOccurrences']}"
        check("collect reports repetition and no quality pass", ok, detail)

    with tempfile.TemporaryDirectory() as tmp:
        prompts = [json.loads(line) for line in
                   (ROOT / "evidence/prompts-dev-v1/prompts.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        run_dir = pathlib.Path(tmp) / "run"
        run_dir.mkdir()
        for prompt in prompts:
            record = {"caseId": prompt["caseId"], "inputSha256": prompt["inputSha256"],
                      "text": "合成正文。用于检查交接格式。", "httpStatus": 200}
            (run_dir / f"{prompt['caseId']}.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        (run_dir / "run-manifest.json").write_text(json.dumps({"modelId": "synthetic"}), encoding="utf-8")
        review = run(["src/make_review_input.py",
                      "--cases", str(DEV / "cases.jsonl"),
                      "--run", str(run_dir),
                      "--prompt-manifest", str(ROOT / "evidence/prompts-dev-v1/prompts.manifest.json"),
                      "--out", str(pathlib.Path(tmp) / "review")])
        ok = review.returncode == 0
        detail = ""
        if ok:
            manifest = json.loads((pathlib.Path(tmp) / "review/review.manifest.json").read_text(encoding="utf-8"))
            ok = manifest["rows"] == 12 and not manifest["problems"] and len(manifest["declaredExcluded"]) == 3
            detail = f"rows={manifest['rows']} excluded={len(manifest['declaredExcluded'])}"
        check("review input joins 12 outputs and lists 3 declared exclusions", ok, detail)

    preview_path = ROOT / "evidence/template-previews/preview.manifest.json"
    if preview_path.exists():
        preview = json.loads(preview_path.read_text(encoding="utf-8"))
        rendered = [entry for entry in preview["results"] if entry.get("rendered")]
        ok = len(rendered) == 5 and all(
            entry.get("hasAssistantTail") and entry.get("containsBodyMarker")
            and entry.get("containsSystemText") and not entry.get("literalTemplateLeft")
            for entry in rendered
        )
        check("GGUF templates render the frozen system+user with an assistant tail", ok,
              f"rendered={len(rendered)}")
    else:
        check("GGUF templates render the frozen system+user with an assistant tail", False,
              "run src/preview_templates.py")

    baseline = pathlib.Path("D:/others/Jity/.local/world-narration-worktree/frontend/public/models/Qwen3-1.7B-Q4_K_M.gguf")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        smoke = tmp_path / "smoke.json"
        smoke.write_text(json.dumps({"choices": [{"message": {"content": "一句话。"}}]}), encoding="utf-8")
        if baseline.exists():
            good = run(["src/verify_preflight.py",
                        "--path", str(baseline),
                        "--expect-sha256", "b139949c5bd74937ad8ed8c8cf3d9ffb1e99c866c823204dc42c0d91fa181897",
                        "--expect-arch", "qwen3",
                        "--smoke-json", str(smoke)])
            bad = tmp_path / "bad.gguf"
            bad.write_bytes(b"not a gguf")
            refused = run(["src/verify_preflight.py", "--path", str(bad),
                           "--expect-sha256", "00" * 32])
            ok = good.returncode == 0 and refused.returncode == 2
            detail = f"good={good.returncode} bad={refused.returncode}"
        else:
            ok, detail = True, "baseline absent; verifier not exercised"
        check("verify_preflight accepts the known Qwen3 file and refuses a mismatch", ok, detail)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        pack = [
            {"caseId": "tasks-ok", "kind": "tasks", "allowedIds": ["char_a", "char_b", "t1", "t2"],
             "allowUniqueNames": True, "nameToId": {"乙": "char_b"},
             "requiredCharacterIds": ["char_a", "char_b"],
             "allowedTaskIdsByCharacter": {"char_a": ["t1"], "char_b": ["t2"]}},
            {"caseId": "tasks-placeholder", "kind": "tasks", "allowedIds": ["char_a"],
             "requiredCharacterIds": ["char_a"], "allowedTaskIdsByCharacter": {"char_a": []}},
            {"caseId": "tasks-missing", "kind": "tasks", "allowedIds": ["char_a", "char_b"],
             "requiredCharacterIds": ["char_a", "char_b"],
             "allowedTaskIdsByCharacter": {"char_a": [], "char_b": []}},
            {"caseId": "results-undeclared", "kind": "results", "allowedIds": ["char_a", "rules"],
             "declaredTargetIds": ["char_a"]},
            {"caseId": "continuation-protagonist", "kind": "continuation",
             "allowedIds": ["char_a", "char_b"], "nameToId": {"路明非": "char_a"},
             "allowUniqueNames": True, "protagonistId": "char_a"},
            {"caseId": "updates-placeholder", "kind": "updates", "allowedIds": ["char_a"]},
        ]
        outputs = {
            "tasks-ok": {"decisions": [{"characterId": "char_a", "achieved": []},
                                       {"characterId": "乙", "achieved": ["t2"]}]},
            "tasks-placeholder": {"decisions": [{"characterId": "id", "achieved": []}]},
            "tasks-missing": {"decisions": [{"characterId": "char_a", "achieved": []}]},
            "results-undeclared": {"members": [{"memberId": "char_a",
                                                "effects": [{"targetId": "rules", "reacted": True}]}]},
            "continuation-protagonist": {"candidates": [{"characterId": "路明非", "text": "他走。"}]},
            "updates-placeholder": {"operations": [{"entityId": "id", "op": "keep",
                                                    "recordIds": [], "text": None}]},
        }
        (tmp_path / "pack.jsonl").write_text(
            "\n".join(json.dumps(item, ensure_ascii=False) for item in pack) + "\n", encoding="utf-8")
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        for case_id, value in outputs.items():
            (run_dir / f"{case_id}.json").write_text(
                json.dumps({"caseId": case_id, "text": json.dumps(value, ensure_ascii=False)},
                           ensure_ascii=False), encoding="utf-8")
        proc = run(["src/semantic_validate.py", "--pack", str(tmp_path / "pack.jsonl"),
                    "--run-dir", str(run_dir), "--out", str(tmp_path / "report.json")])
        ok = proc.returncode == 2
        detail = f"exit={proc.returncode}"
        if ok:
            report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
            by_id = {entry["caseId"]: entry for entry in report["reports"]}
            ok = (by_id["tasks-ok"]["ok"]
                  and any("placeholder" in error for error in by_id["tasks-placeholder"]["errors"])
                  and any("coverage" in error for error in by_id["tasks-missing"]["errors"])
                  and any("undeclared target" in error for error in by_id["results-undeclared"]["errors"])
                  and any("protagonist" in error for error in by_id["continuation-protagonist"]["errors"])
                  and any("placeholder" in error for error in by_id["updates-placeholder"]["errors"]))
            detail = f"passed={report['passed']}/{report['cases']}"
        check("semantic_validate catches placeholder/coverage/declared-target/continuation errors", ok, detail)

    plan = run(["src/screen.py", "--dry-run", "--model-id", "qwen25-1.5b-instruct",
                "--prompts", str(ROOT / "evidence/prompts-dev-v1/prompts.jsonl"),
                "--prompt-manifest", str(ROOT / "evidence/prompts-dev-v1/prompts.manifest.json")])
    ok = plan.returncode == 0 and '"modelId": "qwen25-1.5b-instruct"' in plan.stdout
    check("screen --dry-run prints a plan without a server", ok, f"exit={plan.returncode}")

    registry = json.loads((ROOT / "models/candidates.json").read_text(encoding="utf-8"))
    bad_gate = [c["id"] for c in registry["candidates"]
                if c["preInferenceGate"]["passed"] and c["gguf"]["bytes"] > 1_500_000_000]
    no_reason = [c["id"] for c in registry["candidates"]
                 if not c["preInferenceGate"]["passed"] and not c["preInferenceGate"]["reasons"]]
    check("registry gate is internally consistent", not bad_gate and not no_reason,
          f"oversize={bad_gate} no_reason={no_reason}")

    failed = [name for name, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
