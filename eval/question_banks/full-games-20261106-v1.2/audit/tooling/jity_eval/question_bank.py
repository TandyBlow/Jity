"""Curated capture question banks: freeze, separate channels, and validate offline.

This module has no model adapter and never imports the game runtime. Captured
outputs are historical witnesses, never probe answers. It reuses the existing
JSON hashing/writing primitives and the replay structured-state allowlist.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
import shutil

from .storage import atomic_json, digest, digest_bytes, now
from .replay.context import STRUCTURED_KEYS

SCHEMA = "jity.capture-question-bank.v1"
MODES = ("full", "recent", "state")
INSTRUCTION = "仅依据所提供的检查点记录回答问题；区分观察、角色说法与推断。信息不足时说明无法确定。只判断和解释，不执行游戏行动。"
PUBLIC_KEYS = {"id", "game_id", "data_version", "checkpoint", "question", "kind"}


def read(path):
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                raise ValueError("duplicate JSON key: " + k)
            result[k] = v
        return result
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pointer(value, path):
    require(path == "" or path.startswith("/"), "Invalid JSON pointer")
    for bit in path.split("/")[1:]:
        bit = bit.replace("~1", "/").replace("~0", "~")
        value = value[int(bit)] if isinstance(value, list) else value[bit]
    return value


def leaves(value, path=""):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, val in value.items():
            yield from leaves(val, path + "/" + str(key).replace("~", "~0").replace("/", "~1"))
    elif isinstance(value, list):
        for i, val in enumerate(value):
            yield from leaves(val, path + "/" + str(i))


def safe_path(root, relative):
    p = (Path(root) / relative).resolve()
    require(p.is_relative_to(Path(root).resolve()), "Path escapes bank: " + str(relative))
    return p


def source_name(game, action, kind="checkpoints"):
    return f"{game}/initial.json" if action == 0 else f"{game}/{kind}/turn-{action:04d}.json"


def checkpoint(root, game, action):
    return read(Path(root) / source_name(game, action))


def checkpoint_identity(cp):
    return {"action_index": cp["turn"], "campaign_turn": cp["progress"]["turns_total"],
            "state_turn": cp["state"]["turn"], "timeline_node": cp["head"],
            "state_sha256": digest(cp["state"]), "checkpoint_sha256": digest(cp)}


def recent_rows(root, game, action, window):
    rows = []
    for t in range(max(1, action - window + 1), action + 1):
        cp = checkpoint(root, game, t)
        intent = read(Path(root) / source_name(game, t, "intents"))
        rows.append({"action_index": t, "timeline_node": cp["head"],
                     "player_action": intent["request"]["player_action"], "output": cp["output"]})
    return rows


def channels(cp):
    state = cp["state"]
    memory = state.get("_memory_controller", {})
    structured = {k: deepcopy(state[k]) for k in STRUCTURED_KEYS if k in state}
    structured["item_ledger"] = deepcopy(memory.get("score_tracker", []))
    # Preserve recorded content, including any stale/contradictory summaries.
    # No gold-based retrieval, ideal-memory reconstruction, or repairs.
    nsb = memory.get("nsb", {})
    narrative = {"nsb": {k: deepcopy(nsb.get(k, [])) for k in ("level1", "level2", "level3", "turn_buffer")},
                 "pcb": deepcopy(memory.get("pcb", {}).get("sketches", {})),
                 "recap_compressed": cp["progress"].get("recap_compressed", ""),
                 "recent_events": deepcopy(state.get("recent_events", []))}
    return structured, narrative


def make_input(root, public, mode, window):
    cp = checkpoint(root, public["game_id"], public["checkpoint"]["action_index"])
    state, memory = channels(cp)
    content = {"recent_context": recent_rows(root, public["game_id"], cp["turn"], window)}
    if mode in ("full", "state"):
        content["structured_state"] = state
    if mode == "full":
        content["historical_narrative_memory"] = memory
    return {"schema_version": SCHEMA, "question_id": public["id"], "game_id": public["game_id"],
            "data_version": public["data_version"], "checkpoint": public["checkpoint"],
            "mode": mode, "recent_window": window, "instruction": INSTRUCTION,
            "question": public["question"], "context": content}


def public_mentions(root, game, stop, terms):
    found = []
    for t in range(stop + 1):
        cp = checkpoint(root, game, t)
        corpus = {"output": cp.get("output", {})}
        if t:
            corpus["player_action"] = read(Path(root) / source_name(game, t, "intents"))["request"]["player_action"]
        for path, text in leaves(corpus):
            matches = [term for term in terms if term in text]
            if matches:
                found.append({"action_index": t, "timeline_node": cp["head"], "json_pointer": path,
                              "terms": matches, "excerpt": text})
    return found


def channel_hits(value, terms):
    return [{"json_pointer": p, "terms": [x for x in terms if x in s], "excerpt": s}
            for p, s in leaves(value) if any(x in s for x in terms)]


def verify_source(source):
    seal = read(source / "seal.json")
    require(digest_bytes((source / "seal.json").read_bytes()) == (source / "seal.sha256").read_text().split()[0], "Seal digest mismatch")
    for name, sha in seal["files"].items():
        require(digest_bytes(safe_path(source, name).read_bytes()) == sha, "Source seal changed: " + name)
    return seal


def build(source, spec_path, output, dataset_audit):
    source, output = Path(source).resolve(), Path(output).resolve()
    require(not output.exists(), "Output already exists; choose a new version")
    require(not output.is_relative_to(source), "Never write into recordings")
    seal = verify_source(source)
    spec = read(spec_path)
    require(spec["schema_version"] == SCHEMA, "Wrong authoring schema")
    require(type(spec["recent_window"]) is int and spec["recent_window"] > 0, "Invalid window")
    require(isinstance(spec["questions"], list) and spec["questions"], "Empty question bank")
    ids = []
    for row in spec["questions"]:
        require(isinstance(row.get("id"), str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", row["id"]), "Invalid question ID")
        require(isinstance(row.get("game_id"), str) and re.fullmatch(r"game-0[1-4]", row["game_id"]), "Invalid game")
        require(type(row.get("checkpoint_action")) is int and row["checkpoint_action"] > 0, "Invalid checkpoint")
        require(row.get("kind") in ("recall", "action", "unknown"), "Invalid question kind")
        require(isinstance(row.get("question"), str) and row["question"].strip(), "Empty question")
        ids.append(row["id"])
    require(len(ids) == len(set(ids)), "Duplicate question ID")
    for row in spec.get("candidates", []):
        if "checkpoint_action" in row:
            require(type(row["checkpoint_action"]) is int and row["checkpoint_action"] >= 0, "Invalid candidate checkpoint")
        if "game_id" in row:
            require(isinstance(row["game_id"], str) and re.fullmatch(r"game-0[1-4]", row["game_id"]), "Invalid candidate game")
    version = "full-games-20261106.seal-" + digest_bytes((source / "seal.json").read_bytes())[:16]
    output.mkdir(parents=True)
    frozen = output / "frozen" / "source"
    copied = {}

    def freeze(name):
        original = safe_path(source, name)
        target = safe_path(frozen, name)
        raw = original.read_bytes()
        sha = digest_bytes(raw)
        if name in seal["files"]:
            require(sha == seal["files"][name], "Changed while freezing: " + name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        copied[name] = sha

    all_specs = spec["questions"] + spec.get("candidates", [])
    limits = {}
    for row in all_specs:
        if "game_id" in row and "checkpoint_action" in row:
            limits[row["game_id"]] = max(limits.get(row["game_id"], 0), row["checkpoint_action"])
    for game, stop in limits.items():
        require(re.fullmatch(r"game-0[1-4]", game), "Invalid game")
        freeze(source_name(game, 0))
        for t in range(1, stop + 1):
            freeze(source_name(game, t))
            freeze(source_name(game, t, "intents"))
    for name in ("manifest.json", "seal.json", "seal.sha256", "DATASET.md", "validation/final-acceptance.json"):
        freeze(name)
    # Freeze independent acceptance evidence as provenance, outside model inputs.
    dataset = read(dataset_audit)
    # Terminal/replay evidence is private provenance; it never enters an input.
    for game in dataset.get("games", []):
        for key in ("strict_replay_path", "final_checkpoint_path"):
            if game.get(key):
                freeze(game[key])
    atomic_json(output / "audit/dataset.json", dataset)
    atomic_json(output / "private/authoring.json", spec)
    records, gold, audits, evidences = [], [], [], []
    for row in spec["questions"]:
        game, t, qid = row["game_id"], row["checkpoint_action"], row["id"]
        cp = checkpoint(frozen, game, t)
        public = {"id": qid, "game_id": game, "data_version": version,
                  "checkpoint": checkpoint_identity(cp), "question": row["question"],
                  "kind": "recall" if row["kind"] == "unknown" else row["kind"]}
        records.append(public)
        gold.append({"id": qid, **row["gold"]})
        eids = []
        for i, e in enumerate(row["evidence"], 1):
            e = deepcopy(e)
            action = e.pop("action_index")
            path = source_name(game, action)
            original = pointer(checkpoint(frozen, game, action), e["json_pointer"])
            if e.get("projection") == "names":
                shown = [x.get("name") for x in original]
            else:
                shown = original
            excerpt = e.get("excerpt", shown)
            require((isinstance(shown, str) and isinstance(excerpt, str) and excerpt in shown) or excerpt == shown,
                    "Evidence excerpt not found: " + qid + str(i))
            eid = qid + f".e{i:02d}"
            eids.append(eid)
            evidences.append({"id": eid, "game_id": game, "action_index": action,
                              "timeline_node": checkpoint(frozen, game, action)["head"],
                              "source_path": str(source / path), "frozen_path": "frozen/source/" + path,
                              "file_sha256": copied[path], "value_sha256": digest(original),
                              **e, "excerpt": excerpt})
        mentions = public_mentions(frozen, game, t, row["mention_terms"])
        # Additional semantic rementions require exact original quotations.
        for e in row.get("semantic_mentions", []):
            value = pointer(checkpoint(frozen, game, e["action_index"]), e["json_pointer"])
            require(e["excerpt"] in value, "Invalid semantic mention")
            require(e["action_index"] <= t, "Future semantic mention")
            mentions.append({**e, "timeline_node": checkpoint(frozen, game, e["action_index"])["head"], "method": "editor_semantic"})
        last = max([m["action_index"] for m in mentions] + [row["first_action"]])
        first = checkpoint(frozen, game, row["first_action"])
        latest = checkpoint(frozen, game, last)
        structured, narrative = channels(cp)
        audit = {"id": qid, "category": row["category"], "test_target": row["test_target"],
                 "chronology": {"first_action": row["first_action"], "update_actions": row.get("update_actions", []),
                                "last_public_topic_mention_action": last, "mention_terms": row["mention_terms"],
                                "public_mentions": mentions, "author_notes": row.get("chronology_notes", "")},
                 "interval": {"primary_unit": "submitted_action", "definition": "checkpoint.action_index - last_public_topic_mention_action; 含选项/检定条件/提交后输出全部字符串及实际玩家行动，保守话题扫描，不将持续状态算作新事件",
                              "since_first_actions": t - row["first_action"], "since_last_public_mention_actions": t - last,
                              "since_first_campaign_turns": cp["progress"]["turns_total"] - first["progress"]["turns_total"],
                              "since_last_campaign_turns": cp["progress"]["turns_total"] - latest["progress"]["turns_total"],
                              "ancestor_edges_since_last": t - last,
                              "interpretation": "未知题仅衡量话题间隔，不代表已知答案被遗忘；语义重提待人工复核。"},
                 "channels": {**row["channels"], "recent_window": spec["recent_window"],
                              "recent_action_range": [max(1, t - spec["recent_window"] + 1), t],
                              "structured_snapshot_topic_hits": channel_hits(structured, row["mention_terms"]),
                              "narrative_memory_snapshot_topic_hits": channel_hits(narrative, row["mention_terms"]),
                              "snapshot_note": "持久状态/摘要在当前检查点仍可见不等于最近剧情重提；原始近期 output 可能合法包含 memory_updates。题目相关字面命中不自动等于答案齐全。"},
                 "evidence_ids": eids, "validity": row["validity"], "review": row["review"],
                 "unknown_audit": row.get("unknown_audit")}
        audits.append(audit)
        for mode in MODES:
            atomic_json(output / f"public/inputs/{qid}/{mode}.json", make_input(frozen, public, mode, spec["recent_window"]))
    for name, rows in (("public/questions.json", records), ("private/answers.json", gold),
                       ("audit/items.json", audits), ("audit/evidence.json", evidences)):
        atomic_json(output / name, {"schema_version": SCHEMA, "bank_id": spec["bank_id"], "records": rows})
    atomic_json(output / "private/candidates.json", {"schema_version": SCHEMA, "records": spec.get("candidates", [])})
    atomic_json(output / "coverage.json", spec["coverage"])
    inventory = {str(p.relative_to(output)): digest_bytes(p.read_bytes()) for p in output.rglob("*.json")}
    inventory.update({"frozen/source/seal.sha256": digest_bytes((frozen / "seal.sha256").read_bytes()),
                      "frozen/source/DATASET.md": digest_bytes((frozen / "DATASET.md").read_bytes())})
    manifest = {"schema_version": SCHEMA, "bank_id": spec["bank_id"], "bank_version": spec["bank_version"],
                "created_at": now(), "status": "pending_human_review", "data_version": version,
                "source_root": str(source), "source_seal_sha256": digest_bytes((source / "seal.json").read_bytes()),
                "source_manifest_sha256": digest_bytes((source / "manifest.json").read_bytes()),
                "source_seal_files_verified": len(seal["files"]), "frozen_source_files": copied,
                "recent_window": spec["recent_window"], "modes": list(MODES), "prefix_limits": limits,
                "hash_convention": "file: SHA256(raw bytes); value/state: jity_eval.storage.digest (UTF-8 ensure_ascii=False, sort_keys=True, indent=2)",
                "files": inventory, "paid_api_calls": 0, "model_answers_generated": 0, "game_actions_executed": 0,
                "context_policy": "capture_snapshot_v1; same committed recent outputs, actual recorded NSB/PCB/recap/recent_events for full, STRUCTURED_KEYS + item ledger for full/state; no retrieval, trimming, or synthetic gold memories",
                "limitations": ["不是现有 production PromptBuilder 的最终提示词；后续适配器应使用此冻结通道合同并另存最终输入。",
                                "自动检查证明引用/版本/边界一致，不证明语义答案正确或无隐含线索。",
                                "只读取封存重放验收证据，本次没有重新执行严格重放。"]}
    atomic_json(output / "manifest.json", manifest)
    (output / "manifest.sha256").write_text(digest_bytes((output / "manifest.json").read_bytes()) + "\n")
    result = validate(output, source_check=True)
    atomic_json(output / "validation.json", result)
    return output


def validate(output, source_check=False):
    output = Path(output).resolve()
    m = read(output / "manifest.json")
    require(digest_bytes((output / "manifest.json").read_bytes()) == (output / "manifest.sha256").read_text().strip(), "Manifest fingerprint changed")
    require(m["schema_version"] == SCHEMA and m["status"] == "pending_human_review", "Wrong schema/status")
    for name, sha in m["files"].items():
        require(digest_bytes(safe_path(output, name).read_bytes()) == sha, "Frozen file changed: " + name)
    frozen = output / "frozen/source"
    for name, sha in m["frozen_source_files"].items():
        require(digest_bytes(safe_path(frozen, name).read_bytes()) == sha, "Source copy changed")
        if source_check:
            require(digest_bytes(safe_path(m["source_root"], name).read_bytes()) == sha, "Original changed: " + name)
    if source_check:
        verify_source(Path(m["source_root"]))
    collections = {name: read(output / path)["records"] for name, path in
                   (("questions", "public/questions.json"), ("answers", "private/answers.json"),
                    ("items", "audit/items.json"), ("evidence", "audit/evidence.json"))}
    for name, rows in collections.items():
        require(len({r["id"] for r in rows}) == len(rows), "Duplicate ID: " + name)
    questions, answers, audits, evidence = ({r["id"]: r for r in collections[name]} for name in collections)
    authored_rows = read(output / "private/authoring.json")["questions"]
    authored = {r["id"]: r for r in authored_rows}
    require(len(authored) == len(authored_rows) and authored.keys() == questions.keys(), "Authoring/question identity mismatch")
    require(questions and questions.keys() == answers.keys() == audits.keys(), "Question/answer/audit identity mismatch")
    for game, stop in m["prefix_limits"].items():
        cp0 = checkpoint(frozen, game, 0)
        prev = cp0
        seen = {prev["head"]}
        for t in range(1, stop + 1):
            cp = checkpoint(frozen, game, t)
            intent = read(frozen / source_name(game, t, "intents"))
            require(cp["turn"] == t and intent["turn"] == t, "Action index mismatch")
            require(intent["request"]["timeline_node_id"] == prev["head"], "Broken ancestor chain")
            require(cp["head"] not in seen, "Repeated timeline node")
            require(cp["progress"]["turns_total"] - prev["progress"]["turns_total"] in (0, 1), "Invalid campaign counter")
            seen.add(cp["head"])
            prev = cp
    all_eids = []
    for qid, q in questions.items():
        require(set(q) == PUBLIC_KEYS and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", qid), "Unexpected public question field or ID")
        t, game = q["checkpoint"]["action_index"], q["game_id"]
        require(q["data_version"] == m["data_version"], "Data version mismatch")
        authored_q = authored[qid]
        expected_kind = "recall" if authored_q["kind"] == "unknown" else authored_q["kind"]
        require(q["question"] == authored_q["question"] and q["kind"] == expected_kind
                and game == authored_q["game_id"] and t == authored_q["checkpoint_action"], "Public question differs from frozen authoring")
        require(answers[qid] == {"id": qid, **authored_q["gold"]}, "Gold differs from frozen authoring")
        require(q["checkpoint"] == checkpoint_identity(checkpoint(frozen, game, t)), "Checkpoint identity mismatch")
        a = audits[qid]
        require(a["review"]["status"] == "pending_human_review", "Unreviewed item mislabeled")
        require(a["chronology"]["first_action"] == authored_q["first_action"]
                and a["chronology"]["update_actions"] == authored_q.get("update_actions", [])
                and a["chronology"]["mention_terms"] == authored_q["mention_terms"], "Chronology differs from authoring")
        require(0 <= a["chronology"]["first_action"] <= t and all(0 <= x <= t for x in a["chronology"]["update_actions"]), "Future chronology")
        raw_mentions = public_mentions(frozen, game, t, a["chronology"]["mention_terms"])
        recorded = a["chronology"]["public_mentions"]
        expected_mentions = list(raw_mentions)
        for mention in authored_q.get("semantic_mentions", []):
            mt = mention["action_index"]
            require(type(mt) is int and 0 <= mt <= t, "Future semantic mention")
            source_cp = checkpoint(frozen, game, mt)
            actual = pointer(source_cp, mention["json_pointer"])
            require(isinstance(actual, str) and mention["excerpt"] in actual, "Invalid semantic mention quote")
            expected_mentions.append({**mention, "timeline_node": source_cp["head"], "method": "editor_semantic"})
        require(recorded == expected_mentions, "Unverified or missed public remention")
        last = max([x["action_index"] for x in recorded] + [a["chronology"]["first_action"]])
        require(last <= t and a["chronology"]["last_public_topic_mention_action"] == last, "Invalid last mention")
        require(a["interval"]["since_last_public_mention_actions"] == t - last, "Invalid delay")
        first_cp = checkpoint(frozen, game, authored_q["first_action"])
        last_cp = checkpoint(frozen, game, last)
        require(a["interval"]["since_first_actions"] == t - authored_q["first_action"]
                and a["interval"]["since_first_campaign_turns"] == q["checkpoint"]["campaign_turn"] - first_cp["progress"]["turns_total"]
                and a["interval"]["since_last_campaign_turns"] == q["checkpoint"]["campaign_turn"] - last_cp["progress"]["turns_total"]
                and a["interval"]["ancestor_edges_since_last"] == t - last, "Invalid interval counters")
        require(bool(a["evidence_ids"]), "Question lacks evidence")
        for eid in a["evidence_ids"]:
            e = evidence[eid]
            all_eids.append(eid)
            require(e["game_id"] == game and 0 <= e["action_index"] <= t, "Future/cross-game evidence")
            require(e["frozen_path"] == "frozen/source/" + source_name(game, e["action_index"]), "Evidence path/index mismatch")
            path = safe_path(output, e["frozen_path"])
            value = pointer(read(path), e["json_pointer"])
            require(digest(value) == e["value_sha256"] and digest_bytes(path.read_bytes()) == e["file_sha256"], "Evidence fingerprint mismatch")
            require(e["timeline_node"] == checkpoint(frozen, game, e["action_index"])["head"], "Evidence node mismatch")
            shown = [x.get("name") for x in value] if e.get("projection") == "names" else value
            excerpt = e["excerpt"]
            require((isinstance(shown, str) and isinstance(excerpt, str) and excerpt in shown) or shown == excerpt, "Unsupported evidence excerpt")
        for mode in MODES:
            supplied = read(output / f"public/inputs/{qid}/{mode}.json")
            expected = make_input(frozen, q, mode, m["recent_window"])
            require(supplied == expected, "Model input differs from source-only reconstruction: " + qid + "/" + mode)
        require(authored_q["kind"] != "unknown" or bool(a["unknown_audit"]), "Unknown question needs bounded review")
        require(a["unknown_audit"] == authored_q.get("unknown_audit"), "Unknown audit differs from authoring")
        if a["unknown_audit"]:
            u = a["unknown_audit"]
            require(u["range"] == [0, t] and u["status"] == "editor_reviewed_pending_human", "Unknown audit range/status")
            require(u.get("reviewed_fields") and u.get("inference_review") and u.get("search_terms"), "Incomplete unknown audit")
    require(set(all_eids) == evidence.keys(), "Orphan evidence")
    expected_inputs = {f"public/inputs/{qid}/{mode}.json" for qid in questions for mode in MODES}
    actual_public = {str(p.relative_to(output)) for p in (output / "public").rglob("*") if p.is_file()}
    require(actual_public == expected_inputs | {"public/questions.json"}, "Unexpected public file: possible answer leak")
    return {"schema_version": SCHEMA, "status": "passed", "checked_at": now(),
            "questions": len(questions), "games": len({q["game_id"] for q in questions.values()}),
            "frozen_inputs": len(expected_inputs), "evidence_references": len(evidence),
            "checks": {k: True for k in ("unique_ids", "checkpoint_ancestor_chain", "checkpoint_fingerprints", "evidence_exists",
                         "no_future_evidence", "source_only_model_inputs", "private_gold_separation", "same_questions_and_checkpoints_in_three_groups",
                         "frozen_input_fingerprints", "last_literal_rementions", "unknown_bounded_review")},
            "original_source_checked": source_check, "paid_api_calls": 0, "model_answers": 0,
            "semantic_review": "pending_human_review", "scores": None,
            "limitations": ["问句泄题、隐含推导、别名和语义重提仍需人工审核；不以字面扫描代替语义审计。",
                            "原始历史里出现答案是合法上下文，不等于私有标准答案泄漏；验证从源重建而非禁止答案字串。"]}


def main(argv=None):
    p = argparse.ArgumentParser(description="离线录制题库；不会调用模型或执行游戏")
    sub = p.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--source", type=Path, required=True)
    b.add_argument("--spec", type=Path, required=True)
    b.add_argument("--output", type=Path, required=True)
    b.add_argument("--dataset-audit", type=Path, required=True)
    v = sub.add_parser("validate")
    v.add_argument("bank", type=Path)
    v.add_argument("--check-original", action="store_true")
    r = sub.add_parser("report")
    r.add_argument("bank", type=Path)
    args = p.parse_args(argv)
    try:
        if args.command == "build":
            print(build(args.source, args.spec, args.output, args.dataset_audit))
        elif args.command == "validate":
            print(json.dumps(validate(args.bank, args.check_original), ensure_ascii=False, indent=2))
        else:
            validate(args.bank)
            from .question_bank_report import render_report
            print(render_report(args.bank))
        return 0
    except (ValueError, OSError, KeyError, IndexError, TypeError) as exc:
        print("题库校验失败：" + str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
