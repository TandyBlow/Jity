"""Carry a server-validated roll into every narrative stage."""

from app.schemas.agent_io import ActionPermissibility, ActionRuling


def check_instruction(result) -> str:
    check = result.check
    effect = (
        "该行动成功，兑现声明的成功收益；大成功可增加合理优势。"
        if result.outcome in {"success", "critical"} else
        "该行动失败，落实声明的失败代价；不得把原行动写成成功。失败仍须带来新信息或新局势。"
    )
    return (
        f"[已结算行动判定] {check.name}，通用 d20，{check.expression}，"
        f"骰面 {result.roll}/20，结果：{result.degree}。\n"
        f"事前约定的后果：{check.stakes}\n{effect}\n"
        "这是后端已经校验的本回合结果。不得重掷、改判、要求再做一次技能或血统稳定检定，"
        "也不得使用 d100 或虚构角色技能值推翻此结果。"
        "骰点不豁免物品、地点、人物在场等事实限制；伤害和资源变化必须符合当前场景。"
    )


def apply_check_to_ruling(ruling: ActionRuling, result, *, resolved: bool) -> ActionRuling:
    """Remove pending-roll instructions only after the action was resolved."""
    if not resolved or ruling.permissibility == ActionPermissibility.BLOCKED:
        return ruling
    updated = ruling.model_copy(deep=True)
    updated.permissibility = ActionPermissibility.PERMISSIBLE
    if result is not None:
        instruction = check_instruction(result)
        updated.constraints = instruction
        for rule in updated.triggered_rules:
            if rule.rule_type in {"skill_check", "sanity_check", "combat"}:
                rule.rule_details = instruction
    else:
        updated.triggered_rules = [
            rule for rule in updated.triggered_rules
            if rule.rule_type not in {"skill_check", "sanity_check", "combat"}
        ]
        updated.constraints = "该行动无需掷骰；按当前场景事实执行，不得另行要求技能或血统稳定检定。"
    return updated


def ending_player_action(request) -> str:
    """A failed attempt cannot satisfy a deterministic success-route trigger."""
    result = getattr(request, "_resolved_action_check", None)
    if result is not None and result.outcome in {"failure", "fumble"}:
        return ""
    return request.player_action
