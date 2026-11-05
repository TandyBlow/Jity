"""保守编辑层 v2：只合并相邻、同主体的单元。

版本：edit-layer/2（2026-11-04）
v2 相对 v1：
  - 顺序改为“按输入给定顺序”，不再按 factId 字符串排序（避免 f10 排在 f2 前）
  - 所有格操作单独记录为“删姓名＋的”，并校验所有者可无歧义恢复
  - 不确定结构一律回退原稿，并记录回退原因

规则（按顺序判断，任何一步不满足就回退原稿）：
R1 顺序 = 输入顺序，不重排、不按编号重排。
R2 只有人物主体参与合并；物件、场景主体原样。
R3 相邻且同主体才合并；首句保留姓名；后续句删句首姓名，若为“姓名＋的”则连“的”一起删。
R4 合并只加逗号，句末句号；不插入时间、同时、因果词。
R5 跨主体交替、no_change 句、非人物主体：原样。
R6 句内标点统一为全角逗号。
R7 前一句以“才发现/原来”收尾时不合并（否则会被读成因果）。
"""
VERSION = "edit-layer/2"
import re

NAMES = ("沈砚", "顾行舟", "叶知微", "阿棠", "韩渡")
REFLECT = re.compile(r"(才发现|原来|这才发现)")
BAD_HEAD = re.compile(r"^(把|被|从|在|向|朝|对|给|和|跟)")      # 删主语后不成句
SECURED = re.compile(r"(再|又|随后|接着|然后|同时|正|这时|一边|跟着|于是|所以|因为|之后|先前)")


def strip_subject(text, name):
    """返回 (去掉句首姓名后的内容, 操作类型)。不适用时返回 (None, None)。"""
    t = text.strip().rstrip("。")
    if t.startswith(name + "的"):
        return t[len(name) + 1:], "删姓名＋的"
    if t.startswith(name):
        return t[len(name):], "删姓名"
    return None, None


def _check_unit(unit):
    """单元自身是否适合参与合并。返回 (ok, 原因)。"""
    fid, name, text = unit
    t = (text or "").strip()
    if not t:
        return False, "空文本"
    if name not in NAMES:
        return False, "非人物主体"
    if t.count(name) != 1:
        return False, "主体名出现多次"
    if not t.startswith(name):
        return False, "主体名不在句首"
    body, op = strip_subject(t, name)
    if body is None:
        return False, "无法安全删主语"
    if len(body.strip()) < 3:
        return False, "删主语后过短"
    if op == "删姓名＋的" and BAD_HEAD.match(body.strip()):
        return False, "删姓名＋的之后不成句"
    return True, None


def edit_source(units, source_id=None):
    """units: [(factId, name, text)]，**按输入顺序**，不排序。

    返回 {"sourceId","version","original","edited","ops","fallbacks"}
    """
    original = "".join(t for _, _, t in units)
    out, ops, fallbacks = [], [], []
    i = 0
    while i < len(units):
        ok_i, why_i = _check_unit(units[i])
        if not ok_i:
            fallbacks.append({"factId": units[i][0], "reason": why_i})
            out.append(units[i][2].strip()); i += 1; continue
        j = i + 1
        while j < len(units):
            ok_j, why_j = _check_unit(units[j])
            if not ok_j or units[j][1] != units[i][1]:
                break
            if REFLECT.search(units[j - 1][2]):
                break
            j += 1
        if j - i == 1:
            out.append(units[i][2].strip()); i = j; continue
        # 合并：首句保留姓名，后续删姓名；所有者必须能在本句内无歧义恢复
        parts = [units[i][2].strip().rstrip("。")]
        local_ok = True
        for k in range(i + 1, j):
            body, op = strip_subject(units[k][2], units[k][1])
            if body is None or units[i][1] not in "".join(parts):
                local_ok = False; break
            parts.append(body)
            ops.append({"factId": units[k][0], "op": op,
                        "before": units[k][2].strip(),
                        "after": body,
                        "ownerRecoverable": True})
        if not local_ok:
            fallbacks.append({"factId": units[i][0], "reason": "合并时所有者不可恢复"})
            out.append(units[i][2].strip()); i += 1; continue
        ops.append({"factId": units[i][0], "op": "合句（逗号串联）",
                    "mergedFactIds": [units[k][0] for k in range(i, j)]})
        merged = "，".join(parts).replace(",", "，")
        out.append(merged + "。")
        i = j
    return {"sourceId": source_id, "version": VERSION, "original": original,
            "edited": "".join(out), "ops": ops, "fallbacks": fallbacks,
            "changed": "".join(out) != original}
