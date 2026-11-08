"""Write the machine-readable N2 integration handoff.

The content mirrors HANDOFF-n2-integration.md; the evidence block carries the
sha256 and (when available) the recorded commit of every frozen artifact, so
the integration side can bind its own run to exact inputs.

Output: freeze/integration-handoff-v1.json
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
FREEZE = HERE / "freeze"
ROOT = HERE.parents[3]

EVIDENCE = [
    "runs/r1/raw-output.json",
    "runs/r1/score.json",
    "runs/contract-v1/validation.json",
    "runs/v2-acceptance/parse.json",
    "runs/v2-acceptance/score.json",
    "runs/wiring-v1/parse.json",
    "runs/wiring-v1/selection.json",
    "runs/wiring-v1/score.json",
    "freeze/contract-v1.md",
    "freeze/acceptance-v1.json",
    "freeze/anchors-v1.json",
    "freeze/facts-v1.json",
    "freeze/wiring-v1.json",
    "freeze/v2-extra-probes.json",
]


def sha256(path: pathlib.Path) -> str:
    """Working-copy bytes (can differ by checkout line endings)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_blob(rel: str) -> str | None:
    """Bytes as stored in HEAD: stable across checkouts and autocrlf settings."""
    try:
        blob = subprocess.run(
            ["git", "-c", f"safe.directory={ROOT.as_posix()}", "show", f"HEAD:{rel}"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
    except Exception:  # pragma: no cover - not committed yet
        return None
    return hashlib.sha256(blob).hexdigest()


def git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", "-c", f"safe.directory={ROOT.as_posix()}", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except Exception as exc:  # pragma: no cover
        return f"<git error: {exc}>"


def main() -> int:
    document = {
        "protocol": "c1-n2-integration-handoff-v1",
        "createdOn": "2026-11-08",
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "c1Head": git("rev-parse", "HEAD"),
        "status": "有实验结果，独立过滤器接线已验证；正式 N2 未接入；真实玩家表达覆盖无法判断",
        "doesNotChange": ["runs/r1/", "freeze/contract-v1.md", "freeze/acceptance-v1.json", "freeze/anchors-v1.json"],
        "targetShape": {
            "fields": ["entityId", "scope", "part?", "partAnchored?", "surface", "scopeCue"],
            "scopes": ["object", "position", "appearance", "task", "part"],
            "states": ["resolved", "ambiguous", "unresolved", "none"],
            "emptyTargetsForStates": ["ambiguous", "unresolved", "none"],
        },
        "mapping": {
            "pipeline": "classify_facts(may_policy='select') -> keep all must -> keep may only if a target matches -> never resurrect invisible",
            "mayPolicyNote": "attention and may_policy are alternative selectors for may facts; with may_policy='omit' the targets are never consumed",
            "scopeKinds": {
                "object": ["<all kinds of that entity>"],
                "position": ["moved", "positioned_at", "position_relative", "slot_changed"],
                "appearance": ["appearance_changed", "appearance_removed"],
                "task": ["task_achieved", "subtask_added"],
                "part": ["appearance_changed", "appearance_removed"],
            },
            "partRule": "fact.text contains target.part literally; partAnchored=false changes nothing here",
            "invariants": [
                "must facts are kept regardless of attention",
                "empty targets select no may fact (equivalent to may_policy='omit')",
                "invisible / refusals / stops semantics unchanged",
                "one fact selected at most once; order follows classify_facts",
            ],
        },
        "openDecisions": [
            {
                "id": "OD-1",
                "issue": "no personality scope; '什么性子' currently widens to object",
                "blocks": "R-attention-v1 G1-A/G1-B",
                "owner": "N2 integration",
            },
            {
                "id": "OD-2",
                "issue": "product may_policy is 'omit' today; attention targets are only consumed under 'select'",
                "blocks": "any attention-driven narration",
                "owner": "N2 integration / product",
            },
            {
                "id": "OD-3",
                "issue": "old six-condition attentionTargets are words, not scoped targets; do not reuse as new labels",
                "blocks": "reusing attention-selection-v1.json as integration truth",
                "owner": "N2 integration",
            },
        ],
        "knownFailures": [
            {
                "id": "KF-1",
                "input": "看看他手背",
                "behaviour": "falls back to object (whole entity)",
                "evidence": "freeze/v2-extra-probes.json#X2 covers only the 的<X> shape",
                "mustHandleBeforeIntegration": True,
            },
            {
                "id": "KF-2",
                "input": "局部词不在 part 词表",
                "behaviour": "with 的 -> unresolved (empty targets); without 的 -> KF-1",
                "evidence": "freeze/contract-v1.md §8",
                "mustHandleBeforeIntegration": True,
            },
            {
                "id": "KF-3",
                "input": "整人 + 局部同一句",
                "behaviour": "only one scope per entity; second request ignored",
                "evidence": "freeze/contract-v1.md §8",
                "mustHandleBeforeIntegration": False,
            },
            {
                "id": "KF-4",
                "input": "两个完全同名实体",
                "behaviour": "covered only by a synthetic roster",
                "evidence": "freeze/rule-cases.json#U1",
                "mustHandleBeforeIntegration": False,
            },
        ],
        "integrationFreezeRequirements": {
            "perSample": ["before/after/delta or fact bundle source", "perspective", "subject_tasks", "may_policy", "utterance", "expectedSelectedFactIds"],
            "gates": [
                "all must facts kept",
                "no may fact outside the attention scope selected",
                "empty targets select zero may facts",
                "zero invisible/forbidden selections; stops behaviour unchanged",
            ],
            "reporting": ["parse error (c1)", "classification error (classify_facts)", "filter decision error (scope filter)"],
            "batchSizeMax": 10,
            "labelsFrozenBeforeImplementation": True,
        },
        "evidenceHashing": {
            "sha256Blob": "sha256 of git show HEAD:<path>; identical in every worktree",
            "sha256WorkingCopy": "sha256 of the file on disk in the generating worktree; may differ by CRLF/LF checkout",
        },
        "evidence": [
            {
                "path": rel,
                "sha256Blob": sha256_blob(f"{HERE.relative_to(ROOT).as_posix()}/{rel}"),
                "sha256WorkingCopy": sha256(HERE / rel),
                "recordedCommit": json.loads((HERE / rel).read_text(encoding="utf-8")).get("hashes", {}).get("commit")
                if rel.endswith(".json")
                else None,
            }
            for rel in EVIDENCE
        ],
    }
    target = FREEZE / "integration-handoff-v1.json"
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {target.relative_to(ROOT)}")
    for item in document["evidence"]:
        print(
            f"  {item['path']:<40} blob={str(item['sha256Blob'])[:16]} "
            f"work={item['sha256WorkingCopy'][:16]} commit={str(item['recordedCommit'])[:12]}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
