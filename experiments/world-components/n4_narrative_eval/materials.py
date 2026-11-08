# 构建叙事判分器的评测材料。
#
# 产出（写到 artifacts/world-components/n4-narrative-eval-v1/）：
#   cases.jsonl            132 个案例：已审目标正文 + 事实 + 场景 + 视角
#   positives.jsonl        132 条已审目标正文（候选正例）
#   mutations.jsonl        单点改动负例（每例只改一处，标注预期触发的规则）
#   legit_probes.jsonl     合法变体（省略时间、同义改写、视角内心理、场景细节）
#   model_outputs.jsonl    真实模型/装配输出（12 条 zero-shot + 12 条槽位臂）
#   annotations.jsonl      人工标注稿（本文件只读，另由作者维护）
#
# 设计约束：负例不拿"逐字不匹配"当错误证据；每个负例都写明改了哪一处、
# 应该触发哪条规则，判分器没抓到就是漏报，抓错了（正例被判 fail）就是误报。

from __future__ import annotations

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
WT = HERE.parents[2]                     # .../world-components-worktree
DEV = HERE.parent / "n4_narrative_dev"
OUT = WT / "artifacts" / "world-components" / "n4-narrative-eval-v1"
C9 = pathlib.Path("D:/others/Jity/.local/parallel/c-browser-t5/artifacts/world-components")

CORPORA = [("corpus.jsonl", "dev-v0"), ("corpus_v1.jsonl", "dev-v1"),
           ("corpus_v2.jsonl", "dev-v2"), ("holdout_corpus.jsonl", "holdout-new-world")]
WORLDS = {"w_fog_harbor": DEV / "world.json",
          "w_snow_pass": DEV / "holdout_world.json"}


def load_jsonl(p: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def dump_jsonl(path: pathlib.Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                    encoding="utf-8")


def load_cases() -> list[dict]:
    rows = []
    for name, split in CORPORA:
        for r in load_jsonl(DEV / name):
            r = dict(r)
            r["_split"] = split
            r["_source"] = name
            rows.append(r)
    return rows


def world_of(case: dict) -> dict:
    return json.loads(WORLDS[case["worldId"]].read_text(encoding="utf-8"))


def other_characters(case: dict, world: dict, exclude: set[str]) -> list[str]:
    names = [v["name"] for v in world["characters"].values()]
    return [n for n in names if n not in exclude]


# ---------------------------------------------------------------- 负例构造

def clamp_text(text: str) -> str:
    return text


def mutation_swap_actor(case: dict, world: dict) -> dict | None:
    """只改动作所在分句的主语，保证"只改一处"且确实改在事实锚点上。"""
    import re
    pov = world["characters"][case["perspective"]["entityId"]]["name"]
    others = other_characters(case, world, {pov})
    if not others or pov not in case["narrative"]:
        return None
    other = others[0]
    anchors = []
    for f in case["facts"]:
        if f["kind"] == "moved" and f.get("to"):
            anchors.append(f["to"])
        elif f["kind"] == "outcome" and f.get("resultText"):
            anchors.append(f["resultText"][-3:])
    sentences = re.split(r"(?<=[。！？])", case["narrative"])
    for i, sent in enumerate(sentences):
        if pov in sent and any(a in sent for a in anchors):
            sentences[i] = sent.replace(pov, other, 1)
            return {"mutation": "swap-actor", "text": "".join(sentences),
                    "edit": f"把动作句的主语「{pov}」换成「{other}」",
                    "expectedRule": "fact.moved.subject|fact.outcome.subject|fact.attribution"}
    return None


def mutation_reverse_direction(case: dict, world: dict) -> dict | None:
    moved = next((f for f in case["facts"] if f["kind"] == "moved"), None)
    if not moved:
        return None
    src, dst, text = moved["from"], moved["to"], case["narrative"]
    if src not in text or dst not in text:
        return None
    tmp = "\x00"
    edited = text.replace(src, tmp).replace(dst, src).replace(tmp, dst)
    return {"mutation": "reverse-direction", "text": edited,
            "edit": f"把「{src}」与「{dst}」对调（事实是 {src}→{dst}）",
            "expectedRule": "fact.moved.direction"}


def mutation_inner_thought(case: dict, world: dict) -> dict | None:
    pov = world["characters"][case["perspective"]["entityId"]]["name"]
    others = other_characters(case, world, {pov})
    if not others:
        return None
    other = others[0]
    edited = case["narrative"] + f"{other}心里一沉，没有再说什么。"
    return {"mutation": "inner-thought-other", "text": edited,
            "edit": f"追加「{other}心里一沉」",
            "expectedRule": "pov.innerOther"}


def mutation_goal_leak(case: dict, world: dict) -> dict | None:
    goal = next((f.get("goal") for f in case["facts"] if f.get("goal")), None)
    if not goal:
        return None
    edited = case["narrative"] + f"他想起还没完成的任务：{goal}。"
    return {"mutation": "goal-leak", "text": edited,
            "edit": f"追加任务目标原文「{goal}」",
            "expectedRule": "forbidden.goal"}


def mutation_numeric_panel(case: dict, world: dict) -> dict | None:
    edited = case["narrative"] + "理智从9升到12，精神值也回到满格。"
    return {"mutation": "numeric-panel", "text": edited,
            "edit": "追加理智数值面板",
            "expectedRule": "forbidden.numeric|forbidden.digit"}


def mutation_duration(case: dict, world: dict) -> dict | None:
    edited = case["narrative"] + "这一趟花了他十二分钟。"
    return {"mutation": "explicit-duration", "text": edited,
            "edit": "追加明确时长「十二分钟」",
            "expectedRule": "forbidden.duration"}


def mutation_new_name(case: dict, world: dict) -> dict | None:
    edited = case["narrative"] + "赵渡站在门口，没说话。"
    return {"mutation": "invented-name", "text": edited,
            "edit": "追加世界设定里没有的人物「赵渡」",
            "expectedRule": "fabrication.name"}


def mutation_drop_fact(case: dict, world: dict) -> dict | None:
    """删掉承载某条必述事实的整句。预期由覆盖规则判出（fail 或 uncertain）。"""
    import re
    for f in case["facts"]:
        anchor = None
        if f["kind"] == "moved" and f.get("to"):
            anchor = f["to"]
        elif f["kind"] == "outcome" and f.get("resultText"):
            anchor = f["resultText"][-3:]
        elif f["kind"] in ("appearance_changed", "personality_changed") and f.get("text"):
            anchor = f["text"][-3:]
        if not anchor or anchor not in case["narrative"]:
            continue
        sentences = re.split(r"(?<=[。！？])", case["narrative"])
        kept = "".join(s for s in sentences if anchor not in s)
        # 只有删干净才算"省略"负例：别处还写着同一事实的句子不算
        if kept.strip() == case["narrative"].strip() or anchor in kept:
            continue
        return {"mutation": "drop-fact", "text": kept,
                "edit": f"删掉含「{anchor}」的整句（事实 {f['factId']}，删后锚点不再出现）",
                "expectedRule": f"fact.{f['kind']}.coverage|fact.{f['kind']}.subject"}
    return None


MUTATIONS = [mutation_swap_actor, mutation_reverse_direction, mutation_inner_thought,
             mutation_goal_leak, mutation_numeric_panel, mutation_duration,
             mutation_new_name, mutation_drop_fact]


# ---------------------------------------------------------------- 合法变体

def legit_ellipsis(case: dict, world: dict) -> dict:
    """时间事实必须模糊或省略；删掉任何时长措辞后仍应判 pass。"""
    text = case["narrative"]
    for pat in ("一会儿", "片刻", "许久"):
        text = text.replace(pat, "")
    return {"probe": "ellipsis-time", "text": text,
            "edit": "删掉模糊时间词（时间事实允许省略）",
            "expected": "not-fail"}


def legit_synonym(case: dict, world: dict) -> dict:
    text = case["narrative"]
    swaps = [("过来", "走进来"), ("下来", "走下来"), ("把", "将")]
    for a, b in swaps:
        if a in text:
            text = text.replace(a, b, 1)
            break
    return {"probe": "synonym", "text": text, "edit": "替换一处动词", "expected": "not-fail"}


def legit_pov_inner(case: dict, world: dict) -> dict:
    pov = world["characters"][case["perspective"]["entityId"]]["name"]
    return {"probe": "pov-inner", "text": case["narrative"] + f"{pov}心里松了一口气。",
            "edit": f"追加视角人物「{pov}」的内心（允许）", "expected": "not-fail"}


def legit_scene_detail(case: dict, world: dict) -> dict:
    scene = case.get("sceneState") or {}
    atmo = scene.get("atmosphere") or "风从门缝里钻进来"
    return {"probe": "scene-detail", "text": case["narrative"] + f"{atmo}。",
            "edit": "追加场景细节（来自 sceneState.atmosphere）", "expected": "not-fail"}


LEGIT = [legit_ellipsis, legit_synonym, legit_pov_inner, legit_scene_detail]


# ---------------------------------------------------------------- 真实输出

def model_outputs(cases: list[dict]) -> list[dict]:
    by_id = {c["id"]: c for c in cases}
    rows = []
    zero = json.loads((C9 / "n4-holdout-r1.json").read_text(encoding="utf-8"))["samples"]
    for s in zero:
        if s["sourceId"] not in by_id:
            continue
        rows.append({"id": f"zero-shot:{s['sourceId']}", "caseId": s["sourceId"],
                     "producer": "n4-formal ckpt, zero-shot new world (n4-holdout-r1)",
                     "text": s["output"], "target": s["target"]})
    slots = json.loads((C9 / "n4-compose-full-r2.json").read_text(encoding="utf-8"))["results"]
    for s in slots:
        if s["id"] not in by_id:
            continue
        rows.append({"id": f"slot-arm:{s['id']}", "caseId": s["id"],
                     "producer": "slot scene arm + fact clauses (n4-compose-full-r2)",
                     "text": s["paragraph"], "target": s["target"] if "target" in s else by_id[s["id"]]["narrative"]})
    return rows


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cases = load_cases()
    world_cache = {k: json.loads(v.read_text(encoding="utf-8")) for k, v in WORLDS.items()}

    dump_jsonl(OUT / "cases.jsonl", [
        {"caseId": c["id"], "worldId": c["worldId"], "split": c["_split"],
         "source": c["_source"], "facts": c["facts"], "sceneState": c["sceneState"],
         "perspective": c["perspective"], "target": c["narrative"],
         "title": c.get("title", "")}
        for c in cases])
    dump_jsonl(OUT / "positives.jsonl", [
        {"id": f"target:{c['id']}", "caseId": c["id"], "text": c["narrative"],
         "provenance": f"已审目标正文（{c['_split']}，reviewStatus="
                       f"{c.get('reviewStatus', 'approved')}）"} for c in cases])

    muts = []
    for c in cases:
        world = world_cache[c["worldId"]]
        for fn in MUTATIONS:
            m = fn(c, world)
            if m:
                muts.append({"id": f"{m['mutation']}:{c['id']}", "caseId": c["id"],
                             **m})
    dump_jsonl(OUT / "mutations.jsonl", muts)

    probes = []
    for c in cases:
        world = world_cache[c["worldId"]]
        for fn in LEGIT:
            p = fn(c, world)
            probes.append({"id": f"{p['probe']}:{c['id']}", "caseId": c["id"],
                           "text": p["text"], "edit": p["edit"],
                           "expected": p["expected"]})
    dump_jsonl(OUT / "legit_probes.jsonl", probes)

    dump_jsonl(OUT / "model_outputs.jsonl", model_outputs(cases))

    print("cases", len(cases), "| positives", len(cases), "| mutations", len(muts),
          "| probes", len(probes), "| outputs", len(model_outputs(cases)))
    print("out:", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
