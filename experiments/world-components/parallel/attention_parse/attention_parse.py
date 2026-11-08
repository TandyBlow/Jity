"""Fixed surface-rule baseline for "player utterance -> attention objects".

Contract
--------
Input per sample: the raw player utterance, an optional previous narration
(the last committed narration the player saw) and a roster of objects that
exist in the committed world state (entityId / kind / name / descriptor).

Output: `status` in {resolved, ambiguous, unresolved, none} plus
`attentionTargets` (only non-empty when status == resolved),
`resolvedCandidates`, `ambiguousCandidates`, `unresolvedMentions` and the
surface match trace. The extractor NEVER falls back to the full roster:
no match means an empty target list.

The rule is fixed before the run and does not learn, call a model, or touch
N2's selection rule. Each mechanism is deliberately small:

  M1 exact name / task-goal match           (longest match wins)
  M2 shared name stem -> ambiguity group    (>=2 names share a >=2 char stem)
  M3 descriptor match from committed text   (longest common substring, unique)
  M4 pronoun resolution from prior narration (exactly one antecedent only)
  M5 nickname pattern left unmatched        -> unresolved mention
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

SELF_PRONOUNS = ["我自己", "自己", "我"]
PERSON_PRONOUNS_PLURAL = ["他们", "她们", "它们"]
PERSON_PRONOUNS = ["他", "她", "它"]
PLACE_PRONOUNS = ["这里", "这儿", "那里", "那儿", "那边", "这边"]

FUNCTION_CHARS = set(
    "的了着过吗呢吧啊呀还在是和与及就也都很更又再才只不没我你他她它们这那哪个么什怎为所把被给让对从到向往于以而"
)
# Nickname pattern: 老/小/阿 + exactly one character (e.g. 老林, 小周, 阿宁).
# Longer nicknames (老林头) are NOT covered in this round — declared limitation.
NICKNAME_RE = re.compile(r"(?:老|小|阿)[\u4e00-\u9fa5]")
CLAUSE_SPLIT_RE = re.compile(r"[，。、；！？,.;:：\s]+")


@dataclass
class Match:
    entity_id: str
    surface: str
    start: int
    end: int
    via: str
    note: str = ""

    def span(self) -> tuple[int, int]:
        return self.start, self.end


@dataclass
class Parsed:
    status: str
    attention_targets: list[str]
    resolved_candidates: list[str]
    ambiguous_candidates: list[str]
    ambiguous_groups: list[list[str]]
    unresolved_mentions: list[str]
    matches: list[dict] = field(default_factory=list)
    non_unique_descriptors: list[dict] = field(default_factory=list)
    dropped_descriptors: list[dict] = field(default_factory=list)


def _is_functionish(text: str) -> bool:
    return bool(text) and all(ch in FUNCTION_CHARS for ch in text)


def longest_common_substring(a: str, b: str) -> str:
    """Longest common substring; ties resolved by earliest position in `a`."""
    if not a or not b:
        return ""
    best_len = 0
    best_end = 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            if ai == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best_len:
                    best_len = cur[j]
                    best_end = i
        prev = cur
    return a[best_end - best_len : best_end]


def _find_all(text: str, needle: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    while needle:
        index = text.find(needle, start)
        if index < 0:
            break
        spans.append((index, index + len(needle)))
        start = index + 1
    return spans


def _entities_by_name(roster: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for entity in roster["entities"]:
        out.setdefault(entity["name"], []).append(entity)
    return out


def name_matches(text: str, roster: dict) -> tuple[list[Match], list[list[str]]]:
    """M1 + duplicate full names. Returns matches and ambiguous name groups."""
    matches: list[Match] = []
    groups: list[list[str]] = []
    for name, entities in _entities_by_name(roster).items():
        spans = _find_all(text, name)
        if not spans:
            continue
        ids = [e["entityId"] for e in entities]
        if len(ids) > 1:
            groups.append(ids)
        for start, end in spans:
            for entity in entities:
                matches.append(
                    Match(entity["entityId"], name, start, end, "name", "exact committed name")
                )
    return matches, groups


def stem_matches(text: str, roster: dict) -> tuple[list[Match], list[list[str]]]:
    """M2: names sharing a >=2 char stem; the stem is not itself a full name."""
    names = list(_entities_by_name(roster))
    full = set(names)
    prefix_owners: dict[str, set[str]] = {}
    for name in names:
        for length in range(2, len(name)):
            prefix = name[:length]
            if prefix in full:
                continue
            prefix_owners.setdefault(prefix, set()).add(name)

    matches: list[Match] = []
    groups: list[list[str]] = []
    for prefix, owners in prefix_owners.items():
        if len(owners) < 2:
            continue
        if not _find_all(text, prefix):
            continue
        # Keep only the longest stem of a nested family (学生甲 beats 学生).
        if any(other != prefix and other.startswith(prefix) and len(other) > len(prefix) and len(prefix_owners.get(other, ())) >= 2 for other in prefix_owners):
            continue
        ids: list[str] = []
        for owner in sorted(owners):
            ids.extend(e["entityId"] for e in _entities_by_name(roster)[owner])
        groups.append(ids)
        for start, end in _find_all(text, prefix):
            for owner in sorted(owners):
                for entity in _entities_by_name(roster)[owner]:
                    matches.append(
                        Match(entity["entityId"], prefix, start, end, "name_stem", f"shared stem of {sorted(owners)}")
                    )
    return matches, groups


def descriptor_matches(text: str, roster: dict) -> tuple[list[Match], list[list[str]], list[dict], list[dict]]:
    """M3: descriptor text from committed state, unique longest substring only.
    A hit owned by two entities becomes an ambiguity group (never a silent drop).
    """
    names = list(_entities_by_name(roster))
    per_entity: list[tuple[dict, str, str]] = []
    for entity in roster["entities"]:
        descriptor = (entity.get("descriptor") or "").strip()
        if not descriptor:
            continue
        best = ""
        for clause in CLAUSE_SPLIT_RE.split(descriptor):
            clause = clause.strip()
            if len(clause) < 2:
                continue
            hit = longest_common_substring(text, clause)
            if len(hit) > len(best):
                best = hit
        if len(best) >= 2 and not _is_functionish(best):
            per_entity.append((entity, descriptor, best))

    non_unique: list[dict] = []
    dropped: list[dict] = []
    owners_of: dict[str, list[str]] = {}
    for entity, _descriptor, hit in per_entity:
        owners_of.setdefault(hit, []).append(entity["entityId"])

    groups: list[list[str]] = []
    for hit, owners in owners_of.items():
        if len(owners) > 1:
            groups.append(sorted(owners))
            non_unique.append({"surface": hit, "entityIds": sorted(owners)})

    matches: list[Match] = []
    for entity, descriptor, hit in per_entity:
        if any(hit in name and hit != name for name in names):
            dropped.append(
                {"entityId": entity["entityId"], "surface": hit, "reason": "substring_of_committed_name"}
            )
            continue
        if len(owners_of[hit]) > 1:
            continue
        for start, end in _find_all(text, hit):
            matches.append(
                Match(entity["entityId"], hit, start, end, "descriptor", f"from initialAppearance「{descriptor}」")
            )
    return matches, groups, non_unique, dropped


def _mentioned(prior: str, roster: dict, kinds: set[str]) -> list[str]:
    ids: list[str] = []
    for entity in roster["entities"]:
        if entity["kind"] not in kinds:
            continue
        if entity["name"] in prior and entity["entityId"] not in ids:
            ids.append(entity["entityId"])
    return ids


def pronoun_matches(text: str, roster: dict, prior: str) -> tuple[list[Match], list[list[str]], list[str]]:
    """M4: pronouns resolve only with exactly one antecedent of the right kind."""
    matches: list[Match] = []
    groups: list[list[str]] = []
    unresolved: list[str] = []
    protagonist = roster.get("protagonistId")
    taken: list[tuple[int, int]] = []

    for surface in SELF_PRONOUNS:
        for start, end in _find_all(text, surface):
            if any(s <= start and end <= e for s, e in taken):
                continue
            taken.append((start, end))
            if protagonist and any(e["entityId"] == protagonist for e in roster["entities"]):
                matches.append(Match(protagonist, surface, start, end, "pronoun_self", "player self reference"))
            else:
                unresolved.append(surface)

    for surface in PERSON_PRONOUNS_PLURAL + PERSON_PRONOUNS:
        for start, end in _find_all(text, surface):
            if any(s <= start and end <= e for s, e in taken):
                continue
            taken.append((start, end))
            antecedents = _mentioned(prior or "", roster, {"character"})
            plural = surface in PERSON_PRONOUNS_PLURAL
            if len(antecedents) == 1:
                matches.append(Match(antecedents[0], surface, start, end, "pronoun_prior", "single antecedent in prior narration"))
            elif len(antecedents) >= 2:
                if plural:
                    for entity_id in antecedents:
                        matches.append(Match(entity_id, surface, start, end, "pronoun_prior", "plural pronoun, all antecedents"))
                else:
                    groups.append(antecedents)
                    for entity_id in antecedents:
                        matches.append(Match(entity_id, surface, start, end, "pronoun_ambiguous", "several antecedents in prior narration"))
            else:
                unresolved.append(surface)

    for surface in PLACE_PRONOUNS:
        for start, end in _find_all(text, surface):
            if any(s <= start and end <= e for s, e in taken):
                continue
            taken.append((start, end))
            antecedents = _mentioned(prior or "", roster, {"location"})
            if len(antecedents) == 1:
                matches.append(Match(antecedents[0], surface, start, end, "pronoun_place", "single location antecedent"))
            elif len(antecedents) >= 2:
                groups.append(antecedents)
                for entity_id in antecedents:
                    matches.append(Match(entity_id, surface, start, end, "pronoun_place", "several location antecedents"))
            else:
                unresolved.append(surface)

    return matches, groups, unresolved


def _drop_contained(matches: list[Match]) -> list[Match]:
    kept: list[Match] = []
    for match in matches:
        contained = False
        for other in matches:
            if other is match:
                continue
            if other.start <= match.start and match.end <= other.end and (other.end - other.start) > (match.end - match.start):
                contained = True
                break
        if not contained:
            kept.append(match)
    return kept


def _nickname_mentions(text: str, matches: list[Match]) -> list[str]:
    out: list[str] = []
    for hit in NICKNAME_RE.finditer(text):
        span = (hit.start(), hit.end())
        if any(m.start <= span[0] and span[1] <= m.end for m in matches):
            continue
        if hit.group(0) not in out:
            out.append(hit.group(0))
    return out


def parse(utterance: str, roster: dict, prior: str | None = None) -> Parsed:
    text = re.sub(r"\s+", "", utterance or "")
    prior_text = prior or ""

    matches: list[Match] = []
    groups: list[list[str]] = []

    for finder in (name_matches, stem_matches):
        found, _found_groups = finder(text, roster)
        matches.extend(found)

    descriptor_found, descriptor_groups, non_unique, dropped = descriptor_matches(text, roster)
    matches.extend(descriptor_found)
    groups.extend(descriptor_groups)

    pronoun_found, _pronoun_groups, unresolved = pronoun_matches(text, roster, prior_text)
    matches.extend(pronoun_found)

    matches = _drop_contained(matches)

    # A span that maps to several entities is an ambiguity, not a choice.
    by_span: dict[tuple[int, int], set[str]] = {}
    for match in matches:
        by_span.setdefault(match.span(), set()).add(match.entity_id)
    for span, ids in by_span.items():
        if len(ids) > 1:
            groups.append(sorted(ids))

    for nickname in _nickname_mentions(text, matches):
        if nickname not in unresolved:
            unresolved.append(nickname)

    ambiguous_ids = {entity_id for group in groups for entity_id in group}
    ordered: list[Match] = sorted(matches, key=lambda m: (m.start, m.end, m.entity_id))
    seen: set[str] = set()
    resolved: list[str] = []
    for match in ordered:
        if match.entity_id in ambiguous_ids or match.entity_id in seen:
            continue
        seen.add(match.entity_id)
        resolved.append(match.entity_id)

    unique_groups: list[list[str]] = []
    for group in groups:
        key = sorted(set(group))
        if key and key not in unique_groups:
            unique_groups.append(key)

    if unique_groups:
        status = "ambiguous"
    elif resolved:
        status = "resolved"
    elif unresolved:
        status = "unresolved"
    else:
        status = "none"

    targets = sorted(resolved, key=lambda entity_id: next(m.start for m in ordered if m.entity_id == entity_id)) if status == "resolved" else []

    return Parsed(
        status=status,
        attention_targets=targets,
        resolved_candidates=resolved,
        ambiguous_candidates=sorted(ambiguous_ids),
        ambiguous_groups=unique_groups,
        unresolved_mentions=unresolved,
        matches=[
            {"entityId": m.entity_id, "surface": m.surface, "via": m.via, "start": m.start, "end": m.end, "note": m.note}
            for m in ordered
        ],
        non_unique_descriptors=non_unique,
        dropped_descriptors=dropped,
    )


def as_dict(parsed: Parsed, roster: dict | None = None) -> dict:
    names = {}
    if roster:
        names = {entity["entityId"]: entity["name"] for entity in roster["entities"]}
    return {
        "status": parsed.status,
        "attentionTargets": parsed.attention_targets,
        "targetNames": [names.get(entity_id, entity_id) for entity_id in parsed.attention_targets],
        "resolvedCandidates": parsed.resolved_candidates,
        "ambiguousCandidates": parsed.ambiguous_candidates,
        "ambiguousGroups": parsed.ambiguous_groups,
        "unresolvedMentions": parsed.unresolved_mentions,
        "matches": parsed.matches,
        "nonUniqueDescriptors": parsed.non_unique_descriptors,
        "droppedDescriptors": parsed.dropped_descriptors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="c1 attention-parse rule baseline")
    parser.add_argument("--rosters", default="freeze/rosters.json")
    parser.add_argument("--samples", default="freeze/samples.json")
    parser.add_argument("--out", default=None, help="write raw JSON here instead of stdout")
    args = parser.parse_args(argv)

    rosters = json.loads(Path(args.rosters).read_text(encoding="utf-8"))["rosters"]
    samples = json.loads(Path(args.samples).read_text(encoding="utf-8"))["samples"]
    rows = []
    for sample in samples:
        parsed = parse(sample["utterance"], rosters[sample["worldRef"]], sample.get("priorNarration"))
        rows.append({"sampleId": sample["sampleId"], "parsed": as_dict(parsed, rosters[sample["worldRef"]])})
    text = json.dumps({"protocol": "c1-attention-parse-v1", "rows": rows}, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
