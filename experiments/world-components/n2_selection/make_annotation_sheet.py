# Build the BLIND annotation sheet for the N2 v3 independent labeling (D1).
#
# The sheet strips every label-bearing field (must/target/omittable/forbidden,
# the construction note, and label hashes) so the two annotators see only the
# viewpoint and the facts. Run before anyone labels. The rubric is hashed
# here; label files present at generation time are hashed too (the
# implementer's file is committed, the reviewer must label before opening it).
#
# Usage: python experiments/world-components/n2_selection/make_annotation_sheet.py
# Output: experiments/world-components/n2_selection/annotation/
#           items-blind.jsonl, sheet.md, labels-template.jsonl, manifest.json

import datetime
import hashlib
import json
import pathlib
import subprocess

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
ITEMS = HERE / "items.jsonl"
OUT = HERE / "annotation"
RUBRIC = REPO / "design" / "world-engine-reports" / "components" / "n2-annotation-rubric.md"
KEEP_FACT_KEYS = ("factId", "kind", "entityId", "name", "from", "to", "goal",
                  "text", "amount", "unit", "scope", "at")


def sha_file(p) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO,
                                       text=True).strip()
    except Exception:
        return "unknown"


def blind_item(item: dict) -> dict:
    v = item["viewpoint"]
    return {
        "itemId": item["itemId"],
        "viewpoint": {k: v.get(k) for k in ("type", "entityId", "name", "at", "rule")},
        "facts": [{k: f[k] for k in KEEP_FACT_KEYS if k in f} for f in item["facts"]],
    }


def fact_text(f: dict) -> str:
    k = f["kind"]
    if k == "moved":
        return f"{f['from']} → {f['to']}（{f['name']}）"
    if k == "task_achieved":
        return f"任务达成：{f['name']}「{f['goal']}」"
    if k == "personality_changed":
        return f"{f['name']} {f['text']}"
    if k == "sanity_changed":
        return f"{f['name']} {f['from']}→{f['to']}"
    if k == "appearance_changed":
        return f"{f['name']} {f['text']}"
    if k == "positioned_at":
        return f"{f['name']} 已在 {f['at']}"
    if k == "time":
        return f"约 {f['amount']} {f['unit']}"
    if k == "no_change":
        return f"无变化：{f.get('scope') or f.get('at')}"
    return json.dumps(f, ensure_ascii=False)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    items = [json.loads(line) for line in
             ITEMS.read_text(encoding="utf-8").splitlines() if line.strip()]
    blind = [blind_item(it) for it in items]

    blind_path = OUT / "items-blind.jsonl"
    blind_text = "\n".join(json.dumps(x, ensure_ascii=False) for x in blind) + "\n"
    blind_path.write_text(blind_text, encoding="utf-8")

    template = [{"itemId": it["itemId"], "factId": f["factId"], "label": "", "note": ""}
                for it in items for f in it["facts"]]
    template_text = "\n".join(json.dumps(x, ensure_ascii=False) for x in template) + "\n"
    (OUT / "labels-template.jsonl").write_text(template_text, encoding="utf-8")

    lines = ["# N2 v3 盲标表（92 条事实）", "",
             f"Rubric：`{RUBRIC.relative_to(REPO)}`（哈希见 `manifest.json`）", "",
             "只按 rubric 标 `must` / `omit` / `may`；不要把本表与 `items.jsonl` 的标签对照。", ""]
    for it in blind:
        v = it["viewpoint"]
        who = f"{v.get('name') or '全知'}（{v.get('entityId') or '—'}）"
        lines.append(f"## {it['itemId']} · {v['type']} · {who} @ {v.get('at') or '全局'}")
        lines.append("")
        lines.append(f"规则：{v.get('rule') or '（全知：全部可见）'}")
        lines.append("")
        lines.append("| factId | kind | 主体 | 地点 | 内容 | 标签 |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for f in it["facts"]:
            subject = (f"{f.get('name')}（{f.get('entityId')}）"
                       if f.get("entityId") else "—")
            lines.append(f"| {f['factId']} | {f['kind']} | {subject} | "
                         f"{f.get('at') or '全局'} | {fact_text(f)} |  |")
        lines.append("")
    (OUT / "sheet.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    label_files = {}
    for p in sorted(OUT.glob("labels-*.jsonl")):
        if p.name == "labels-template.jsonl":
            continue
        label_files[p.name] = sha_file(p)

    manifest = {
        "purpose": "N2 v3 blind annotation package (D1); hashes registered before labeling",
        "rubric": {"file": str(RUBRIC.relative_to(REPO)), "sha256": sha_file(RUBRIC)},
        "blindItems": {"file": "items-blind.jsonl", "sha256": sha_file(blind_path)},
        "sheet": {"file": "sheet.md", "sha256": sha_file(OUT / "sheet.md")},
        "template": {"file": "labels-template.jsonl", "sha256": sha_file(OUT / "labels-template.jsonl")},
        "facts": len(template),
        "items": len(blind),
        "labelFilesPresentAtGeneration": label_files,
        "blindness": {
            "strippedFromItems": ["must", "target", "omittable", "forbidden",
                                  "note", "hashes"],
            "annotatorsMustNotRead": ["items.jsonl labels", "run_n2.py outputs",
                                      "n3_plan.py outputs",
                                      "the other annotator's label file before finishing"],
            "implementerExposure": ("the C implementer saw v2 labels and aggregate arm "
                                     "outputs during the repair; the reviewer must be blind"),
        },
        "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "generatedFromCommit": git_commit(),
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(blind)} blind items / {len(template)} facts -> {OUT}")
    print(f"rubric sha256 {manifest['rubric']['sha256']}")


if __name__ == "__main__":
    main()
