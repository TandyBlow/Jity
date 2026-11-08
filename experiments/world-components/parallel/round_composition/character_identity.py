"""One authoritative identity record shared by N4 (rendering) and N5 (judging).

Why this exists (owner review of 2026-11-09): the grouped renderer read 急躁 /
沉默 from the character state while the judge read `text`/`appearance` from the
fact objects. The renderer had identifying information the judge never saw, so
for `rb-same-name` G4 stayed undetermined no matter what was rendered. This
module is the single preparation step: it takes the world state once and returns
per-entity descriptors with their authoritative source, so both sides read the
same data.

Rules:
- descriptor = last personality change, else initial personality; if neither,
  last appearance change, else initial appearance (a bare "常态" is not a
  descriptor);
- every entry records the entityId and the exact state path it came from;
- a display name with two different descriptors is distinguishable; identical
  descriptors are NOT evidence and are reported as such.

Usage:
    ids = build_identities(state)
    ids["entries"]["char_pb"] -> {"entityId", "name", "descriptor", "field",
                                  "source"}
    ids["sameName"] -> {"管线乙": {"char_pb": "急躁", "char_pc": "沉默"}}
    ids["indistinguishable"] -> {"管线乙": ["char_pb", "char_pc"]}  # if equal
"""

VERSION = "identity-v0.1"


def _initial(state, eid):
    return ((state.get("initial") or {}).get("characters") or {}).get(eid) or {}


def _current(state, eid):
    return ((state.get("characters") or {}).get(eid)) or {}


def _last_change(state, eid, field):
    changes = _current(state, eid).get(field) or []
    for ch in reversed(changes):
        if isinstance(ch, dict) and ch.get("text"):
            return ch["text"]
    return None


def _describe(state, eid):
    pers = _last_change(state, eid, "personalityChanges")
    if pers:
        return pers, "性格", \
            f"characters.{eid}.personalityChanges[-1].text"
    pers = _initial(state, eid).get("initialPersonality")
    if pers:
        return pers, "性格", f"initial.characters.{eid}.initialPersonality"
    app = _last_change(state, eid, "appearanceChanges")
    if app:
        return app, "外貌", f"characters.{eid}.appearanceChanges[-1].text"
    app = _initial(state, eid).get("initialAppearance")
    if app and app != "常态":
        return app, "外貌", f"initial.characters.{eid}.initialAppearance"
    return None, None, None


def build_identities(state):
    state = state or {}
    entries = {}
    for eid in ((state.get("characters") or {}) or
                (state.get("initial", {}).get("characters") or {})).keys():
        name = _initial(state, eid).get("name") or eid
        desc, field, source = _describe(state, eid)
        entries[eid] = {"entityId": eid, "name": name, "descriptor": desc,
                        "field": field, "source": source}
    by_name = {}
    for eid, e in entries.items():
        by_name.setdefault(e["name"], []).append(eid)
    same = {}
    indistinguishable = {}
    for name, eids in by_name.items():
        if len(eids) < 2:
            continue
        descs = {entries[e]["descriptor"] for e in eids}
        if None in descs or len(descs) < len(eids):
            indistinguishable[name] = sorted(eids)
            continue
        same[name] = {e: entries[e]["descriptor"] for e in sorted(eids)}
    return {"version": VERSION, "entries": entries, "sameName": same,
            "indistinguishable": indistinguishable}


def descriptor_for(identities, eid):
    if not identities:
        return None, None
    e = (identities.get("entries") or {}).get(eid) or {}
    return e.get("descriptor"), e.get("field")


def same_name_descriptors(identities, name, eids):
    """Descriptors for a same-name group, or (None, reason).

    Identical descriptors do not separate two actors, so they are refused here
    instead of letting both the renderer and the judge pretend otherwise.
    """
    if not identities:
        return None, "no-identity-record"
    got = {}
    for eid in eids:
        desc, _ = descriptor_for(identities, eid)
        if not desc:
            return None, "descriptor-missing"
        got[eid] = desc
    if len(set(got.values())) < len(got):
        return None, "descriptors-identical"
    return got, None
