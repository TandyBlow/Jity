"""C8 fresh-eval source inventory and exclusion basis builder.

Reads a declared source list (never globs blindly by directory), records for
every file its sha256 / bytes / row count, and extracts two different things:

  blocking strings  narrative-bearing text (sentences, fact texts, rendered
                    model inputs). These become the >=4-char bidirectional
                    substring exclusion corpus.
  vocabulary        registry-ish values (character / location / task / item
                    names) from structured world blocks, fact objects, rendered
                    input headers and perspective strings. Used to prove the new
                    scenario set introduces new names, not to block sentences.

Outputs (all under artifacts/world-components/fresh-eval/sources/):
  inventory.json / .md          per-source, per-file evidence
  exclusion-corpus.jsonl        unique blocking strings + their origins
  vocab-used.json / .md         vocabulary buckets + origins
  exclusion-scope.json          declared scope, rules, the 10 three-arm signatures

Scope semantics per source:
  text  -> contributes blocking strings
  vocab -> contributes vocabulary only (fixtures / reports with real content)
  none  -> registered, no content contribution

No file outside this directory is written.

Usage:
  python artifacts/world-components/fresh-eval/tools/build_inventory.py
  python artifacts/world-components/fresh-eval/tools/build_inventory.py --check
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent                      # artifacts/world-components/fresh-eval
REPO = OUT.parents[2]                  # .../c-fresh-eval
CJK = re.compile(r"[\u4e00-\u9fff]")
CJK_RUN = re.compile(r"[\u4e00-\u9fff]{2,8}")

def _three_arm_facts(kinds, actors, amount, unit):
    """Build a fact list for the ten frozen items.

    Change facts (moved / task / personality / sanity_changed) use at most
    `actors` distinct actors; standing facts (at / plain sanity) reuse the same
    ids and never enter the change signature.
    """
    changes = [k for k in kinds if k in _screening.CHANGE_KINDS]
    change_actors = min(actors, len(changes)) if changes else 0
    facts, ci = [], 0
    for kind in kinds:
        if kind in _screening.CHANGE_KINDS:
            facts.append({"kind": kind, "actor": f"a{ci % max(change_actors, 1)}"})
            ci += 1
        else:
            facts.append({"kind": kind, "actor": f"a{ci % max(actors, 1)}"})
    return facts

_spec = importlib.util.spec_from_file_location("screening", HERE / "screening.py")
_screening = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_screening)
signature_of = _screening.signature_of
write_artifact = _screening.write_artifact

# ---------------------------------------------------------------- sources ---
SOURCES: list[dict] = [
    # --- the three-arm comparison set and its sibling question sets ---
    dict(id="s01", label="三臂对照 10 题（nv-*，含 mechanical/reference/forbidden）",
         path="frontend/src/lib/world-engine/runtime/narration-eval-samples.ts",
         kind="ts", role="eval", scope="text",
         note="本轮明确排除的主集合；改名派生按事实签名排除，见 exclusion-scope.json"),
    dict(id="s02", label="叙事事实核验题（hv-*）",
         path="frontend/src/lib/world-engine/runtime/narration-eval-validation.ts",
         kind="ts", role="eval", scope="text"),
    dict(id="s03", label="叙事拆分题（ns-*，四件套输入）",
         path="frontend/src/lib/world-engine/runtime/narration-split-samples.ts",
         kind="ts", role="eval", scope="text"),
    dict(id="s04", label="B3 四件套输入样本",
         path="frontend/src/lib/world-engine/runtime/b3-samples.ts",
         kind="ts", role="eval", scope="text"),
    dict(id="s05", label="B3 短句样本（周宁/林川）",
         path="frontend/src/lib/world-engine/runtime/b3-short-samples.ts",
         kind="ts", role="eval", scope="text"),
    dict(id="s06", label="focus 输入样本",
         path="frontend/src/lib/world-engine/runtime/focused-input.ts",
         kind="ts", role="tuning-dev", scope="text"),

    # --- live-run archives that contain generated/committed text ---
    dict(id="s07", label="三臂真机运行归档（manifest + run）",
         path="artifacts/narration-eval", glob="*.json",
         kind="json-glob", role="live-archive", scope="text"),
    dict(id="s08", label="三臂复核归档",
         path="artifacts/narration-eval-recheck/run.json",
         kind="json", role="live-archive", scope="text"),
    dict(id="s09", label="拆分基线输出",
         path="artifacts/narration-split-baseline.json",
         kind="json", role="live-archive", scope="text"),
    dict(id="s10", label="世界页面整链归档",
         path="artifacts/world-page", glob="*.json",
         kind="json-glob", role="live-archive", scope="text"),
    dict(id="s11", label="真实 HTTP 叙事复核",
         path="artifacts/narration-http-review.json",
         kind="json", role="live-archive", scope="text"),
    dict(id="s12", label="规则事实整链归档",
         path="artifacts/rule-facts", glob="*.json",
         kind="json-glob", role="live-archive", scope="text"),
    dict(id="s13", label="B3 短句真机输出",
         path="artifacts/b3-short", glob="*.json",
         kind="json-glob", role="live-archive", scope="text"),
    dict(id="s14", label="H2 集成验收报告（无中文内容，仅结构证据）",
         path="artifacts/h2-integration-d1d2de0", glob="*.json",
         kind="json-glob", role="report", scope="none",
         note="实测 0 个中文字符：只有 ID / 哈希 / 计数，不贡献排除串"),

    # --- training / tuning corpora ---
    dict(id="s20", label="N4 成句语料（300 seed + 300 rewrite）",
         path="experiments/world-components/n4_corpus", glob="*.jsonl",
         kind="jsonl-glob", role="training", scope="text"),
    dict(id="s21", label="N4 v2/v3/v3a 训练与留出语料",
         path="experiments/world-components/n4_corpus_v2", glob="**/*.jsonl",
         kind="jsonl-glob", role="training", scope="text"),
    dict(id="s22", label="N5 支持/扰动对（train + test）",
         path="experiments/world-components/n4_corpus_v2/corpus_v2/n5", glob="*.jsonl",
         kind="jsonl-glob", role="training", scope="text"),
    dict(id="s23", label="N4 独立留出集（24 组 / 48 行）",
         path="experiments/world-components/n4_holdout/holdout.jsonl",
         kind="jsonl", role="eval", scope="text"),
    dict(id="s24", label="N4 改写语料 60/100",
         path="experiments/world-components/n4_rewrite60", glob="corpus*.jsonl",
         kind="jsonl-glob", role="training", scope="text"),
    dict(id="s25", label="N4 场景/叙事/动词开发集",
         path="experiments/world-components/n4_narrative_dev", glob="*.jsonl",
         kind="jsonl-glob", role="training", scope="text"),
    dict(id="s26", label="N2 选择样本与标注",
         path="experiments/world-components/n2_selection", glob="**/*.jsonl",
         kind="jsonl-glob", role="tuning-dev", scope="text"),
    dict(id="s27", label="N4/N2 契约与生成抽样（artifacts 侧）",
         path="artifacts/world-components", glob="*.jsonl",
         kind="jsonl-glob", role="training", scope="text"),
    dict(id="s28", label="organize/wording 三档语料与运行抽样",
         path="artifacts/world-components/organize-wording", glob="**/*.jsonl",
         kind="jsonl-glob", role="tuning-dev", scope="text"),
    dict(id="s29", label="行动分类器调参语料",
         path="artifacts/benchmark", glob="classifier-*.json",
         kind="json-glob", role="tuning-dev", scope="text"),
    dict(id="s33", label="attention-selection 六条件与人工选择",
         path="artifacts/world-components/organize-wording/attention-selection-v1.json",
         kind="json", role="tuning-dev", scope="text"),

    # --- protocol fixtures (structural authority; vocabulary only) ---
    dict(id="s30", label="v1 学校世界夹具（10 份）",
         path="design/world-protocol/v1/fixtures", glob="*.json",
         kind="json-glob", role="fixture", scope="vocab",
         note="夹具共用 world_school / person_a-f / 走廊大厅门厅教室；新场景不得复用"),
    dict(id="s31", label="v2 契约夹具与轨迹",
         path="design/world-protocol/v2", glob="**/*.json",
         kind="json-glob", role="fixture", scope="none",
         note="只登记：api/branches/errors 是结构夹具，内容不进入叙事排除语料"),
    dict(id="s32", label="前端世界夹具与 t01-t08 场景",
         path="frontend/src/lib/world-engine", glob="*.ts",
         kind="ts-glob", role="fixture", scope="vocab"),
    dict(id="s34", label="旧产品战役与开场剧本（龙族内容，词表来源）",
         path="backend/data", glob="**/*.json",
         kind="json-glob", role="fixture", scope="vocab",
         note="旧 TRPG 战役/剧本非本引擎素材；只收词表，避免新场景撞回旧人名地名"),
    dict(id="s35", label="仓库根验收/签署 Markdown",
         path="artifacts", glob="*.md",
         kind="md-glob", role="report", scope="none"),

    # --- 主树（world-server 侧）的历史训练/调参归档：本工作树里没有这些文件 ---
    dict(id="s50", label="主树 cohesion-split（组内聚与拆分组调参）",
         path="artifacts/cohesion-split", glob="**/*.json",
         kind="json-glob", role="tuning-dev", scope="text", tree="main"),
    dict(id="s51", label="主树 decode-compare（解码对照 215/40 例）",
         path="artifacts/decode-compare", glob="**/*.json",
         kind="json-glob", role="tuning-dev", scope="text", tree="main"),
    dict(id="s52", label="主树 statement-extractor / statement-verification（陈述抽取与核验）",
         path="artifacts/statement-extractor", glob="**/*.json",
         kind="json-glob", role="training", scope="text", tree="main"),
    dict(id="s53", label="主树 statement-verification（标签、切分冻结与报告）",
         path="artifacts/statement-verification", glob="**/*.json",
         kind="json-glob", role="training", scope="text", tree="main"),
    dict(id="s54", label="主树 world-provenance（叙事来源/证据对照）",
         path="artifacts/world-provenance", glob="**/*.json",
         kind="json-glob", role="tuning-dev", scope="text", tree="main"),
    dict(id="s55", label="主树 world-integration 与 h2 归档（结构证据）",
         path="artifacts", glob="world-integration-*/**/*.json",
         kind="json-glob", role="report", scope="none", tree="main"),
    dict(id="s56", label="主树 benchmark 全量（分类器/CRF/叙述样本）",
         path="artifacts/benchmark", glob="**/*.json",
         kind="json-glob", role="tuning-dev", scope="text", tree="main"),
    dict(id="s57", label="主树 smoke（旧战役冒烟）",
         path="artifacts/smoke", glob="**/*.json",
         kind="json-glob", role="live-archive", scope="text", tree="main"),

    # --- reports (registered, not content-blocking) ---
    dict(id="s40", label="组件/世界引擎报告",
         path="design", glob="**/*.md",
         kind="md-glob", role="report", scope="none"),
]

# The ten frozen three-arm items: shape signature = (fact kinds, actors, time).
NV_SIGNATURES = [
    ("nv-move-1", ["moved"], 1, 2, "minute"),
    ("nv-task-pers-sanity-1", ["personality_changed", "sanity_changed", "task_achieved"], 1, 1, "minute"),
    ("nv-multi-1", ["at", "moved"], 2, 1, "minute"),
    ("nv-task-only-1", ["task_achieved"], 1, 30, "second"),
    ("nv-refused-1", [], 0, 1, "second"),
    ("nv-empty-1", [], 0, 5, "minute"),
    ("nv-cont-1", ["moved"], 1, 2, "second"),
    ("nv-cont-2", ["at"], 1, 2, "minute"),
    ("nv-cont-3", ["at"], 1, 5, "minute"),
    ("nv-multi-opposite-1", ["moved", "moved"], 2, 3, "second"),
]

RULES = {
    "textMatch": "双向子串：候选串与排除串任一方向包含即命中；只比较 ≥4 个汉字的内容串",
    "noteStrip": "含（）注记的排除串，剥掉注记后的核心串同样入集（nv-cont-1 冒烟教训）",
    "castWords": "人物/地名等词表项：零命中才是目标，命中即改名，不按子串宽容量放过",
    "signature": "事实签名=(kind 计数, 涉及人物数, 时长折算秒数)；与 nv-* 十题任一相同即判改名派生",
    "signatureTime": "时长先折算成秒再比：2 分钟与 120 秒视为同一时长，防单位改名绕过",
    "signatureLimit": "签名只覆盖事实形状，不覆盖语义；形状不同也可能是派生，由人工核验补",
    "excludedFields": "结构字段 kind/unit/ref/amount/entityId/scope 不参与文本比对",
    "unknownProvenance": "来源或用途无法追到文件与哈希的场景记为 undetermined，不进入候选池",
}

# Keys whose string values are narrative text (blocking) rather than registry.
BLOCK_KEYS = {
    "text", "sentence", "narrative", "target", "reference", "mechanical", "input",
    "note", "atmosphere", "timeNarrative", "resultText", "reason", "phrase",
    "mustNotAdd", "mustNotFabricate", "forbidden", "mayMention", "rule", "contract",
    "appearance", "initialAppearance", "atmosphere",
}
# Keys whose string values are registry vocabulary. Fact objects are handled
# separately (a fact's `name` is a character for character facts and a place for
# appearance facts — treating it as always-character polluted the bucket).
VOCAB_KEYS = {
    "names": "other", "characterContext": "characters", "roster": "characters",
    "present": "characters", "viewpoint": "characters", "viewpointName": "characters",
    "props": "items", "visibleItems": "items", "visible": "items",
    "location": "locations", "loc": "locations", "place": "locations",
    "locationPath": "locations", "at": "locations", "from": "locations",
    "to": "locations", "goal": "tasks", "taskGoal": "tasks", "title": "other",
}
CHARACTER_FACT_KINDS = {"moved", "positioned_at", "task_achieved",
                        "personality_changed", "sanity_changed", "at"}
PROTOCOL_ID = re.compile(r"\b(?:person|char|loc|task|item|world|entity|scene|point|round|group|n4|n4h|n2|v2|nv|hv|ns|b3)[-_][a-z0-9_]{1,20}\b")
GENERIC = {
    "moved", "positioned_at", "task_achieved", "personality_changed", "sanity_changed",
    "appearance_changed", "position", "appearance", "personality", "sanity", "task",
    "time", "movement", "multi_character", "continuity", "empty_delta",
    "task_personality_sanity", "root", "commit", "protagonist", "third-person",
    "第三人称", "主角视角", "视角", "外貌", "性格", "人格", "精神值", "任务达成",
}
# Rendered n4 input headers: 人物=A、B / 地点=… / 视角=… / 事实=…
HDR_KEY = {"人物": "characters", "地点": "locations", "地点可见": "items",
           "视角": "characters", "事实": "tasks"}
TS_STR = re.compile(r"""'([^'\\\n]{2,})'|"([^"\\\n]{2,})"|`([^`\\\n]{2,})`""")
TS_KEY_STR = re.compile(
    r'''\b(name|goal|location|loc|place|from|to|at|roster|present|props|title|'''
    r'''viewpoint|taskGoal|visible)\s*:\s*(['"`])([^'"`]+)\2''')
TS_ARRAY_KEY = re.compile(r"\b(roster|present|props|locations|visible|names)\s*:\s*\[([^\]]*)\]")
SPLIT_TOKENS = re.compile(r"[、，,；;/｜|。：:\s]")


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


MAIN_TREE = REPO.parents[2]           # 仓库主树（world-server 检出）


def source_root(entry: dict) -> pathlib.Path:
    return MAIN_TREE if entry.get("tree") == "main" else REPO


def resolve(entry: dict) -> list[pathlib.Path]:
    base = source_root(entry) / entry["path"]
    if "glob" not in entry:
        return [base] if base.exists() else []
    return sorted(p for p in base.glob(entry["glob"]) if p.is_file())


def header_vocab(s: str):
    """Parse rendered-input header lines: 人物=甲、乙 → characters."""
    out = []
    for line in s.splitlines():
        m = re.match(r"^(人物|地点|地点可见|视角|事实)=(.+)$", line.strip())
        if not m:
            continue
        bucket = HDR_KEY[m.group(1)]
        # 风格：渲染输入的一行可带子字段（视角=陆行；性格=谨慎；外貌=旧羊皮袄），
        # 子字段不是名字，整段丢弃。
        for seg in m.group(2).split("；"):
            if "=" in seg or "：" in seg:
                continue
            for tok in SPLIT_TOKENS.split(seg):
                tok = tok.strip().strip("「」『』（）()")
                tok = re.sub(r"[｜|].*$", "", tok).strip()
                if 2 <= len(tok) <= 10 and CJK.search(tok):
                    out.append((bucket, tok))
    return out


def add_terms(vocab, bucket, value):
    for tok in SPLIT_TOKENS.split(value):
        tok = tok.strip().strip("「」『』（）()")
        if "=" in tok or "：" in tok:
            continue                          # 子字段串，不是名字
        if 2 <= len(tok) <= 12 and CJK.search(tok) and tok not in GENERIC:
            vocab.setdefault(bucket, []).append(tok)


def registry_terms(world, vocab, blocking):
    """Explicit world registry shapes: characters/locations/items as dict or
    list, plus the flat `names` list used by the v2 corpora."""
    if not isinstance(world, dict):
        return
    for bucket, key in (("characters", "characters"), ("locations", "locations"),
                        ("items", "items")):
        entries = world.get(key)
        if isinstance(entries, dict):
            entries = list(entries.values())
        if isinstance(entries, list):
            for ent in entries:
                if isinstance(ent, dict) and CJK.search(str(ent.get("name", ""))):
                    add_terms(vocab, bucket, ent["name"])
                    for t in ent.get("tasks", []) or []:
                        if isinstance(t, dict) and CJK.search(str(t.get("goal", ""))):
                            add_terms(vocab, "tasks", t["goal"])
                    if bucket == "locations" and len(CJK.findall(ent.get("initialAppearance", ""))) >= 4:
                        blocking.append(("initialAppearance", ent["initialAppearance"]))
    for n in world.get("names", []) or []:
        if isinstance(n, str) and CJK.search(n):
            add_terms(vocab, "other", n)


def harvest(node, key, blocking, vocab):
    if isinstance(node, dict):
        if "world" in node:
            registry_terms(node["world"], vocab, blocking)
        is_fact = "kind" in node and "name" in node
        for k, v in node.items():
            if is_fact and k == "name":
                continue                      # handled by the fact branch below
            harvest(v, k, blocking, vocab)
        if is_fact and isinstance(node.get("name"), str) and CJK.search(node["name"]):
            group = node.get("entityGroup")
            bucket = ("characters" if node.get("kind") in CHARACTER_FACT_KINDS
                      else "other")
            if group in ("characters", "locations", "items"):
                bucket = group
            add_terms(vocab, bucket, node["name"])
        return
    if isinstance(node, list):
        for v in node:
            harvest(v, key, blocking, vocab)
        return
    if not isinstance(node, str):
        return
    for pid in PROTOCOL_ID.findall(node):
        vocab.setdefault("protocolIds", []).append(pid)
    if not CJK.search(node) or node in GENERIC:
        return
    if key in BLOCK_KEYS:
        if len(CJK.findall(node)) >= 4:
            blocking.append((key, node))
        for bucket, tok in header_vocab(node):
            vocab.setdefault(bucket, []).append(tok)
        return
    if key in VOCAB_KEYS:
        bucket = VOCAB_KEYS[key]
        add_terms(vocab, bucket, node)
        if len(CJK.findall(node)) >= 4 and bucket != "characters":
            # location/place strings often carry a descriptor; keep the whole
            # string too so exact reuse is caught
            blocking.append((key, node))
        return
    # unclassified CJK string: vocabulary only, never a blocked sentence
    for tok in CJK_RUN.findall(node):
        if len(tok) <= 6 and tok not in GENERIC:
            vocab.setdefault("other", []).append(tok)


def extract(path: pathlib.Path, kind: str):
    blocking: list[tuple[str, str]] = []
    vocab: dict[str, list[str]] = {}
    if kind.startswith("ts") or kind.startswith("md"):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            # TS object literals: name: '学生A', goal: '…', roster: [...]
            for m in TS_KEY_STR.finditer(line):
                key, s = m.group(1), m.group(3)
                s = re.sub(r"\$\{[^}]*\}", "", s).strip()
                if not CJK.search(s) or s in GENERIC:
                    continue
                bucket = VOCAB_KEYS.get(key)
                if bucket:
                    add_terms(vocab, bucket, s)
                if len(CJK.findall(s)) >= 4:
                    blocking.append((key, s))
            for m in TS_ARRAY_KEY.finditer(line):
                key = m.group(1)
                bucket = VOCAB_KEYS.get(key)
                if not bucket:
                    continue
                for sm in TS_STR.finditer(m.group(2)):
                    s = next(g for g in sm.groups() if g).strip()
                    if CJK.search(s):
                        add_terms(vocab, bucket, s)
        for m in TS_STR.finditer(text):
            s = re.sub(r"\$\{[^}]*\}", "", next(g for g in m.groups() if g)).strip()
            if not CJK.search(s) or s in GENERIC:
                continue
            if len(CJK.findall(s)) >= 4:
                blocking.append(("ts-string", s))
            else:
                add_terms(vocab, "other", s)          # 短字面量（人名/地名常量）
            for bucket, tok in header_vocab(s):
                vocab.setdefault(bucket, []).append(tok)
        for pid in PROTOCOL_ID.findall(text):
            vocab.setdefault("protocolIds", []).append(pid)
        return blocking, vocab

    if kind.startswith("jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            harvest(json.loads(line), None, blocking, vocab)
        return blocking, vocab

    harvest(json.loads(path.read_text(encoding="utf-8")), None, blocking, vocab)
    return blocking, vocab


def main() -> int:
    check = "--check" in sys.argv
    head = git_head()
    inv = {
        "formatVersion": 2,
        "purpose": "C8 独立评测场景：来源清点与排除依据",
        "worktree": {"branch": "exp/c-fresh-eval", "head": head},
        "scopeSemantics": {
            "text": "贡献整句排除串（叙事文本）",
            "vocab": "只贡献词表，用于证明新名字",
            "none": "已登记，不贡献内容",
        },
        "sources": [],
    }
    blocked: dict[str, dict] = {}
    vocab_all: dict[str, dict] = {"characters": {}, "locations": {}, "tasks": {},
                                  "items": {}, "other": {}, "protocolIds": {}}
    for entry in SOURCES:
        files = resolve(entry)
        rec = {"id": entry["id"], "label": entry["label"], "role": entry["role"],
               "scope": entry["scope"], "path": entry["path"],
               "note": entry.get("note", ""), "exists": bool(files),
               "files": [], "blockingStrings": 0, "vocabTerms": 0}
        for f in files:
            rows = None
            if f.suffix == ".jsonl":
                rows = sum(1 for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip())
            b, v = (extract(f, entry["kind"]) if entry["scope"] != "none"
                    else ([], {}))
            prefix = "" if entry.get("tree") != "main" else "main-tree:"
            rec["files"].append({"path": prefix + f.relative_to(source_root(entry)).as_posix(),
                                 "sha256": sha256(f), "bytes": f.stat().st_size,
                                 "rows": rows,
                                 "blockingStrings": len(set(b)),
                                 "vocabTerms": sum(len(set(x)) for x in v.values())})
            rec["blockingStrings"] += len(set(b))
            rec["vocabTerms"] += sum(len(set(x)) for x in v.values())
            if entry["scope"] == "text":
                for key, s in b:
                    rec_b = blocked.setdefault(s, {"sources": [], "keys": []})
                    if entry["id"] not in rec_b["sources"]:
                        rec_b["sources"].append(entry["id"])
                    if key not in rec_b["keys"] and len(rec_b["keys"]) < 4:
                        rec_b["keys"].append(key)
            if entry["scope"] in ("text", "vocab"):
                for bucket, toks in v.items():
                    for t in set(toks):
                        d = vocab_all[bucket].setdefault(t, {"sources": []})
                        if entry["id"] not in d["sources"]:
                            d["sources"].append(entry["id"])
        inv["sources"].append(rec)

    gap_files = [f"{label}:{path.relative_to(root).as_posix()}"
                 for label, root in (("worktree", REPO), ("main-tree", MAIN_TREE))
                 for path in sorted((root / "artifacts/world-chain").glob("*.json"))
                 if path.is_file()]
    inv["knownSourceGaps"] = [{
        "path": "artifacts/world-chain/*.json",
        "checkedRoots": [REPO.as_posix(), MAIN_TREE.as_posix()],
        "foundFiles": gap_files,
        "status": "not-in-exclusion-corpus" if gap_files else "missing-in-checked-roots",
        "coverage": "undetermined",
    }]

    exclusion = {
        "formatVersion": 2,
        "worktreeHead": head,
        "rules": RULES,
        "textScopeSources": [s["id"] for s in inv["sources"] if s["scope"] == "text"],
        "vocabScopeSources": [s["id"] for s in inv["sources"] if s["scope"] == "vocab"],
        "threeArmItems": [
            {"id": i, "kinds": sorted(k), "actors": a, "timeAmount": t,
             "timeUnit": u,
             "changeKinds": sorted(x for x in k if x in _screening.CHANGE_KINDS),
             "signature": _screening.change_signature(
                 _three_arm_facts(k, a, t, u), {"amount": t, "unit": u}),
             "fullSignature": _screening.full_signature(
                 _three_arm_facts(k, a, t, u), {"amount": t, "unit": u})}
            for (i, k, a, t, u) in NV_SIGNATURES
        ],
        "threeArmSiblings": {
            "hv-*": "narration-eval-validation.ts（事实核验题）",
            "ns-*": "narration-split-samples.ts（拆分四件套）",
            "b3-*": "b3-samples.ts / b3-short-samples.ts",
        },
        "knownLimits": [
            "artifacts/world-chain/*.json 未纳入：当前工作树及主树未找到，历史覆盖记为 undetermined；不代表所有检出或 Git 历史均无此归档",
            "TS 类型代码与注释不扫；Markdown 报告不参与整句排除",
            "未登记的新文件不会自动进入排除集：改源清单必须重跑本脚本并更新哈希",
            "签名只覆盖事实形状，语义派生（换地点、换任务但同形）仍需人工核验",
            "词表来自结构化字段与渲染输入表头；只在正文散文里出现的人名可能漏收",
        ],
    }

    if check:
        path = OUT / "sources/inventory.json"
        if not path.exists():
            print("no inventory to check")
            return 1
        old = json.loads(path.read_text(encoding="utf-8"))
        old_map = {f["path"]: f["sha256"] for s in old["sources"] for f in s["files"]}
        new_map = {f["path"]: f["sha256"] for s in inv["sources"] for f in s["files"]}
        drift = [p for p in sorted(set(old_map) | set(new_map))
                 if old_map.get(p) != new_map.get(p)]
        missing = [s["id"] for s in inv["sources"] if not s["exists"]]
        print(f"files old={len(old_map)} new={len(new_map)} drift={len(drift)} "
              f"missingSources={missing} blockedOld={old.get('blockingTotal')}")
        for p in drift:
            print("  DRIFT", p)
        stored_corpus = [json.loads(line) for line in
                         (OUT / "sources/exclusion-corpus.jsonl").read_text(encoding="utf-8").splitlines()
                         if line.strip()]
        expected_corpus = [{"text": s, **blocked[s]} for s in sorted(blocked)]
        stored_vocab = json.loads((OUT / "sources/vocab-used.json").read_text(encoding="utf-8"))
        expected_vocab = {b: dict(sorted(v.items())) for b, v in vocab_all.items()}
        stored_scope = json.loads((OUT / "sources/exclusion-scope.json").read_text(encoding="utf-8"))
        corpus_ok = stored_corpus == expected_corpus
        vocab_ok = stored_vocab["buckets"] == expected_vocab
        scope_ok = all(stored_scope.get(k) == v for k, v in exclusion.items()
                       if k != "worktreeHead")
        known_gaps_ok = old.get("knownSourceGaps") == inv["knownSourceGaps"]
        print(f"corpusMatches={corpus_ok} vocabularyMatches={vocab_ok} "
              f"scopeMatches={scope_ok} knownGapsMatch={known_gaps_ok}")
        ok = (not drift and not missing and old.get("blockingTotal") == len(blocked)
              and corpus_ok and vocab_ok and scope_ok and known_gaps_ok)
        print("CHECK", "OK" if ok else "FAIL")
        return 0 if ok else 1

    (OUT / "sources").mkdir(parents=True, exist_ok=True)
    inv["blockingTotal"] = len(blocked)
    inv["vocabTotal"] = {b: len(v) for b, v in vocab_all.items()}

    write_artifact(OUT / "sources/inventory.json", 
        json.dumps(inv, ensure_ascii=False, indent=1) + "\n")
    with (OUT / "sources/exclusion-corpus.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for s in sorted(blocked):
            fh.write(json.dumps({"text": s, "sources": blocked[s]["sources"],
                                 "keys": blocked[s]["keys"]}, ensure_ascii=False) + "\n")
    write_artifact(OUT / "sources/vocab-used.json", 
        json.dumps({"worktreeHead": head,
                    "buckets": {b: dict(sorted(v.items())) for b, v in vocab_all.items()}},
                   ensure_ascii=False, indent=1) + "\n")
    exclusion["blockingStrings"] = len(blocked)
    exclusion["vocabCounts"] = {b: len(v) for b, v in vocab_all.items()}
    exclusion["vocabUnionCount"] = len(set().union(*[set(v) for v in vocab_all.values()]))
    write_artifact(OUT / "sources/exclusion-scope.json", 
        json.dumps(exclusion, ensure_ascii=False, indent=1) + "\n")

    lines = ["# 来源清点（自动生成，勿手改）", "",
             f"工作树 HEAD：`{head}`；生成脚本 `tools/build_inventory.py`。", "",
             "| 编号 | 来源 | 角色 | 范围 | 文件数 | 排除串 | 词表项 |",
             "|---|---|---|---|---:|---:|---:|"]
    for s in inv["sources"]:
        lines.append(f"| {s['id']} | {s['label']} | {s['role']} | {s['scope']} | "
                     f"{len(s['files'])} | {s['blockingStrings']} | {s['vocabTerms']} |")
    lines += ["", f"合计：排除串 {len(blocked)} 条（去重后），词表 "
              f"{', '.join(f'{b} {len(v)}' for b, v in vocab_all.items())}。", "",
              "范围：`text`=贡献整句排除串；`vocab`=只贡献词表；`none`=仅登记。", ""]
    missing = [s["id"] for s in inv["sources"] if not s["exists"]]
    lines.append(f"**缺失来源**：{', '.join(missing) if missing else '无（全部登记文件已找到）'}")
    lines += ["", "**历史覆盖缺口**（不计入上述已登记的 39 条来源）："]
    for gap in inv["knownSourceGaps"]:
        lines.append(f"- `{gap['path']}`：{gap['status']}；已找到 {len(gap['foundFiles'])} 个文件；"
                     "当前工作树/主树范围之外未核实，不能据此声明历史去重完整。")
    write_artifact(OUT / "sources/inventory.md", "\n".join(lines) + "\n")

    vlines = ["# 已用词表（自动生成，勿手改）", "",
              f"工作树 HEAD：`{head}`。只统计 `text`/`vocab` 范围来源。", "",
              "分桶只表示「在该位置观察到」，排除判定用并集：任一分桶命中即算已用。", "",
              f"并集规模：{exclusion['vocabUnionCount']} 项。", ""]
    for bucket, title in (("characters", "人物与视角"), ("locations", "地点"),
                          ("tasks", "任务目标"), ("items", "物品与可见物"),
                          ("other", "其他内容值"), ("protocolIds", "协议实体 ID")):
        items = vocab_all[bucket]
        vlines += [f"## {title}（{len(items)} 个不同值）", "",
                   "| 值 | 来源 |", "|---|---|"]
        for v, d in sorted(items.items(), key=lambda kv: (len(kv[0]), kv[0]))[:600]:
            vlines.append(f"| {v} | {', '.join(d['sources'])} |")
        if len(items) > 600:
            vlines.append(f"| … | 其余 {len(items) - 600} 项见 `vocab-used.json` |")
        vlines.append("")
    write_artifact(OUT / "sources/vocab-used.md", "\n".join(vlines).rstrip() + "\n")

    print(f"head={head[:12]} sources={len(inv['sources'])} "
          f"files={sum(len(s['files']) for s in inv['sources'])} "
          f"blockedUnique={len(blocked)} "
          + " ".join(f"{b}={len(v)}" for b, v in vocab_all.items()))
    if missing:
        print("MISSING SOURCES:", missing)
    return 0


def git_head() -> str:
    try:
        return subprocess.run(["git", "-c", f"safe.directory={REPO.as_posix()}",
                               "-C", str(REPO), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


if __name__ == "__main__":
    sys.exit(main())
