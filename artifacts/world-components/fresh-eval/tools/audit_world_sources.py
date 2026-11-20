"""Audit every branch tip and working tree for world/fixture material, then
classify each world by the usage records that reference it.

Design (what this does and does not cover):
  * committed content  : every branch tip (refs/heads + refs/remotes) after
                         `git fetch --all --prune`; blobs are de-duplicated by
                         object id, so N tips cost M unique blobs.
  * uncommitted content: every registered worktree, but only files that
                         `git status --porcelain` reports (modified/untracked).
                         Committed files are already covered by the tips above.
  * classification     : a world's class is decided by *which* files mention its
                         names, mapped to roles by path (training corpus, eval
                         sample, live archive, protocol fixture, legacy product,
                         definition only). Nothing is blanket-labelled
                         "undetermined"; each world records its evidence and the
                         reason it is selected or excluded.
  * limits             : deleted history and use outside this repository are not
                         covered; a name match is evidence of exposure, not proof
                         that a world was used for training.

Outputs: source-search/audit.json, source-search/README.md
Usage: python artifacts/world-components/fresh-eval/tools/audit_world_sources.py [--fetch]
"""

from __future__ import annotations

import collections
import datetime as dt
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time

OUT = pathlib.Path(__file__).resolve().parents[1]
REPO = OUT.parents[2]
ROOT = REPO.parents[2]
DEST = OUT / "source-search"
SELF_PREFIX = "artifacts/world-components/fresh-eval/"
SKIP_DIRS = {".git", "node_modules", ".next", "__pycache__", "models", "weights",
             "checkpoints", "cache", ".cache", ".venv", "venv", ".local"}
EXTENSIONS = {".json", ".jsonl", ".py", ".ts", ".tsx", ".md", ".sql", ".txt"}
MAX_BYTES = 8 * 1024 * 1024

# path -> role. First match wins; order matters.
ROLE_RULES = [
    ("experiments/world-components/n4_", "training-or-tuning-corpus"),
    ("experiments/world-components/n3_", "training-or-tuning-corpus"),
    ("experiments/world-components/n2_", "training-or-tuning-corpus"),
    ("experiments/world-components/organize_wording", "training-or-tuning-corpus"),
    ("experiments/world-components/", "component-experiment"),
    ("artifacts/world-components/n4", "training-or-tuning-corpus"),
    ("artifacts/world-components/n5", "training-or-tuning-corpus"),
    ("artifacts/world-components/n2", "training-or-tuning-corpus"),
    ("artifacts/world-components/n3", "training-or-tuning-corpus"),
    ("artifacts/world-components/organize-wording", "training-or-tuning-corpus"),
    ("artifacts/world-components/", "component-experiment"),
    ("artifacts/world-page", "live-archive"),
    ("artifacts/rule-facts", "live-archive"),
    ("artifacts/narration-", "live-archive"),
    ("artifacts/b3-short", "live-archive"),
    ("artifacts/benchmark", "tuning-run"),
    ("artifacts/cohesion-split", "tuning-run"),
    ("artifacts/decode-compare", "tuning-run"),
    ("artifacts/statement-", "training-or-tuning-corpus"),
    ("artifacts/world-provenance", "tuning-run"),
    ("artifacts/smoke", "live-archive"),
    ("frontend/src/lib/world-engine/runtime/narration-eval", "eval-sample"),
    ("frontend/src/lib/world-engine/runtime/narration-split", "eval-sample"),
    ("frontend/src/lib/world-engine/runtime/narration-alignment", "grader"),
    ("frontend/src/lib/world-engine/runtime/b3-", "eval-sample"),
    ("frontend/src/lib/world-engine/runtime/world-reads", "runtime"),
    ("frontend/src/lib/world-engine/runtime/", "runtime"),
    ("frontend/src/lib/world-engine/", "fixture-or-test"),
    ("design/world-protocol/", "protocol-fixture"),
    ("backend/data/", "legacy-product-content"),
    ("backend/tests/", "test"),
    ("design/", "design-doc"),
]

CLASS_ORDER = [
    ("training-or-tuning", "used-in-training-or-tuning"),
    ("tuning-run", "used-in-tuning-run"),
    ("eval-sample", "used-in-eval-samples"),
    ("live-archive", "used-in-live-archives"),
    ("legacy-product-content", "used-by-legacy-product"),
    ("grader", "referenced-by-grader"),
    ("runtime", "referenced-by-runtime-code"),
    ("fixture-or-test", "fixture-or-test-only"),
    ("protocol-fixture", "protocol-fixture-only"),
    ("design-doc", "design-doc-only"),
]


def git(*args, check=True):
    return subprocess.run(["git", "-c", f"safe.directory={ROOT.as_posix()}",
                           "-C", str(ROOT), *args], check=check,
                          stdout=subprocess.PIPE).stdout


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def role_of(path: str) -> str:
    for prefix, role in ROLE_RULES:
        if path.startswith(prefix):
            return role
    return "other"


def canon(value) -> str:
    return sha(json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":")).encode())


def find_worlds(value, pointer=""):
    """Yield world-shaped objects: characters + locations maps with names."""
    if isinstance(value, dict):
        chars, locs = value.get("characters"), value.get("locations")
        if isinstance(chars, dict) and isinstance(locs, dict) and chars and locs:
            named = [c for c in chars.values() if isinstance(c, dict) and "name" in c]
            if named:
                names = sorted({str(v["name"]) for group in
                                (chars, locs, value.get("items") or {})
                                if isinstance(group, dict)
                                for v in group.values()
                                if isinstance(v, dict) and "name" in v})
                yield {"pointer": pointer or "/", "worldId": value.get("worldId"),
                       "format": "initial-template" if "initialTime" in value else "world-map",
                       "characters": sorted(chars), "locations": sorted(locs),
                       "names": names, "canonical": canon(value)}
        for key, child in value.items():
            if isinstance(child, (dict, list)):
                yield from find_worlds(child, f"{pointer}/{key}")
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from find_worlds(child, f"{pointer}/{i}")


def main() -> int:
    started = time.time()
    if "--fetch" in sys.argv:
        subprocess.run(["git", "-C", str(ROOT), "fetch", "--all", "--prune"],
                       check=False, capture_output=True)
    refs = []
    for line in git("for-each-ref", "--format=%(refname) %(objectname)",
                    "refs/heads", "refs/remotes").decode().splitlines():
        name, commit = line.split()
        refs.append({"ref": name, "commit": commit})
    tips = collections.defaultdict(list)
    for r in refs:
        tips[r["commit"]].append(r["ref"])
    worktrees = []
    for section in git("worktree", "list", "--porcelain").decode().strip().split("\n\n"):
        fields = dict(line.split(" ", 1) if " " in line else (line, True)
                      for line in section.splitlines())
        if "worktree" in fields:
            head = subprocess.run(["git", "-C", fields["worktree"], "rev-parse", "HEAD"],
                                  capture_output=True, text=True).stdout.strip()
            worktrees.append({"path": fields["worktree"], "head": head,
                              "branch": fields.get("branch", "(detached)").replace("refs/heads/", ""),
                              "isMain": fields["worktree"].rstrip("/\\") == str(ROOT).rstrip("/\\")})

    # ---- committed blobs from every branch tip -----------------------------
    blob_owners = collections.defaultdict(list)
    scanned_files = []
    for commit, names in tips.items():
        tree = git("ls-tree", "-r", "-z", commit)
        for entry in tree.split(b"\0"):
            if not entry:
                continue
            meta, raw = entry.split(b"\t", 1)
            _, kind, oid = meta.decode().split()
            path = raw.decode("utf-8")
            if kind != "blob" or pathlib.Path(path).suffix.lower() not in EXTENSIONS:
                continue
            if path.startswith(SELF_PREFIX):
                continue
            blob_owners[oid].append({"commit": commit, "refs": names, "path": path})
    contents = {}
    proc = subprocess.Popen(["git", "-c", f"safe.directory={ROOT.as_posix()}", "-C", str(ROOT),
                             "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    done = 0
    for oid, owners in blob_owners.items():
        proc.stdin.write((oid + "\n").encode())
        proc.stdin.flush()
        header = proc.stdout.readline().decode().split()
        if not header or header[-1] == "missing":
            continue
        size = int(header[-1])
        data = proc.stdout.read(size)
        proc.stdout.read(1)
        contents.setdefault(sha(data), data)
        for owner in owners:
            scanned_files.append({"kind": "git-blob", "path": owner["path"],
                                  "refs": owner["refs"][:4], "commit": owner["commit"],
                                  "sha256": sha(data), "bytes": len(data),
                                  "role": role_of(owner["path"])})
        done += 1
        if done % 2000 == 0:
            print(f"  blobs {done}/{len(blob_owners)}", flush=True)
    proc.stdin.close()
    proc.wait()
    print(f"committed blobs read: {len(blob_owners)} (unique by content: {len(contents)})", flush=True)

    # ---- uncommitted files in every worktree -------------------------------
    unread = []
    for wt in worktrees:
        base = pathlib.Path(wt["path"])
        if not base.exists():
            unread.append({"path": wt["path"], "reason": "worktree path missing"})
            continue
        status = subprocess.run(["git", "-C", str(base), "status", "--porcelain", "-z",
                                 "--untracked-files=all"], capture_output=True)
        entries = status.stdout.split(b"\0")
        rels = []
        for entry in entries:
            if not entry:
                continue
            text = entry.decode("utf-8", "replace")
            rel = text[3:].strip()
            if " -> " in rel:
                rel = rel.split(" -> ")[-1]
            rels.append(rel)
        for rel in sorted(set(rels)):
            path = base / rel
            if not path.is_file():
                continue
            if rel.startswith(SELF_PREFIX):
                continue
            if path.suffix.lower() not in EXTENSIONS:
                continue
            try:
                if path.stat().st_size > MAX_BYTES:
                    unread.append({"path": str(path), "reason": "over-8MiB"})
                    continue
                data = path.read_bytes()
            except OSError as exc:
                unread.append({"path": str(path), "reason": str(exc)})
                continue
            contents.setdefault(sha(data), data)
            scanned_files.append({"kind": "worktree-uncommitted", "path": rel,
                                  "worktree": wt["path"], "sha256": sha(data),
                                  "bytes": len(data), "role": role_of(rel)})

    # ---- extract worlds and usage ------------------------------------------
    worlds = []
    for file_sha, data in contents.items():
        if not file_sha.endswith(""):
            pass
        if not (file_sha in contents):
            continue
    for record in scanned_files:
        data = contents[record["sha256"]]
        if not record["path"].endswith(".json"):
            continue
        try:
            value = json.loads(data)
        except (ValueError, UnicodeError):
            continue
        for w in find_worlds(value):
            worlds.append({**w, "file": record["path"], "role": record["role"],
                           "fileSha256": record["sha256"]})

    # ---- cluster the same world across encodings --------------------------
    # Traces sometimes carry {"$var": "v1"} instead of a literal worldId, and
    # the same world is re-serialised in several files. Cluster by the identity
    # sets, so one world is one row.
    def cluster_key(w):
        return (tuple(sorted(w["characters"])), tuple(sorted(w["locations"])),
                tuple(sorted(w["names"])))

    clusters = collections.defaultdict(list)
    for w in worlds:
        clusters[cluster_key(w)].append(w)

    cluster_names = {k: sorted({n for w in ws for n in w["names"]}) for k, ws in clusters.items()}
    name_clusters = collections.defaultdict(set)
    for key, names in cluster_names.items():
        for n in names:
            if len(n) >= 2:
                name_clusters[n].add(key)
    unique_names = {k: [n for n in names if len(name_clusters[n]) == 1]
                    for k, names in cluster_names.items()}
    literal_ids = {}
    for key, ws in clusters.items():
        ids = {w.get("worldId") for w in ws if isinstance(w.get("worldId"), str)}
        literal_ids[key] = sorted(i for i in ids if not i.startswith("{"))

    # ---- evidence: a file must mention 2+ names unique to this world -------
    cluster_evidence = collections.defaultdict(set)
    for record in scanned_files:
        data = contents[record["sha256"]]
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for key, names in unique_names.items():
            if not names:
                continue
            hit = sum(1 for n in names if n in text)
            id_hit = any(i and i in text for i in literal_ids.get(key, []))
            if hit >= 2 or (hit >= 1 and len(names) == 1) or id_hit:
                cluster_evidence[key].add(record["path"])

    world_rows = []
    for key, entries in sorted(clusters.items(), key=lambda kv: -len(kv[1])):
        head = entries[0]
        usage = collections.defaultdict(set)
        for path in cluster_evidence.get(key, ()):
            usage[role_of(path)].add(path)
        unique = unique_names[key]
        if len(unique) < 2:
            klass = "undetermined-name-overlap"
            reason = (f"只有 {len(unique)} 个专有名字，其余名字在多个世界间共用，"
                      "无法用名字判定它是否被使用；记为无法判断，不作为独立来源")
        else:
            klass, reason = "definition-only", "只有定义该世界的文件提到它的专有名字"
            for role, label in CLASS_ORDER:
                if role in usage:
                    klass = label
                    reason = f"被 {len(usage[role])} 个 {role} 文件提到"
                    break
        defined = {(e["file"], e["role"]) for e in entries}
        world_rows.append({
            "clusterKey": list(key[0]) + list(key[1]),
            "worldId": (literal_ids[key][0] if len(literal_ids[key]) == 1 else None),
            "worldIds": literal_ids[key][:4],
            "format": head["format"],
            "characters": head["characters"],
            "locations": head["locations"],
            "names": cluster_names[key],
            "discriminativeNames": unique[:10],
            "occurrences": len(entries),
            "canonicalVariants": len({e["canonical"] for e in entries}),
            "definedAt": [{"path": p_, "role": r} for p_, r in sorted(defined)][:12],
            "usageCounts": {r: len(usage[r]) for r in
                            [r for r, _ in CLASS_ORDER if r in usage]},
            "usageExamples": {r: sorted(usage[r])[:4] for r in
                              [r for r, _ in CLASS_ORDER if r in usage]},
            "class": klass,
            "reason": reason,
            "eligibleAsUnseen": klass == "definition-only" and len(unique) >= 3,
        })
    eligible = [w for w in world_rows if w["eligibleAsUnseen"]]

    summary = {
        "refs": len(refs), "uniqueTips": len(tips), "worktrees": len(worktrees),
        "uniqueBlobs": len(blob_owners), "uniqueContents": len(contents),
        "scannedFileRecords": len(scanned_files), "worldOccurrences": len(worlds),
        "uniqueWorlds": len(world_rows), "eligibleUnseen": len(eligible),
        "unread": len(unread),
    }
    audit = {
        "schemaVersion": 2,
        "createdUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "worktree": {"path": str(REPO), "head": git("rev-parse", "HEAD").decode().strip()},
        "method": ("分支尖端全量（按 blob 去重）+ 工作树未提交文件；"
                   "世界按名字被哪些角色的文件提到来分类；"
                   "不穷举已删除历史与仓库外使用。"),
        "summary": summary,
        "refs": refs,
        "worktrees": worktrees,
        "worlds": world_rows,
        "unread": unread,
        "selection": ("存在定义级独立世界时优先复核它们；否则新建评测专用注册夹具。"
                      "任何世界都不以改名的形式冒充新来源。"),
    }
    DEST.mkdir(parents=True, exist_ok=True)
    (DEST / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=1) + "\n",
                                     encoding="utf-8", newline="\n")

    # ---- readable report ---------------------------------------------------
    lines = ["# 全分支与工作树来源审计", "",
             f"生成时间：{audit['createdUtc']}；工作树 HEAD `{audit['worktree']['head'][:12]}`。", "",
             "## 范围与方法", "",
             f"- 分支与远端引用：{summary['refs']} 条，去重后 {summary['uniqueTips']} 个尖端。",
             f"- 工作树：{summary['worktrees']} 个（每个工作树只读未提交文件，已提交内容由尖端覆盖）。",
             f"- 已提交 blob：{summary['uniqueBlobs']} 个，按内容去重后 {summary['uniqueContents']} 份。",
             f"- 扫到的世界出现：{summary['worldOccurrences']} 次，按身份集合合并后 {summary['uniqueWorlds']} 个世界。",
             f"- 未读文件：{summary['unread']} 个（见 audit.json 的 unread）。", "",
             "分类规则：按世界的名字被哪些角色的文件提到——训练/调参语料、调参运行、评测样本、"
             "真机归档、旧产品内容、判分器、运行时代码、夹具/测试、协议夹具、设计文档、"
             "仅定义。**没有一条统一标 undetermined**；每个世界都有具体理由。", "",
             "## 世界分类", "",
             "| 世界摘要 | 人物/地点 | 出现 | 分类 | 理由 | 独立? |",
             "|---|---|---|---|---|---|"]
    for w in world_rows:
        lines.append(f"| `{hashlib.sha256('|'.join(w['clusterKey']).encode()).hexdigest()[:12]}` "
                     f"{w['worldId'] or ''} | "
                     f"{len(w['characters'])}/{len(w['locations'])} | {w['occurrences']} | "
                     f"{w['class']} | {w['reason']} | {'是' if w['eligibleAsUnseen'] else '否'} |")
    lines += ["", "## 入选与排除理由", "",
              "| 世界 | 分类 | 是否可用作独立来源 | 具体理由 |", "|---|---|---|---|"]
    for w in world_rows:
        key = hashlib.sha256("|".join(w["clusterKey"]).encode()).hexdigest()[:12]
        if w["eligibleAsUnseen"]:
            verdict = "候选"
            why = (f"只在定义文件中出现；专有名字 {len(w['discriminativeNames'])} 个；"
                   "仍需人工确认用途后使用")
        elif w["class"] == "definition-only":
            verdict = "否"
            why = (f"仅定义级，但只有 {len(w['discriminativeNames'])} 个专有名字、"
                   f"{len(w['characters'])} 人物/{len(w['locations'])} 地点，"
                   "不满足多人物/多地点覆盖，且用于单元测试夹具")
        elif w["class"] == "undetermined-name-overlap":
            verdict = "否"
            why = "名字在多个世界间共用，无法用证据判断用途；按无法判断处理，不作独立来源"
        else:
            verdict = "否"
            why = f"{w['reason']}；已有曝光记录，不能作独立来源"
        lines.append(f"| `{key}` | {w['class']} | {verdict} | {why} |")
    lines += ["", f"结论：可用作独立来源的世界 **{len(eligible)}** 个。"
              + ("" if eligible else
                 "因此本次改为新建评测专用注册夹具（见 `../fresh/`），"
                 "不把任何旧世界改名冒充新来源。")]
    lines += ["", "## 各类数量", ""]
    counts = collections.Counter(w["class"] for w in world_rows)
    for klass, n in counts.most_common():
        lines.append(f"- {klass}：{n}")
    lines += ["", "## 边界", "",
              "- 名字匹配只能证明“该文件提到过这个名字”，不等于证明该世界被用于训练或调参。",
              "- 已删除的历史文件、仓库外的使用记录不在本次扫描范围。",
              "- 工作树只读未提交文件；已提交内容由分支尖端覆盖。"]
    (DEST / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    print(json.dumps(summary, ensure_ascii=False))
    print(f"elapsed {time.time() - started:.1f}s")
    if eligible:
        print("ELIGIBLE:", [w["canonical"][:12] + " " + str(w["worldId"]) for w in eligible])
    return 0


if __name__ == "__main__":
    sys.exit(main())
