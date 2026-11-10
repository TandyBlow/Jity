# -*- coding: utf-8 -*-
"""Build (page draft -> prose) pairs that use the product page's own prompt.

The page already has two deterministic pieces (worktrees/06-recovery
`local/prompt.ts` and `local/game-model.ts`):

  * `factualNarration(...)` — the settled-fact draft paragraph;
  * `instructNarrationInput(..., draft)` — the model prompt for rewriting it.

This module reproduces those two shapes in Python so training text equals the
page text. The TS source stays authoritative; the strings below are copied from
it verbatim (2026-11-10, commit of 06's tree recorded in the output manifest).
A later drift in the page template must regenerate this file, not be patched at
inference time.

Targets are the hand-written prose: lane 01's 71 short rows (20 of them the
product world) and, optionally, the 199 frozen scenes. Splits: frozen v1 for the
199 rows, whole-group holdout for lane 01 rows (see build_draft_pairs.py).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.abspath(os.path.join(HERE, ".."))
REPO = os.path.abspath(os.path.join(V2, "..", ".."))

ROWS_V2 = os.path.join(V2, "data", "rows-v2.jsonl")
SHORT_ROWS = os.path.join(V2, "data", "rows-short-v1.jsonl")
SPLIT = os.path.abspath(os.path.join(
    REPO, "experiments", "world-components", "narration-dataset-v1", "splits", "v1.json"))

UNIT = {"second": "秒", "minute": "分钟", "hour": "小时",
        "day": "天", "month": "个月", "year": "年"}

# Verbatim from worktrees/06-recovery/frontend/src/lib/world-engine/local/prompt.ts
# 06's 6a157cb5 unified both heads at 160-240 chars. Keep this in lockstep with
# prompt.ts; check_page_prompt.py compares the rendered prompt byte for byte.
REPAIR_HEAD = "你是中文小说作者。上一稿没能全部落在已结算事实上。请只把下面这段草稿改写成 {name} 视角的小说正文，160 到 240 字。"
SCENE_HEAD = "你是中文小说作者。请把下面这段已经结算的事实草稿改写成 {name} 视角的小说正文，160 到 240 字。"
DRAFT_RULES = ("要求：只能使用草稿里明确写出的动作、位置、外观和结果；可以调整语序、连接词和短句节奏，"
               "但不得新增任何动作、对白、物品、人物、地点、数字、伤情、往事、心理活动或比喻；"
               "每个人物的伤势、衣物和物品只属于本人，不要用“他/她”把一个人的特征挪到另一个人身上；"
               "不要逐条复述草稿，不要把人物外貌列成清单；以动作为主线写成一个连续场景，"
               "环境和人物只保留与当前动作有关的一两笔；不要写标题、列表或 Markdown；分 2 到 3 段。")


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    with io.open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def page_prompt(name: str, draft: str, mode: str = "scene") -> str:
    head = (REPAIR_HEAD if mode == "repair" else SCENE_HEAD).format(name=name)
    return "\n".join([head, DRAFT_RULES, "事实草稿：", draft, "正文："])


def pick_clauses(text: str, count: int = 2) -> str:
    parts = [part.strip() for part in re.split(r"[。；;]", str(text or "")) if part.strip()]
    return "，".join(parts[:count])


VIEWPOINT_RE = re.compile(r"改写成\s*(\S+?)\s*视角")


def viewpoint_name(prompt: str) -> str:
    """The viewpoint the page prompt already names, read back out of it."""
    hit = VIEWPOINT_RE.search(prompt)
    return hit.group(1) if hit else "主角"


def viewpoint_of(x: Dict[str, Any]) -> str:
    view = str(x.get("视角") or "")
    return view.split("（")[-1].split("）")[0] if "（" in view else view


def case_state(x: Dict[str, Any]) -> Dict[str, Any]:
    """The row's before/after state and delta, read from the four-field input."""
    before = x.get("上回合状态") or {}
    after = x.get("本回合状态") or {}
    delta = (x.get("本回合变化") or {}).get("变化") or {}
    time = (x.get("本回合变化") or {}).get("时间推进")
    return {"before": before, "after": after, "delta": delta, "time": time}


def cast_names(before: Dict[str, Any]) -> set:
    """People in the previous state. Items live under '物品' and must not get
    the 'X没有出声' clause the page reserves for characters."""
    people = before.get("人物") or {}
    return set(people.keys())


def page_draft(x: Dict[str, Any]) -> str:
    """A reduced but faithful port of `factualNarration`."""
    state = case_state(x)
    before, after, delta, time = state["before"], state["after"], state["delta"], state["time"]
    view = viewpoint_of(x)
    people_before = before.get("人物") or {}
    mine_before = people_before.get(view) or {}
    mine_after = (after.get(view) or {}) if after else {}
    out: List[str] = []
    if time:
        digits = re.match(r"(\d+)", str(time).replace(" ", ""))
        if digits:
            unit = "分钟"
            for candidate in ("小时", "分钟", "秒", "天", "个月", "年"):
                if candidate in str(time):
                    unit = candidate
                    break
            out.append(f"时间过去了约{digits.group(1)}{unit}。")
    ops = delta.get(view) or {}
    room = mine_after.get("位置") or mine_before.get("位置") or ""
    if isinstance(ops, dict) and ops.get("位置"):
        out.append(f"{view}从{mine_before.get('位置') or ''}走到{ops['位置']}。")
    task_ops = (ops or {}).get("完成任务") if isinstance(ops, dict) else None
    for goal in (task_ops or []):
        out.append(f"{view}完成了「{goal}」。")
    # The page reads the static initial world (`after.initial`), which in these
    # rows is `上回合状态`: locations and people there carry `外貌`. Reading it
    # from `本回合状态` yields empty scenery, because that block only lists what
    # changed this turn.
    locations = (before.get("地点") or {})
    room_look = (locations.get(room) or {}).get("外貌") or []
    if room_look:
        out.append(f"{room}里，{pick_clauses('。'.join(room_look), 2)}。")
    people = cast_names(before)
    present = sorted(people) if people else [name for name in (after or {})]
    for other in present:
        if other == view or other == room:
            continue
        value = (after or {}).get(other) or {}
        position = value.get("位置") or ((before.get("人物") or {}).get(other) or {}).get("位置")
        if position == room:
            look = ((before.get("人物") or {}).get(other) or {}).get("外貌") or []
            out.append(f"{other}{pick_clauses('。'.join(look), 2) if look else '没有出声'}。")
    for other, ops in delta.items():
        if other == view or not isinstance(ops, dict):
            continue
        for goal in (ops.get("完成任务") or []):
            out.append(f"{other}完成了「{goal}」。")
    return "".join(out).strip()


def group_key_for(row: Dict[str, Any]) -> str:
    family = row.get("worldFamily") or "unknown"
    lineage = str(row.get("sourceRowId") or row["id"]).split("#")[-1]
    return f"{family}#{lineage}"


def group_split(key: str) -> str:
    bucket = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16) % 10
    if bucket == 0:
        return "test"
    if bucket in (1, 2):
        return "dev"
    return "train"


SENTENCE = re.compile(r"(?<=[。！？])")
SANITY_WORD = re.compile(r"(精神值|理智值|精神)")


def bigrams(text: str):
    clean = re.sub(r"[^一-鿿]", "", text)
    return {clean[i:i + 2] for i in range(len(clean) - 1)}


def clamp_to_draft(target: str, draft: str, min_overlap: float = 0.0) -> str:
    """Keep only sentences the draft can license.

    The page's draft has no sanity line (`factualNarration` ignores sanity), while
    the hand-written targets sometimes say '精神值从 51 掉到 46'. Training on that
    teaches the model to invent numbers: the v2 adapter wrote '精神值从 53 升到 58'
    on a draft that contained no such change. A sentence that mentions sanity, or
    any number the draft does not contain, is dropped.
    """
    allowed = set(re.findall(r"[0-9]+", draft))
    draft_grams = bigrams(draft)
    kept = []
    for sentence in SENTENCE.split(target):
        if not sentence.strip():
            continue
        if SANITY_WORD.search(sentence):
            continue
        if re.search(r"[「“『]", sentence):
            # The page forbids new dialogue; a target with quoted speech teaches
            # the model to invent it.
            continue
        numbers = set(re.findall(r"[0-9]+", sentence))
        if numbers - allowed:
            continue
        if min_overlap > 0 and draft_grams:
            grams = bigrams(sentence)
            if grams and len(grams & draft_grams) / len(grams) < min_overlap:
                continue
        kept.append(sentence)
    return "".join(kept).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.path.join(V2, "data", "train-page-v1.jsonl"))
    parser.add_argument("--split-manifest", default=os.path.join(V2, "data", "splits-page-v1.json"))
    parser.add_argument("--short-weight", type=int, default=6)
    parser.add_argument("--scenes-weight", type=int, default=2)
    parser.add_argument("--include-scenes", dest="include_scenes", action="store_true", default=False)
    parser.add_argument("--exclude-scenes", dest="include_scenes", action="store_false")
    parser.add_argument("--min-draft-overlap", type=float, default=0.0,
                        help="keep only target sentences whose character bigrams overlap the draft by this share")
    parser.add_argument("--clamp-to-draft", action="store_true",
                        help="drop target sentences the draft cannot license (sanity values, unknown numbers)")
    parser.add_argument("--include-05", action="store_true",
                        help="include 05's 11 hand-written tide scenes as longer targets")
    parser.add_argument("--rows05", default=os.path.join(
        REPO, "..", "05-kernel", "experiments", "narration-quality",
        "corpus-scenes", "generated", "rows.jsonl"))
    parser.add_argument("--prompt-mode", default="scene", choices=("scene", "repair", "both"),
                        help="the page's first attempt uses the repair head (140-220 chars); "
                             "scene is only the second attempt. 'both' emits one row per mode")
    parser.add_argument("--new-rows", default="",
                        help="JSONL of new hand-written rows: id, viewpoint, draft, target, "
                             "optional worldFamily/lineage/sourceWorld; draft is used verbatim")
    parser.add_argument("--page-template-source", default="worktrees/06-recovery/frontend/src/lib/world-engine/local/prompt.ts")
    args = parser.parse_args()

    with io.open(SPLIT, encoding="utf-8") as handle:
        frozen = json.load(handle)
    split_of = {row_id: name for name in ("train", "dev", "test")
                for row_id in frozen.get(name, [])}

    out: List[Dict[str, Any]] = []
    skipped: List[str] = []
    groups: Dict[str, str] = {}
    sources: Dict[str, str] = {"pageTemplate": args.page_template_source}

    if args.include_scenes:
        sources["rows-v2"] = sha256(ROWS_V2)
        for row in read_jsonl(ROWS_V2):
            draft = page_draft(row["x"])
            target = row["y"]
            if args.clamp_to_draft:
                target = clamp_to_draft(target, draft, args.min_draft_overlap)
                if not target:
                    continue
            out.append({"id": row["id"], "split": split_of[row["id"]], "mode": "scene",
                        "draft": draft,
                        "user": page_prompt(viewpoint_of(row["x"]), draft),
                        "target": target, "weight": args.scenes_weight,
                        "source": "rows-v2"})

    sources["rows-short-v1"] = sha256(SHORT_ROWS)
    for row in read_jsonl(SHORT_ROWS):
        draft = page_draft(row["input"])
        if not draft:
            continue
        key = group_key_for(row)
        split = group_split(key)
        groups[key] = split
        target = row["target"]
        if args.clamp_to_draft:
            target = clamp_to_draft(target, draft, args.min_draft_overlap)
            if not target:
                continue
        out.append({"id": row["id"], "split": split, "mode": "scene", "draft": draft,
                    "user": page_prompt(viewpoint_of(row["input"]), draft),
                    "target": target, "weight": args.short_weight,
                    "source": "short-01"})

    if args.include_05 and os.path.exists(args.rows05):
        sources["rows-05"] = sha256(args.rows05)
        for row in read_jsonl(args.rows05):
            draft = page_draft(row["input"])
            if not draft:
                continue
            # 05's rows are one continuous sequence, so they stay in train and
            # never provide a dev or test sample.
            target = row["targetText"]
            if args.clamp_to_draft:
                target = clamp_to_draft(target, draft, args.min_draft_overlap)
                if not target:
                    continue
            out.append({"id": row["id"], "split": "train", "mode": "scene", "draft": draft,
                        "user": page_prompt(viewpoint_of(row["input"]), draft),
                        "target": target,
                        "weight": max(1, args.short_weight // 2),
                        "source": "short-05"})

    if args.new_rows:
        sources["new-rows"] = sha256(args.new_rows)
        for row in read_jsonl(args.new_rows):
            draft = (row.get("draft") or "").strip()
            target = (row.get("target") or "").strip()
            viewpoint = row.get("viewpoint") or ""
            if not draft or not target or not viewpoint:
                # A row without a draft, a target or a viewpoint cannot become a
                # page prompt; skip it loudly instead of guessing a viewpoint.
                skipped.append(row.get("id", "?"))
                continue
            if args.clamp_to_draft:
                target = clamp_to_draft(target, draft, args.min_draft_overlap)
                if not target:
                    skipped.append(row.get("id", "?"))
                    continue
            family = row.get("worldFamily") or row.get("sourceWorld") or "unknown"
            key = f"{family}#{row.get('lineage') or row.get('sourceWorld') or 'single'}"
            split = group_split(key)
            groups[key] = split
            out.append({"id": row["id"], "split": split, "mode": "scene", "draft": draft,
                        "user": page_prompt(viewpoint, draft), "target": target,
                        "weight": args.short_weight, "source": "new-rows"})

    if args.prompt_mode != "scene":
        # The page's first attempt is the repair head (140-220 chars); the free
        # scene head is only the second attempt. Training on scene alone left the
        # arm unable to write the prompt the page actually sends first.
        if args.prompt_mode == "repair":
            for row in out:
                row["user"] = page_prompt(viewpoint_name(row["user"]), row["draft"], "repair")
                row["promptMode"] = "repair"
        else:
            expanded = []
            for row in out:
                name = viewpoint_name(row["user"])
                repair = dict(row)
                repair["id"] = row["id"] + "-repair"
                repair["user"] = page_prompt(name, row["draft"], "repair")
                repair["promptMode"] = "repair"
                scene = dict(row)
                scene["id"] = row["id"] + "-scene"
                scene["promptMode"] = "scene"
                expanded.extend([repair, scene])
            out = expanded

    with io.open(args.split_manifest, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({"version": "page-splits-v1",
                                 "groups": groups,
                                 "rule": "frozen v1 splits for the 199 rows; whole-group holdout "
                                         "(worldFamily#lineage) for lane-01 rows"},
                                ensure_ascii=False, indent=1) + "\n")

    with io.open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        for row in out:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    counts: Dict[str, int] = {}
    weighted: Dict[str, int] = {}
    for row in out:
        counts[row["split"]] = counts.get(row["split"], 0) + 1
        weighted[row["split"]] = weighted.get(row["split"], 0) + row["weight"]
    summary = {"rows": len(out), "sha256": sha256(args.out), "splits": counts,
               "weighted": weighted, "sources": sources, "out": args.out,
               "splitManifest": args.split_manifest,
               "splitManifestSha256": sha256(args.split_manifest),
               "skipped": skipped,
               "sample": out[0]["user"] if out else ""}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
