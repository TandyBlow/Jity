# N4.1 scene-context assembly: authoritative state + selected facts + explicit
# environment overlay -> the scene/character context consumed by N4.2.
#
# State-authority rules:
#   - locations/path/appearance, characters, items all come from the state;
#   - "present" is NOT a full roster scan: it is the viewpoint subject plus
#     entities that carry a SELECTED fact at this scene. A 100-NPC location
#     with no facts must not be enumerated (the old co-presence regression);
#   - weather/wind/light/time-of-day are not in WorldState; they come from an
#     explicit environment overlay. If absent they stay None and the renderer
#     omits them; the builder never invents weather.
#
# The builder returns a `sceneContext` (the shape the renderer consumes)
# plus a `worldView` (names/appearances for the renderer). It does not write
# state, facts or prose.

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def _active_text(initial_text, changes):
    texts = [c.get("text") for c in (changes or [])
             if c.get("active") and c.get("text")]
    if not texts:
        return initial_text
    return "；".join([initial_text] + texts)


def _item_name(state, iid):
    return ((state.get("initial") or {}).get("items") or {}).get(iid, {}).get("name")


def _char_name(state, eid):
    return ((state.get("initial") or {}).get("characters") or {}).get(eid, {}).get("name")


def _loc_name(state, lid):
    return ((state.get("initial") or {}).get("locations") or {}).get(lid, {}).get("name")


def _path_ids(state, lid):
    initial = (state.get("initial") or {}).get("locations") or {}
    out = []
    seen = set()
    while lid is not None and lid in initial and lid not in seen:
        out.append(lid)
        seen.add(lid)
        lid = initial[lid].get("parentLocationId")
    return list(reversed(out))


def _appearance(state, kind, eid):
    initial = (state.get("initial") or {}).get(kind) or {}
    current = (state.get(kind) or {}).get(eid) or {}
    base = initial.get(eid, {}).get("initialAppearance")
    return _active_text(base, current.get("appearanceChanges"))


def _personality(state, eid):
    initial = (state.get("initial") or {}).get("characters") or {}
    current = (state.get("characters") or {}).get(eid) or {}
    base = initial.get(eid, {}).get("initialPersonality")
    return _active_text(base, current.get("personalityChanges"))


def _inventory(state, eid):
    out = []
    for iid, item in (state.get("items") or {}).items():
        pos = item.get("position") or {}
        if pos.get("containerId") == eid:
            out.append(iid)
    return out


def build_scene_context(state, perspective, selected_facts,
                        environment=None):
    env = environment or {}
    diagnostics = []
    subject = (perspective or {}).get("entityId")
    characters = state.get("characters") or {}
    if subject not in characters:
        return {"status": "stopped", "reason": "subject-unregistered",
                "diagnostics": [{"code": "subject-unregistered",
                                 "entityId": subject}]}
    loc_id = (characters[subject].get("position") or {}).get("containerId")
    initial_locs = ((state.get("initial") or {}).get("locations") or {})
    if loc_id not in initial_locs:
        return {"status": "stopped", "reason": "subject-location-unresolvable",
                "diagnostics": [{"code": "subject-location-unresolvable",
                                 "entityId": subject, "containerId": loc_id}]}
    path_ids = _path_ids(state, loc_id)
    loc_name = _loc_name(state, loc_id)

    # present = subject + entities with a SELECTED fact at this scene.
    # Never iterate state.characters to build a roster.
    present = [subject]
    for f in selected_facts or []:
        eid = f.get("entityId")
        if not eid or eid == subject or eid in present:
            continue
        at = f.get("at") or f.get("to")
        if at == loc_name and eid in characters:
            present.append(eid)

    item_ids = []
    for iid, item in (state.get("items") or {}).items():
        pos = item.get("position") or {}
        if pos.get("containerId") in (loc_id, *present):
            item_ids.append(iid)

    character_context = []
    for eid in present:
        inv = _inventory(state, eid)
        character_context.append({
            "entityId": eid,
            "name": _char_name(state, eid),
            "personality": _personality(state, eid),
            "appearance": _appearance(state, "characters", eid),
            "inventory": inv,
            "use": "read",
        })

    scene_state = {
        "locationId": loc_id,
        "locationPath": path_ids,
        "time": env.get("time"),
        "weather": env.get("weather"),
        "wind": env.get("wind"),
        "light": env.get("light"),
        "present": present,
        "visibleItems": item_ids,
        "atmosphere": env.get("atmosphere"),
    }
    for key in ("time", "weather", "wind", "light", "atmosphere"):
        if scene_state[key] is None:
            diagnostics.append({"code": "environment-field-missing",
                                "field": key})

    world_view = {"locations": {}, "items": {}, "characters": {}}
    for lid in path_ids:
        world_view["locations"][lid] = {
            "name": _loc_name(state, lid),
            "appearance": _appearance(state, "locations", lid),
            "sublocations": [],
        }
    for iid in item_ids:
        world_view["items"][iid] = {
            "name": _item_name(state, iid),
            "appearance": _appearance(state, "items", iid),
        }
    for cc in character_context:
        world_view["characters"][cc["entityId"]] = {
            "name": cc["name"],
            "appearance": cc["appearance"],
            "personality": cc["personality"],
            "inventory": cc["inventory"],
        }
    return {"status": "ok", "sceneContext": {
        "sceneState": scene_state,
        "characterContext": character_context,
        "perspective": {"entityId": subject},
    }, "worldView": world_view, "diagnostics": diagnostics}
