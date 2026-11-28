#!/usr/bin/env python3
"""Compare task achievements between two product evidence runs (same turns)."""
import json
import sys


def achievements(path):
    data = json.load(open(path, encoding="utf-8"))
    out = []
    prev = set()
    for turn in data.get("turns") or []:
        snapshot = turn.get("snapshotAfterTurn") or {}
        state = ((snapshot.get("transport") or {}).get("state")) or {}
        now = set()
        for owner, character in (state.get("characters") or {}).items():
            for task in (character.get("tasks") or {}).values():
                if task.get("status") == "achieved":
                    now.add((owner, task.get("id")))
        calls = [s for s in (turn.get("product") or {}).get("semanticCalls") or []
                 if s.get("task") == "updates" and (s.get("key") or "").endswith("#tasks")]
        out.append({
            "turn": turn.get("turn"), "id": turn.get("id"),
            "new": sorted(now - prev), "all": sorted(now),
            "sources": [s.get("source") for s in calls],
        })
        prev = now
    return out


def main():
    a, b = sys.argv[1], sys.argv[2]
    left, right = achievements(a), achievements(b)
    print(f"A={a}\nB={b}")
    for la, lb in zip(left, right):
        print(f"turn {la['turn']} {la.get('id')}")
        print("  A new", la["new"], "sources", la["sources"])
        print("  B new", lb["new"], "sources", lb["sources"])
    a_all = set(left[-1]["all"]) if left else set()
    b_all = set(right[-1]["all"]) if right else set()
    print("A only", sorted(a_all - b_all))
    print("B only", sorted(b_all - a_all))


if __name__ == "__main__":
    main()
