"""N3 叙事计划的关系字段：最小契约与校验（第一版只允许 before）。

关系不写进事实序列化（fact_contract 不动），单独放在计划的 relations 里，
每条关系必须引用真实证据事件。

    {"type": "before",
     "fromFactId": "f2",
     "toFactId": "f10",
     "evidenceEventIds": ["e17", "e18"]}

证据的可信来源只有时间线本身：
  - 同一世界、同一 chain（previousPointId 相连）
  - 两点之间的时间推进之和 > 0（timeAdvance.boundary=elapsed 且 duration>0）

明确不构成证据的东西：
  - 数组/事实列表顺序
  - factId 的字典序
  - 同一个 advanceId（批次）
  - round.order 的遍历顺序（处理顺序）
  - boundary=instant / duration=0（只是“引擎没有推进时间”，不是“同时”）
"""
from __future__ import annotations

UNIT_SECONDS = {"second": 1, "minute": 60, "hour": 3600}

class RelationError(ValueError):
    pass


def _seconds(time_json):
    if not time_json or time_json.get("boundary") != "elapsed":
        return 0
    d = time_json.get("duration") or {}
    return int(d.get("amount") or 0) * UNIT_SECONDS.get(d.get("unit"), 0)


def elapsed_between(a, b, points):
    """同一 chain 上 a 到 b 的时间推进之和；不同 chain 或方向不对返回 None。"""
    seq = {p["id"]: p for p in points}
    if a not in seq or b not in seq:
        return None
    pa, pb = seq[a], seq[b]
    if pa.get("worldId") != pb.get("worldId"):
        return None
    chain, cur = [], a
    while cur is not None:
        chain.append(cur)
        if cur == b:
            break
        nxt = [p["id"] for p in points if p.get("previousPointId") == cur]
        cur = nxt[0] if len(nxt) == 1 else None
    else:
        return None
    if not chain or chain[-1] != b:
        return None
    return sum(_seconds(seq[p].get("time")) for p in chain[1:])


def validate(relations, plan_fact_ids, fact_events, points):
    """返回问题列表；空表示全部合法。

    plan_fact_ids: 计划里出现的 factId 集合
    fact_events:   {factId: [eventId, ...]}  事实 → 产生它的已提交事件
    points:        [{"id","worldId","sequence","previousPointId","time"}]
    """
    problems = []
    edges = []
    for i, r in enumerate(relations):
        tag = f"relations[{i}]"
        if r.get("type") != "before":
            problems.append(f"{tag}: 第一版只允许 type=before，得到 {r.get('type')!r}")
            continue
        a, b = r.get("fromFactId"), r.get("toFactId")
        if a not in plan_fact_ids or b not in plan_fact_ids:
            problems.append(f"{tag}: factId 不在计划内（{a!r}→{b!r}）")
            continue
        if a == b:
            problems.append(f"{tag}: 自指（{a}→{b}）")
            continue
        ev = r.get("evidenceEventIds") or []
        if not ev:
            problems.append(f"{tag}: 缺少 evidenceEventIds")
            continue
        unknown = [e for e in ev if not any(e == x for x in fact_events.get(a, []) + fact_events.get(b, []))]
        if unknown:
            problems.append(f"{tag}: 证据事件无法追溯到这两条事实 {unknown}")
            continue
        ev_a = [e for e in fact_events.get(a, []) if e in ev]
        ev_b = [e for e in fact_events.get(b, []) if e in ev]
        if not ev_a or not ev_b:
            problems.append(f"{tag}: 证据没有同时覆盖两端（{a}:{ev_a} {b}:{ev_b}）")
            continue
        # 取时间上最早/最晚的证据点，要求两端之间确实推进过时间
        secs = None
        for pa in ev_a:
            for pb in ev_b:
                s = elapsed_between(pa, pb, points)
                if s is not None:
                    secs = s if secs is None else max(secs, s)
        if secs is None:
            problems.append(f"{tag}: 两点不在同一 chain，无法比较先后")
            continue
        if secs <= 0:
            problems.append(f"{tag}: 两点之间时间推进为 0，不构成先后证据")
            continue
        edges.append((a, b))
    # 成环检查（只看通过验证的边，再连上所有声称的边）
    claimed = [(r.get("fromFactId"), r.get("toFactId")) for r in relations
               if r.get("type") == "before" and r.get("fromFactId") != r.get("toFactId")]
    adj = {}
    for a, b in claimed:
        adj.setdefault(a, []).append(b)
    state = {}
    def dfs(n):
        state[n] = 1
        for m in adj.get(n, []):
            if state.get(m) == 1:
                return True
            if state.get(m) is None and dfs(m):
                return True
        state[n] = 2
        return False
    if any(state.get(n) is None and dfs(n) for n in list(adj)):
        problems.append("关系成环")
    return problems
