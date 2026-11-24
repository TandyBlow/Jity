"""Deterministic local feasibility checks; never calls an LLM or rolls dice.

Only explicit use/interaction/location phrases impose prerequisites. Unknown
free-form prose is left to the narrator rather than treated as a parsed command.
The legacy rules_texts argument is ignored; rule prose cannot activate a roll.
"""

import re
from typing import Any

from app.schemas.agent_io import ActionPermissibility, ActionRuling, TriggeredRule

_PASSIVE_CONTINUATION_RE = re.compile(
    r"^\s*(?:继续|继续剧情|继续故事|接着|接着讲|接着说)[。.!！?？…]*\s*$"
)
_OWNED = {"owned", "active", "equipped", "持有", "获得", "已装备"}
_PRESENT = {"present", "following", "在场", "同行"}
_COMBAT = re.compile(r"攻击|射击|开枪|挥刀|刺向|格斗|战斗|反击")
_SKILLS = {
    "侦查": r"侦查|搜查|搜索|调查|观察",
    "聆听": r"聆听|偷听",
    "潜行": r"潜行|潜入|悄悄接近",
    "开锁": r"撬锁|开锁",
    "说服": r"说服|劝说|威吓|恐吓",
    "急救": r"急救|包扎|治疗",
    "运动": r"攀爬|攀登|游泳|跳跃|奔跑|冲刺",
    "知识": r"破解|破译|鉴定|辨认|黑客",
}
_SAN = re.compile(r"SAN\s*检定|理智检定|血统稳定(?:值)?检定|(?:直视|遭遇|目睹|看见).*(?:神话生物|古神|龙王)|释放言灵|发动言灵|使用言灵", re.I)
_PHYSICAL = re.compile(r"攻击|射击|开枪|格斗|战斗|反击|攀爬|攀登|游泳|跳跃|奔跑|冲刺")
# A noun is bounded by the next action verb; searching for an item is not use.
_ITEM_USE = re.compile(
    r"(?:使用|用(?!力|心)|拿出|掏出|举起|装备|喝下|服用)\s*[\"“「]?"
    r"(?P<name>[^，。！？；、\s\"”」]{1,24}?)"
    r"[\"”」]?(?=来|进行|打开|开启|开门|解锁|撬|照|攻击|射击|检查|治疗|包扎|与|和|向|对|，|。|！|？|；|$)"
)
_NPC_INTERACTION = re.compile(
    r"(?:与|和|跟|向|对)\s*[\"“「]?(?P<name>[^，。！？；\s\"”」]{1,16}?)[\"”」]?"
    r"(?:交谈|对话|谈话|交流|询问|问话|搭话|求助|说话)"
)
_DIRECT_NPC = re.compile(r"(?:^|，)\s*(?:我)?(?:询问|问话|说服)\s*[\"“「]?(?P<name>[^，。！？；\s\"”」]{1,16}?)[\"”」]?(?=关于|有关|是否|，|。|！|？|；|$)")
_LOCATION = re.compile(r"(?:^|，|；)\s*(?:我)?在(?P<name>[^，。！？；]{1,20}?)(?:里|内)?(?:调查|搜索|搜查|休息|使用|打开|与|和)")
_GENERIC_TARGETS = {"他", "她", "它", "他们", "她们", "对方", "敌人", "怪物", "NPC", "npc", "所有人"}


def is_passive_continuation_action(player_action: str) -> bool:
    return bool(_PASSIVE_CONTINUATION_RE.fullmatch(player_action))


def _active_clauses(action: str) -> str:
    """Ignore explicit negated/hypothetical clauses, not every occurrence of 不."""
    clauses = re.split(r"[，。！？；\n]|(?:而是|但是)", action)
    return "，".join(
        clause for clause in clauses
        if not re.match(r"\s*(?:我)?(?:不|不要|并不|并未|没有|放弃|取消|如果|假如|是否|能否)", clause)
    )


def _entities(state: dict, key: str) -> dict[str, dict]:
    return {
        entry["name"]: entry for entry in state.get(key, [])
        if isinstance(entry, dict) and entry.get("name")
    }


def _resolve_name(name: str) -> str:
    name = re.sub(r"^(?:我的|背包里的|背包中的|手中的|一把|一支|一个|一瓶)", "", name).strip()
    # Exact match first; never claim a different named item is the requested one.
    return name


class ExaminerAgent:
    """Python rules over the existing item/NPC/location/sanity/health state."""

    async def examine(
        self,
        player_action: str,
        game_state: dict[str, Any],
        rules_texts: list[str] | None = None,
    ) -> ActionRuling:
        if is_passive_continuation_action(player_action):
            return ActionRuling()
        action = _active_clauses(player_action)
        items = _entities(game_state, "items")
        npcs = _entities(game_state, "npcs")
        location = game_state.get("current_location", "")
        failures: list[str] = []
        rules: list[TriggeredRule] = []

        for match in _ITEM_USE.finditer(action):
            name = _resolve_name(match["name"])
            # Abilities and body parts are not inventory items.
            if name.startswith("言灵") or name in {"技能", "双手", "手", "拳头", "力气", "全力"}:
                continue
            item = items.get(name)
            if item is None or item.get("status", "owned") not in _OWNED:
                failures.append(f"你目前没有可用的“{name}”，无法使用它。")
            else:
                rules.append(TriggeredRule(rule_type="item_use", rule_name=f"使用物品：{name}"))

        targets = {m["name"] for pattern in (_NPC_INTERACTION, _DIRECT_NPC) for m in pattern.finditer(action)}
        # Known NPCs can also be the target of a longer sentence.
        for name in npcs:
            if re.search(r"(?:询问|攻击|说服|治疗)\s*" + re.escape(name), action):
                targets.add(name)
        # A longer inquiry may include a known name followed by its topic.
        targets = {
            next((known for known in sorted(npcs, key=len, reverse=True) if name.startswith(known)), name)
            for name in targets
        }
        for name in sorted(targets):
            if name in _GENERIC_TARGETS:
                continue
            npc = npcs.get(name)
            if npc is None:
                failures.append(f"当前记录中没有“{name}”，无法确认与其直接互动。")
                continue
            status = npc.get("status", "present")
            npc_location = npc.get("current_location", "")
            if status not in _PRESENT or (
                status not in {"following", "同行"} and npc_location and location and npc_location != location
            ):
                failures.append(f"“{name}”目前不在场，无法与其直接互动。")

        for match in _LOCATION.finditer(action):
            required = match["name"]
            approaching = re.search(
                r"(?:前往|走到|去|到达)" + re.escape(required), action[:match.start()]
            )
            if location and required != location and not approaching:
                failures.append(f"你当前位于“{location}”，需要先到达“{required}”才能在那里行动。")

        combat = bool(_COMBAT.search(action))
        sanity = bool(_SAN.search(action))
        if (combat or _PHYSICAL.search(action)) and game_state.get("health", 100) <= 0:
            failures.append("你的体力已经耗尽，无法执行这项体力行动。")
        if sanity and game_state.get("sanity", 80) <= 0:
            failures.append("你的血统稳定值已经耗尽，无法主动进行这项高风险行动。")
        if sanity:
            rules.append(TriggeredRule(
                rule_type="sanity_check", rule_name="SAN／血统稳定检定",
                rule_details="需要进行血统稳定检定（1d100 ≤ 当前SAN值）；本地检查尚未掷骰，不得视为自动成功。",
            ))
        for skill, pattern in _SKILLS.items():
            if re.search(pattern, action):
                rules.append(TriggeredRule(
                    rule_type="skill_check", rule_name=f"技能检定：{skill}",
                    rule_details="需依据角色技能值进行检定；没有技能值或检定结果时，不得编造成功结果。",
                ))
        if combat:
            rules.append(TriggeredRule(
                rule_type="combat", rule_name="战斗规则",
                rule_details="进入战斗判定，需核实命中、防御和伤害；本地检查不结算伤害。",
            ))
        if failures:
            reason = "\n".join(dict.fromkeys(failures))
            return ActionRuling(
                permissibility=ActionPermissibility.BLOCKED,
                triggered_rules=rules, constraints=reason, rejection_reason=reason,
            )
        needs_check = any(rule.rule_type != "item_use" for rule in rules)
        return ActionRuling(
            permissibility=ActionPermissibility.CONDITIONAL if needs_check else ActionPermissibility.PERMISSIBLE,
            triggered_rules=rules,
            constraints="需要处理触发的规则；未进行掷骰，不得宣称检定已成功。" if needs_check else "",
        )
