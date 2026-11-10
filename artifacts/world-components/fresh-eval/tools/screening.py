"""Shared screening rules for the C8 fresh-eval work (single implementation).

Used by:
  tools/build_inventory.py     writes the ten three-arm signatures
  tools/exclusion_selftest.py  proves the rules reject the old material
  tools/build_diagnostics.py   screens the diagnostic fixtures

Two R1 versions are kept side by side. v1 is the rule that existed when the
candidates were first screened; v2 is the directional rule written after that
screening, so v2 must never be used to justify v2's own result. Both versions
share the time normalization (R3 keeps it in both).

R1 v1 (original)
  candidate text (>=4 CJK) vs every excluded string, any direction of
  containment counts; parentheses-stripped variants of the source are also
  tested.
R1 v2 (post-hoc, directional)
    exact equality                     -> hit
    candidate inside an exclusion      -> hit (the candidate is a fragment)
    exclusion inside the candidate     -> hit only when that exclusion has
                                          >= MIN_HIT_CJK=8 CJK chars; shorter
                                          ones become `R1-short-phrase` notes
  Reason: a 5-char goal taken from a registered fixture sits inside every
  sentence that names that goal, so v1 rejected candidates for reusing their
  own approved source.

R2 vocabulary  candidate terms vs the used-vocabulary union; the caller decides
               whether a hit blocks (formal item) or is only recorded
               (source-bound diagnostic).
R3 signature   (change kinds with counts | distinct change actors | seconds)
               equal to one of the ten three-arm signatures. The map value is a
               LIST of every item id sharing that signature (never a single id:
               nv-empty-1 and nv-cont-3 share one), and a match is reported with
               the basis of the old item (authoritative read vs undetermined).

Fact provenance rule: only facts produced by this point's raw delta count as
*changes*. Standing readings of untouched entities (`at`, plain `sanity`) are
references and are excluded from the signature, so a candidate cannot dodge an
old signature by adding more standing items.
"""

from __future__ import annotations

import json
import pathlib
import re
from collections import Counter

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent
CJK = re.compile(r"[\u4e00-\u9fff]")
NOTE = re.compile(r"（[^）]*）")

UNIT_SECONDS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400,
                "month": 2592000, "year": 31536000}
MIN_HIT_CJK = 8
CHANGE_KINDS = {"moved", "task_achieved", "personality_changed", "sanity_changed"}
STANDING_KINDS = {"at", "sanity"}


def load_sources():
    corpus = {}
    for line in (OUT / "sources/exclusion-corpus.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        corpus[row["text"]] = row["sources"]
    vocab_doc = json.loads((OUT / "sources/vocab-used.json").read_text(encoding="utf-8"))
    vocab = set()
    for terms in vocab_doc["buckets"].values():
        vocab.update(terms)
    scope = json.loads((OUT / "sources/exclusion-scope.json").read_text(encoding="utf-8"))
    return corpus, vocab, scope


def cjk_len(text: str) -> int:
    return len(CJK.findall(text))


def norm_variants(text: str) -> list[str]:
    """Source string plus its parentheses-stripped core (nv-cont-1 lesson)."""
    out = [text]
    if NOTE.search(text):
        core = NOTE.sub("", text).strip()
        if cjk_len(core) >= 4:
            out.append(core)
    return out


def norm_seconds(amount, unit):
    if amount is None or unit not in UNIT_SECONDS:
        return None
    return int(amount) * UNIT_SECONDS[unit]


# ----------------------------------------------------------------- R1 -----
def r1_hits(texts, corpus, version="v2"):
    hits, short = [], []
    for t in texts:
        if cjk_len(t) < 4:
            continue
        for src, sources in corpus.items():
            matched = False
            for variant in norm_variants(src):
                if version == "v1":
                    if variant == t or t in variant or variant in t:
                        hits.append({"candidateText": t, "excluded": src,
                                     "sources": sources, "direction": "any"})
                        matched = True
                elif variant == t:
                    hits.append({"candidateText": t, "excluded": src,
                                 "sources": sources, "direction": "equal"})
                    matched = True
                elif t in variant:
                    hits.append({"candidateText": t, "excluded": src,
                                 "sources": sources, "direction": "candidate-inside-exclusion"})
                    matched = True
                elif variant in t:
                    record = {"candidateText": t, "excluded": src,
                              "sources": sources, "direction": "exclusion-inside-candidate",
                              "shorterCjk": cjk_len(variant)}
                    (hits if cjk_len(variant) >= MIN_HIT_CJK else short).append(record)
                    matched = True
                if matched:
                    break
            if matched:
                break
    return hits, short


# ------------------------------------------------------------ signature ---
def _phase(fact):
    return fact.get("phase") or ("change" if fact["kind"] in CHANGE_KINDS else "standing")


def _actor(fact):
    return fact.get("actor") or fact.get("actorId")


def _sig(facts):
    counts = Counter(f["kind"] for f in facts)
    actors = {_actor(f) for f in facts if _actor(f)}
    return counts, actors


def _fmt(counts, actors, secs):
    kinds = "+".join(f"{k}*{n}" for k, n in sorted(counts.items())) or "none"
    return f"{kinds}|{len(actors)}|{secs}s"


def change_signature(facts, time) -> str:
    changes = [f for f in facts or [] if _phase(f) == "change"]
    counts, actors = _sig(changes)
    return _fmt(counts, actors, norm_seconds((time or {}).get("amount"),
                                             (time or {}).get("unit")))


def full_signature(facts, time) -> str:
    counts, actors = _sig(facts or [])
    return _fmt(counts, actors, norm_seconds((time or {}).get("amount"),
                                             (time or {}).get("unit")))


def change_signature_of(cand: dict) -> str:
    return change_signature(cand.get("facts"), cand.get("time"))


def signature_of(cand: dict) -> str:
    """Full-packet signature (kept for backwards compatibility / reference)."""
    return full_signature(cand.get("facts"), cand.get("time"))


# --------------------------------------------------------------- screen ---
def _owners(signatures: dict, sig: str) -> list:
    owners = signatures.get(sig)
    if owners is None:
        return []
    if isinstance(owners, str):
        return [owners]
    return list(owners)


def screen(cand: dict, corpus: dict, vocab: set, signatures: dict,
           mode: str = "new-world", r1_version: str = "v2",
           basis: dict | None = None) -> dict:
    """mode: new-world -> vocabulary hit blocks;
             source-bound -> vocabulary hit is recorded only."""
    reasons, warnings = [], []
    hits, short = r1_hits([t for t in cand.get("texts", [])], corpus, r1_version)
    if hits:
        reasons.append({"rule": "R1-substring", "r1Version": r1_version,
                        "hits": hits[:5], "hitCount": len(hits)})
    if short:
        warnings.append({"rule": "R1-short-phrase", "hits": short[:5],
                         "hitCount": len(short),
                         "note": f"较短一侧不足 {MIN_HIT_CJK} 个汉字，只登记不判失败"})

    terms, overlaps = [], []
    for key in ("characters", "locations", "tasks", "items", "terms"):
        for v in cand.get(key, []) or []:
            if str(v) in vocab:
                (overlaps if mode == "source-bound" else terms).append(
                    {"term": str(v), "field": key})
    if terms:
        reasons.append({"rule": "R2-vocabulary", "hits": terms})
    if overlaps:
        warnings.append({"rule": "R2-registered-overlap", "hits": overlaps,
                         "note": "source-bound：复用已登记来源的名字，记录范围，不表示独立"})

    sig = change_signature_of(cand)
    owners = _owners(signatures, sig)
    if owners:
        reason = {"rule": "R3-signature", "signature": sig, "matches": owners}
        if basis is not None:
            reason["matchBasis"] = {i: basis.get(i, "unknown") for i in owners}
        reasons.append(reason)
    verdict = "rejected" if reasons else (
        "source-bound" if mode == "source-bound" else "candidate")
    return {"id": cand.get("id"), "verdict": verdict, "signature": sig,
            "fullSignature": signature_of(cand), "mode": mode,
            "r1Version": r1_version, "reasons": reasons, "warnings": warnings}


def screen_both(cand: dict, corpus: dict, vocab: set, signatures: dict,
                mode: str = "source-bound", basis: dict | None = None) -> dict:
    """Run v1 and v2 on the same candidate and record the difference."""
    v1 = screen(cand, corpus, vocab, signatures, mode=mode, r1_version="v1",
                basis=basis)
    v2 = screen(cand, corpus, vocab, signatures, mode=mode, r1_version="v2",
                basis=basis)
    return {"v1": v1, "v2": v2,
            "differs": v1["verdict"] != v2["verdict"],
            "v1Reasons": [r["rule"] for r in v1["reasons"]],
            "v2Reasons": [r["rule"] for r in v2["reasons"]]}


# ---------------------------------------------------------- io helpers ----
def normalize_lf(root=None) -> int:
    root = pathlib.Path(root) if root else OUT
    changed = 0
    crlf = bytes((13, 10))
    for path in root.rglob("*"):
        if path.is_file() and path.suffix in (".json", ".md", ".jsonl", ".py", ".log"):
            data = path.read_bytes()
            if crlf in data:
                path.write_bytes(data.replace(crlf, bytes((10,))))
                changed += 1
    return changed


def write_artifact(path, text) -> None:
    """Write a generated artefact, keeping the file's existing line endings.

    `.gitattributes` here pins `* -text`, so the committed bytes are part of the
    record. Regenerating must not silently rewrite every line of every file: a
    file that already uses CRLF keeps CRLF, a new file gets LF.
    """
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    crlf = bytes((13, 10))
    if path.exists() and crlf in path.read_bytes():
        data = data.replace(bytes((10,)), crlf)
    path.write_bytes(data)
