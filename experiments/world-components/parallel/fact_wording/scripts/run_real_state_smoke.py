"""Real committed-state N3 -> N4 (u240) smoke run. Read-only.

What it does, in order:
  1. read one committed point (and its explicit predecessor) from a world DB,
     validating world identity, version continuity, predecessor identity and
     state digest -- per design/.../n3-n4-interface-plan.md;
  2. run the program chain N1 -> N2 -> N3 (narration_pipeline.run_pipeline_v2)
     with no tokenizer gate, keeping the plan, selected facts and sources;
  3. decide per fact whether the frozen u240 input contract can carry it;
  4. for supported facts, render the frozen single-fact input from STATE ONLY
     (place, items at that place, time-of-day, viewpoint) and call u240 greedily,
     timing encoder and decoder separately.

It never writes state, never trains, and never fills gaps with invented text:
unsupported facts are recorded as unsupported and skipped.

Applicability (fixed before looking at any output):
  moved            supported   (subject + from + to are state names)
  task_achieved    unsupported (N1 carries goal+status; u240 takes a result sentence)
  sanity_changed   unsupported (u240 input may not carry numbers; N1 has no descriptor)
  appearance_changed supported (N1 carries the changed text; none selected in this world)
  anything else    unsupported

Usage (from the experiment dir):
  JITY_REPO=<repo> env/Scripts/python.exe scripts/run_real_state_smoke.py \
      --db <repo>/.local/b3-debug-action-db/world.db --point point_7 \
      --db <repo>/.local/world-chain-full-1793200688255/world.db --point point_19
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
import platform
from pathlib import Path

HERE = Path(__file__).resolve()
EXP = HERE.parents[1]
TREE = EXP.parents[3]
WC = TREE / "experiments/world-components"
sys.path.insert(0, str(WC))

import narration_pipeline as np  # noqa: E402

TEMPLATE = (
    "短句任务。\n"
    "地点={place}\n"
    "地点可见={visible}\n"
    "场景={scene}\n"
    "视角={viewer}；第三人称\n"
    "事实={fact_line}\n"
    "要求：写一句话，把事实写成场景里可见的动作或状态；句中出现事实主体的名字；"
    "只用地点可见里的物件与场景给的现象；需要表示高低时用方向给的字；"
    "不写任务标题、数值、具体时长、字段名；不新增人物、物品、地点。\n"
    "短句：\n"
)

HOURS = [(5, "清晨"), (11, "上午"), (13, "午后"), (18, "傍晚"), (22, "夜")]


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def time_of_day(iso: str) -> str:
    hh = int(iso[11:13])
    for limit, label in HOURS:
        if hh < limit:
            return label
    return "夜"


def load_point(conn, pid: str) -> dict:
    row = conn.execute(
        "select id, sequence, previous_point_id, time_json, delta_json, state_digest "
        "from world_points where id=?", (pid,)).fetchone()
    if row is None:
        raise SystemExit(f"point not found: {pid}")
    st = conn.execute("select state_json from world_state_checkpoints where point_id=?",
                      (pid,)).fetchone()
    if st is None:
        raise SystemExit(f"no state checkpoint for {pid}")
    return dict(pointId=row[0], version=row[1], previousPointId=row[2],
                timeAdvance=json.loads(row[3]) if row[3] else None,
                entityDeltas=json.loads(row[4]) if row[4] else {},
                stateDigest=row[5], state=json.loads(st[0]))


def validate(point: dict, before: dict) -> list[str]:
    problems = []
    if not point["state"].get("worldId"):
        problems.append("world-missing")
    if point["previousPointId"] != before["pointId"]:
        problems.append("predecessor-identity-mismatch")
    if point["version"] != before["version"] + 1:
        problems.append("version-gap")
    if not point["stateDigest"]:
        problems.append("missing-stateDigest")
    if point["state"].get("worldId") != before["state"].get("worldId"):
        problems.append("world-mismatch")
    return problems


def applicable(fact: dict) -> tuple[bool, str]:
    kind = fact["kind"]
    if kind == "moved":
        return True, ""
    if kind == "task_achieved":
        return False, ("u240 takes a result sentence; N1 task facts carry goal+status "
                       "and no resultText, so a faithful fact line cannot be rendered")
    if kind == "sanity_changed":
        return False, ("u240 input may not carry numbers and N1 sanity facts have no "
                       "descriptor, so only the numbers exist")
    if kind == "appearance_changed":
        return True, ""
    return False, f"kind not in the u240 fact contract: {kind}"


def scene_fields(state: dict, fact: dict) -> dict:
    initial = state.get("initial") or {}
    locs = initial.get("locations") or {}
    items = initial.get("items") or {}
    dest_id = fact.get("atPath")[-1] if fact.get("atPath") else None
    if fact["kind"] == "moved":
        place = locs.get(dest_id, {}).get("name") or fact.get("to")
    else:
        pos = ((state.get("characters") or {}).get(fact["entityId"]) or {}).get("position") or {}
        dest_id = pos.get("containerId")
        place = locs.get(dest_id, {}).get("name")
    visible = []
    for iid, item in (state.get("items") or {}).items():
        if (item.get("position") or {}).get("containerId") == dest_id:
            visible.append((items.get(iid) or {}).get("name") or iid)
    viewer = (initial.get("characters") or {}).get(state.get("protagonistId"), {}).get("name")
    return dict(place=place, visible="、".join(visible), scene=time_of_day(state["time"]["dateTime"]),
                viewer=viewer, destinationId=dest_id)


def fact_line(fact: dict) -> str:
    if fact["kind"] == "moved":
        return f'{fact["name"]}｜移动｜{fact["from"]}→{fact["to"]}'
    return f'{fact["name"]}｜外貌变化｜{fact.get("text")}'


def render(fields: dict, line: str) -> str:
    return TEMPLATE.format(place=fields["place"], visible=fields["visible"], scene=fields["scene"],
                           viewer=fields["viewer"], fact_line=line)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", action="append", required=True)
    ap.add_argument("--point", action="append", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    if len(args.db) != len(args.point):
        raise SystemExit("--db and --point must pair up")

    import torch
    from transformers import T5ForConditionalGeneration, T5Tokenizer
    from transformers.modeling_outputs import BaseModelOutput

    repo = Path(os.environ.get("JITY_REPO", "<repo>"))
    model_dir = repo / ".local/models"
    out_dir = Path(args.out) if args.out else (
        EXP / "artifacts/fact-wording/real-state-smoke" /
        (time.strftime("%Y%m%dT%H%M%S") + "-realstate"))
    out_dir.mkdir(parents=True, exist_ok=False)

    torch.set_num_threads(4)
    torch.manual_seed(0)
    t0 = time.time()
    tokenizer = T5Tokenizer(vocab_file=str(model_dir / "spiece.model"), model_max_length=512)
    model = T5ForConditionalGeneration.from_pretrained(str(model_dir), torch_dtype=torch.float32)
    model.eval()
    load_seconds = time.time() - t0

    run = dict(protocol="c4-real-state-n3n4-smoke-v1", startedAt=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               modelDir=str(model_dir).replace(str(repo), "<repo>"), modelSha256=file_sha(model_dir / "u240-model.safetensors"),
               loadSeconds=round(load_seconds, 3), decoderStartTokenId=model.config.decoder_start_token_id,
               eosTokenId=model.config.eos_token_id, maxNewTokens=64, budgetSeconds=20.0,
               units=[])
    import pydantic
    env = dict(python=platform.python_version(), pydantic=pydantic.VERSION, torch=torch.__version__,
               transformers=__import__("transformers").__version__, device="cpu", threads=4,
               cudaAvailable=torch.cuda.is_available(), os=platform.platform())
    (out_dir / "env.json").write_text(json.dumps(env, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    raw = (out_dir / "raw.jsonl").open("w", encoding="utf-8")
    for db, pid in zip(args.db, args.point):
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        point = load_point(conn, pid)
        before = load_point(conn, point["previousPointId"])
        problems = validate(point, before)
        try:
            db_display = os.path.relpath(db, repo).replace(os.sep, "/")
        except ValueError:
            db_display = os.path.basename(db)
        unit = dict(db=db_display, pointId=pid, version=point["version"],
                    previousPointId=point["previousPointId"], stateDigest=point["stateDigest"],
                    worldId=point["state"].get("worldId"), entityDeltas=point["entityDeltas"],
                    bindingProblems=problems)
        if problems:
            unit["status"] = "binding-failed"
            run["units"].append(unit)
            print(pid, "binding-failed", problems)
            continue

        chain = np.run_pipeline_v2(point, before,
                                   {"entityId": point["state"].get("protagonistId"),
                                    "type": "protagonist"}, real_tok=None)
        unit["n1"] = chain.get("n1")
        unit["n2"] = chain.get("n2")
        unit["n3"] = chain.get("n3")
        unit["plan"] = chain.get("plan")
        unit["selectedFacts"] = chain.get("selectedFacts")
        unit["planImplementation"] = ("flat per-fact calls; N3 grouping/coreference are NOT executed "
                                      "by the wording stage (not implemented)")
        if chain.get("status") != "stopped-at-token-gate":
            unit["status"] = "chain-stopped"
            unit["reason"] = chain.get("reason") or chain.get("status")
            run["units"].append(unit)
            print(pid, "chain-stopped", unit["reason"])
            continue

        unit["status"] = "ran"
        for fact in chain["selectedFacts"]:
            ok, why = applicable(fact)
            if not ok:
                unit.setdefault("unsupported", []).append(
                    dict(factId=fact["factId"], kind=fact["kind"], reason=why))
                continue
            fields = scene_fields(point["state"], fact)
            line = fact_line(fact)
            text_in = render(fields, line)
            enc = tokenizer(text_in, return_tensors="pt")
            if enc.input_ids.shape[1] > 512:
                unit.setdefault("unsupported", []).append(
                    dict(factId=fact["factId"], kind=fact["kind"], reason="input over 512 tokens"))
                continue
            ts = time.time()
            with torch.no_grad():
                hidden = model.encoder(input_ids=enc.input_ids,
                                       attention_mask=enc.attention_mask).last_hidden_state
            encode_seconds = time.time() - ts

            toks, started = [], time.time()
            dec = torch.tensor([[run["decoderStartTokenId"]]], dtype=torch.long)
            stop = "cap"
            while len(toks) < 64:
                if time.time() - started > 20.0:
                    stop = "budget"
                    break
                with torch.no_grad():
                    o = model(encoder_outputs=BaseModelOutput(last_hidden_state=hidden),
                              attention_mask=enc.attention_mask,
                              decoder_input_ids=dec)
                tok = int(torch.argmax(o.logits[0, -1]))
                toks.append(tok)
                if tok == run["eosTokenId"]:
                    stop = "eos"
                    break
                dec = torch.cat([dec, torch.tensor([[tok]], dtype=torch.long)], dim=1)
            decode_seconds = time.time() - started
            text = tokenizer.decode(toks, skip_special_tokens=True)

            row = dict(pointId=pid, version=point["version"], worldId=unit["worldId"],
                       planFactId=fact["factId"], factKind=fact["kind"], fact=fact,
                       place=fields["place"], destinationId=fields["destinationId"],
                       visible=fields["visible"], scene=fields["scene"], viewer=fields["viewer"],
                       input=text_in, inputSha256=sha(text_in),
                       stopReason=stop, newTokens=len(toks),
                       encodeSeconds=round(encode_seconds, 3),
                       decodeSeconds=round(decode_seconds, 3),
                       totalSeconds=round(encode_seconds + decode_seconds, 3),
                       output=text)
            raw.write(json.dumps(row, ensure_ascii=False) + "\n")
            raw.flush()
            unit.setdefault("rows", []).append(dict(planFactId=fact["factId"], inputSha256=sha(text_in),
                                                    stopReason=stop, output=text,
                                                    encodeSeconds=row["encodeSeconds"],
                                                    decodeSeconds=row["decodeSeconds"]))
            print(f'{pid} {fact["factId"]} {stop} enc={row["encodeSeconds"]:.2f}s '
                  f'dec={row["decodeSeconds"]:.2f}s out={text!r}')
        run["units"].append(unit)
    raw.close()

    run["finishedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    run["wallSeconds"] = round(time.time() - t0, 1)
    (out_dir / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("out:", out_dir)
    return 0


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
