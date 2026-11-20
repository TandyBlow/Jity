"""表达层唯一新增的编辑操作：为已授权的 before 加“随后”。

前提（任何一条不满足就原样输出并记录原因）：
  R1 两个单元在事实顺序里**相邻**
  R2 关系方向与顺序一致（from = 前一条，to = 后一条）
  R3 关系带**校验器通过**的授权（authorization.verdict == 'pass'）
  R4 校验器版本与本地认识的版本一致
  R5 后一条以自己的人物姓名开头（不省主语、不换代词、不合句）
只有 R1–R5 全部满足，才在**后一句**前面插入“随后，”，保留完整句界。
"""
from __future__ import annotations

VERSION = "relation-edit/1"
VALIDATOR = "world-relation-validator/1"
CONNECTOR = "随后，"


def _index(units):
    return {unit[0]: i for i, unit in enumerate(units)}


def apply_before(units, authorization):
    """units: [(factId, name, text)] 按事实顺序。返回 {"text","ops","fallbacks"}。"""
    text = "".join(unit[2] for unit in units)
    if not authorization or authorization.get("verdict") != "pass":
        return {"text": text, "ops": [],
                "fallbacks": [{"reason": "no-authorized-relation",
                               "detail": (authorization or {}).get("verdict")}]}
    if authorization.get("validatorVersion") != VALIDATOR:
        return {"text": text, "ops": [],
                "fallbacks": [{"reason": "validator-version-mismatch",
                               "detail": authorization.get("validatorVersion")}]}
    position = _index(units)
    outs = [unit[2] for unit in units]
    ops, fallbacks = [], []
    for relation in authorization.get("relations", []):
        source, target = relation.get("fromFactId"), relation.get("toFactId")
        if source not in position or target not in position:
            fallbacks.append({"reason": "unknown-fact", "relation": relation})
            continue
        i, j = position[source], position[target]
        if j != i + 1:
            fallbacks.append({"reason": "not-adjacent" if j > i else "relation-reversed",
                              "relation": relation})
            continue
        name = units[j][1]
        sentence = outs[j]
        if not name or not sentence.startswith(name):
            fallbacks.append({"reason": "subject-not-at-start", "relation": relation})
            continue
        if sentence.startswith(CONNECTOR):
            fallbacks.append({"reason": "already-joined", "relation": relation})
            continue
        outs[j] = CONNECTOR + sentence
        ops.append({"op": "加“随后”", "factId": target, "afterFactId": source,
                    "evidence": relation.get("evidence"),
                    "validatorVersion": relation.get("authorization", {}).get("validatorVersion")})
    return {"text": "".join(outs), "ops": ops, "fallbacks": fallbacks}
