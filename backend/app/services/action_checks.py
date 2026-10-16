"""Resolve action checks without storage mutations, network calls, or dice rolls.

The caller supplies the active timeline output and current state. The generator
must call these functions again inside its session lock; a preview never grants
permission to use a result against a different timeline node.
"""

from dataclasses import dataclass
import re
from typing import Any

from app.schemas.agent_io import ActionPermissibility, ActionRuling
from app.schemas.game.action_checks import ActionCheckResult, ActionCheckSubmission, OptionCheck
from app.services.agents.examiner import ExaminerAgent, is_passive_continuation_action


class ActionCheckError(ValueError):
    """The submitted action or die does not match the active turn's check."""


@dataclass(frozen=True)
class ActionCheckResolution:
    check: OptionCheck | None
    option_index: int | None
    ruling: ActionRuling


def is_check_transition(campaign_manager: Any) -> bool:
    """Match the pipeline's chapter-entry exemption without accepting mock clocks."""
    if campaign_manager is None or not campaign_manager.is_loaded():
        return False
    progress = getattr(campaign_manager, "progress", None)
    turn = getattr(progress, "turn_in_session", None)
    total = getattr(progress, "turns_total", None)
    return type(turn) is int and turn == 0 and type(total) is int and total > 0


async def resolve_action_check(
    player_action: str,
    game_state: dict[str, Any],
    previous_output: dict[str, Any] | None,
    option_index: int | None = None,
    *,
    defer_feasibility: bool = False,
) -> ActionCheckResolution:
    """Select saved metadata, or derive one normal d20 check for a custom action.

    A stored null/disabled check is an explicit direct action. The examiner
    still verifies its prerequisites but cannot turn it into a new dice check.
    """
    if game_state.get("sanity", 80) <= 0:
        # No new action is executed after bloodline collapse. The frontend
        # should proceed directly to the ending instead of asking for a roll.
        return ActionCheckResolution(None, None, ActionRuling())
    if re.search(r"[\[【]\s*行动判定\s*[\]】]", player_action):
        raise ActionCheckError("请通过掷骰界面提交判定，行动文本不能包含判定结果。")
    output = previous_output or {}
    options = output.get("options") or []
    if option_index is not None:
        if type(option_index) is not int or not 0 <= option_index < len(options):
            raise ActionCheckError("所选行动已失效，请刷新当前剧情选项。")
        if options[option_index] != player_action:
            raise ActionCheckError("行动内容与所选选项不一致，请重新选择。")
    else:
        matches = [index for index, option in enumerate(options) if option == player_action]
        if len(matches) > 1:
            raise ActionCheckError("当前存在同名行动，请从选项按钮重新选择。")
        option_index = matches[0] if matches else None

    # A new session's first request opens the scripted scene, without a check.
    if not output:
        return ActionCheckResolution(None, None, ActionRuling())

    ruling = (
        ActionRuling() if is_passive_continuation_action(player_action)
        else await ExaminerAgent().examine(player_action, game_state)
    )
    if defer_feasibility and ruling.permissibility == ActionPermissibility.BLOCKED:
        # At chapter entry the snapshot still describes the previous scene.
        # Preserve triggered checks while deferring stale location/NPC/item
        # prerequisites to the same transition path used by the narrator.
        needs_check = any(
            rule.rule_type in {"skill_check", "sanity_check", "combat"}
            for rule in ruling.triggered_rules
        )
        ruling = ActionRuling(
            permissibility=(ActionPermissibility.CONDITIONAL if needs_check else ActionPermissibility.PERMISSIBLE),
            triggered_rules=ruling.triggered_rules,
        )
    if ruling.permissibility == ActionPermissibility.BLOCKED:
        return ActionCheckResolution(None, option_index, ruling)

    if option_index is not None:
        checks = output.get("option_checks") or []
        raw_check = checks[option_index] if option_index < len(checks) else None
        check = OptionCheck.model_validate(raw_check) if raw_check is not None else None
        if check is not None and not check.requires_check:
            check = None
        return ActionCheckResolution(check, option_index, ruling)

    check_rules = [
        rule for rule in ruling.triggered_rules
        if rule.rule_type in {"skill_check", "sanity_check", "combat"}
    ]
    if ruling.permissibility != ActionPermissibility.CONDITIONAL or not check_rules:
        return ActionCheckResolution(None, None, ruling)

    names = list(dict.fromkeys(rule.rule_name for rule in check_rules))
    skills = {
        "sanity_check": "血统稳定",
        "combat": "战斗",
    }
    skill_names = [
        skills.get(rule.rule_type, rule.rule_name.removeprefix("技能检定："))
        for rule in check_rules
    ]
    check = OptionCheck(
        name="／".join(names),
        skill="／".join(dict.fromkeys(skill_names)),
        difficulty="普通",
        stakes="成功推进这次行动；失败时行动受阻，并承担与当前情境相符的后果。",
    )
    return ActionCheckResolution(check, None, ruling)


def validate_action_check(
    resolution: ActionCheckResolution,
    submission: ActionCheckSubmission | None,
) -> ActionCheckResult | None:
    """Require a die exactly when needed, and compute the outcome on the server."""
    check = resolution.check
    if check is None:
        if submission is not None:
            raise ActionCheckError("当前行动不需要判定，请重新提交行动。")
        return None
    if submission is None:
        raise ActionCheckError("当前行动需要判定，请先完成掷骰。")
    if type(submission.roll) is not int or not 1 <= submission.roll <= 20:
        raise ActionCheckError("判定骰点必须为 1 到 20 的整数。")
    if submission.option_index is not None and submission.option_index != resolution.option_index:
        raise ActionCheckError("判定结果与当前行动不一致，请重新选择。")

    # Re-derive the threshold even if an internal caller mutated a model.
    check = OptionCheck.model_validate(check.model_dump())
    roll = submission.roll
    if roll == 20:
        outcome, degree = "critical", "大成功"
    elif roll == 1:
        outcome, degree = "fumble", "大失败"
    elif roll >= check.target:
        outcome, degree = "success", "成功"
    else:
        outcome, degree = "failure", "失败"
    return ActionCheckResult(
        check=check,
        roll=roll,
        option_index=resolution.option_index,
        outcome=outcome,
        degree=degree,
    )
