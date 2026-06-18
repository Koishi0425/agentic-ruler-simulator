from __future__ import annotations

import json
import random
from pathlib import Path

from .models import (
    ActionIntent,
    EndTurnReport,
    ExternalEvent,
    GameState,
    MyNation,
    NationChange,
    Province,
    RivalChange,
    RivalNation,
    StatDelta,
    clamp,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
WORLD_CONFIG_PATH = ROOT_DIR / "world_config.json"


ACTION_KEYWORDS = {
    "attack": ["进攻", "攻击", "宣战", "开战", "攻打", "征服", "讨伐"],
    "diplomacy": ["外交", "使者", "改善关系", "结盟", "谈判", "通商", "互市"],
    "mobilize": ["动员", "征兵", "扩军", "集结", "备战"],
    "build": ["建设", "修筑", "建造", "修复", "要塞", "粮仓", "工厂", "道路", "哨塔"],
    "expand": ["扩张", "殖民", "开拓", "吞并", "占领无主", "边疆开垦"],
}


def load_world_config() -> dict:
    return json.loads(WORLD_CONFIG_PATH.read_text(encoding="utf-8"))


def initialize_world(setting: str) -> tuple[MyNation, list[RivalNation], int, list[str], EndTurnReport]:
    config = load_world_config()
    template = config.get(setting) or config["架空中世纪"]
    nation = MyNation.model_validate(template["my_nation"])
    rivals = [RivalNation.model_validate(item) for item in template["rivals"]]
    tension = clamp(round(sum(rival.threat for rival in rivals) / max(1, len(rivals))), 0, 100)
    intel = [
        f"边境斥候认为{rivals[0].name}的真实兵力可能高于公开情报。"
    ]
    report = EndTurnReport(
        economy="核心省份维持基础产出，财政尚能支撑一次中等规模行动。",
        border=f"{rivals[0].name}在边境保持压力。",
        intel=intel[0],
        factions="内廷派系尚未完全理解外部威胁的重量。",
        military=f"常备军战力约 {nation.army_power}，动员等级 {nation.mobilization}。",
    )
    return nation, rivals, tension, intel, report


def ensure_world_state(state: GameState) -> GameState:
    needs_world = not state.my_nation.provinces or not state.world_map
    if not needs_world:
        return state
    nation, rivals, tension, intel, report = initialize_world(state.world_metadata.setting)
    return state.model_copy(
        deep=True,
        update={
            "my_nation": nation,
            "world_map": rivals,
            "world_tension": tension,
            "intel_reports": state.intel_reports or intel,
            "end_turn_report": report,
        },
    )


def parse_action_intents(command: str, state: GameState) -> list[ActionIntent]:
    intents: list[ActionIntent] = []
    for action_type, keywords in ACTION_KEYWORDS.items():
        if any(keyword in command for keyword in keywords):
            intents.append(
                ActionIntent(
                    action_type=action_type,  # type: ignore[arg-type]
                    target=_find_target(command, state),
                    details=command,
                )
            )
    if not intents:
        intents.append(ActionIntent(action_type="domestic_policy", details=command))
    elif not any(intent.action_type == "domestic_policy" for intent in intents):
        if any(keyword in command for keyword in ["加税", "赈济", "特权", "改革", "镇压"]):
            intents.append(ActionIntent(action_type="domestic_policy", details=command))
    return intents


def resolve_world_actions(
    state: GameState, command: str, intents: list[ActionIntent]
) -> tuple[
    StatDelta,
    list[NationChange],
    list[RivalChange],
    list[ExternalEvent],
    EndTurnReport,
    int,
    list[str],
    str,
]:
    rng = random.Random(f"{state.game_id}:{state.turn_number}:{command}")
    stat_delta = StatDelta()
    nation_changes: list[NationChange] = []
    rival_changes: list[RivalChange] = []
    events: list[ExternalEvent] = []
    intel_updates: list[str] = []
    report = EndTurnReport()
    world_tension_delta = 0
    military_lines: list[str] = []
    border_lines: list[str] = []
    economy_lines: list[str] = []
    intel_lines: list[str] = []

    for intent in intents:
        if intent.action_type == "mobilize":
            stat_delta.treasury -= 12
            stat_delta.stability -= 3
            world_tension_delta += 4
            nation_changes.append(
                NationChange(
                    army_power_delta=90,
                    mobilization_delta=18,
                    war_exhaustion_delta=4,
                    reason="动员民兵与军镇预备队。",
                )
            )
            military_lines.append("动员令提升了战力，但工坊与田庄开始感到人手紧张。")
        elif intent.action_type == "diplomacy":
            rival = _target_rival(state, intent.target)
            if rival:
                stat_delta.treasury -= 6
                rival_changes.append(
                    RivalChange(
                        nation_id=rival.nation_id,
                        threat_delta=-8,
                        relations_delta=16,
                        reason="派出使者、礼物与互市承诺。",
                    )
                )
                world_tension_delta -= 3
                border_lines.append(f"派往{rival.name}的使团降低了边境误判风险。")
            else:
                economy_lines.append("外交资源被分散使用，未能锁定明确目标。")
        elif intent.action_type == "build":
            stat_delta.treasury -= 14
            province = _target_province(state, intent.target)
            facility = _facility_from_command(command)
            updated = _province_with_facility(province or state.my_nation.provinces[0], facility)
            nation_changes.append(
                NationChange(
                    province_updates=[updated],
                    army_power_delta=25 if facility in {"要塞", "哨塔", "军营"} else 0,
                    reason=f"在{updated.name}修筑{facility}。",
                )
            )
            economy_lines.append(f"{updated.name}开始修筑{facility}，短期耗费国库，长期改善战略纵深。")
        elif intent.action_type == "expand":
            stat_delta.treasury -= 10
            stat_delta.stability -= 2
            new_province = Province(
                id=f"frontier_{state.turn_number + len(nation_changes) + 1}",
                name=_frontier_name(state),
                province_type="frontier",
                facilities=["临时哨站"],
                output={"treasury": 4, "army_power": 10},
                adjacent_targets=[rival.nation_id for rival in state.world_map[:2]],
            )
            nation_changes.append(
                NationChange(
                    army_power_delta=-20,
                    war_exhaustion_delta=2,
                    added_provinces=[new_province],
                    reason=f"开拓并控制{new_province.name}。",
                )
            )
            world_tension_delta += 6
            border_lines.append(f"{new_province.name}被纳入王国边疆，但邻国也注意到了旗帜的移动。")
        elif intent.action_type == "attack":
            rival = _target_rival(state, intent.target) or _most_threatening_rival(state)
            attack_result = _resolve_attack(state, rival, rng)
            stat_delta.treasury += attack_result["treasury"]
            stat_delta.stability += attack_result["stability"]
            stat_delta.prestige += attack_result["prestige"]
            nation_changes.append(attack_result["nation_change"])
            rival_changes.append(attack_result["rival_change"])
            events.append(attack_result["event"])
            world_tension_delta += attack_result["tension"]
            military_lines.append(attack_result["summary"])

    external_event = maybe_external_event(state, rng)
    if external_event:
        event, rival_change, tension = external_event
        events.append(event)
        rival_changes.append(rival_change)
        world_tension_delta += tension
        border_lines.append(event.description)

    if any("间谍" in command or "情报" in command or "侦察" in command for _ in [0]):
        rival = _most_threatening_rival(state)
        intel = f"密探回报：{rival.name}的真实战力约为 {rival.true_power}，公开估计偏差正在缩小。"
        intel_updates.append(intel)
        intel_lines.append(intel)
        rival_changes.append(
            RivalChange(
                nation_id=rival.nation_id,
                threat_delta=-2,
                relations_delta=-3,
                reason="间谍网提高情报精度，但也激怒了对方。",
            )
        )

    report = EndTurnReport(
        economy="；".join(economy_lines) or _economy_report(stat_delta),
        border="；".join(border_lines) or "边境没有爆发新的公开摩擦。",
        intel="；".join(intel_lines) or _intel_report(state),
        factions="派系态度已反映在御前会议记录中。",
        military="；".join(military_lines) or _military_report(state),
    )
    narrative_suffix = _world_narrative(events, report)
    return (
        stat_delta,
        nation_changes,
        rival_changes,
        events,
        report,
        world_tension_delta,
        intel_updates,
        narrative_suffix,
    )


def apply_world_changes(
    state: GameState,
    nation_changes: list[NationChange],
    rival_changes: list[RivalChange],
    world_tension_delta: int,
    intel_updates: list[str],
    end_turn_report: EndTurnReport,
) -> GameState:
    nation = state.my_nation.model_copy(deep=True)
    provinces = {province.id: province for province in nation.provinces}
    for change in nation_changes:
        nation.army_power = clamp(nation.army_power + change.army_power_delta, 0, 5000)
        nation.tech_level = clamp(nation.tech_level + change.tech_level_delta, 1, 10)
        nation.mobilization = clamp(nation.mobilization + change.mobilization_delta)
        nation.war_exhaustion = clamp(nation.war_exhaustion + change.war_exhaustion_delta)
        for province in change.added_provinces:
            provinces[province.id] = province
        for province in change.province_updates:
            provinces[province.id] = province
    nation.provinces = list(provinces.values())

    rival_change_by_id = {change.nation_id: change for change in rival_changes}
    rivals: list[RivalNation] = []
    for rival in state.world_map:
        change = rival_change_by_id.get(rival.nation_id)
        if not change:
            rivals.append(rival)
            continue
        rivals.append(
            rival.model_copy(
                update={
                    "visible_power": clamp(
                        rival.visible_power + change.visible_power_delta, 0, 5000
                    ),
                    "true_power": clamp(rival.true_power + change.true_power_delta, 0, 5000),
                    "threat": clamp(rival.threat + change.threat_delta),
                    "relations": clamp(rival.relations + change.relations_delta, -100, 100),
                    "stance": change.stance or rival.stance,
                    "war_status": change.war_status or rival.war_status,
                }
            )
        )

    intel = [*state.intel_reports[-4:], *intel_updates]
    return state.model_copy(
        deep=True,
        update={
            "my_nation": nation,
            "world_map": rivals,
            "world_tension": clamp(state.world_tension + world_tension_delta),
            "intel_reports": intel[-5:],
            "end_turn_report": end_turn_report,
        },
    )


def maybe_external_event(
    state: GameState, rng: random.Random
) -> tuple[ExternalEvent, RivalChange, int] | None:
    trigger = state.turn_number > 0 and state.turn_number % rng.randint(3, 5) == 0
    pressure = state.global_stats.stability < 40 or state.world_tension > 70
    if not trigger and not pressure:
        return None
    rival = _most_threatening_rival(state)
    if rival.threat > 65 or pressure:
        return (
            ExternalEvent(
                category="border",
                title=f"{rival.name}制造边境摩擦",
                description=f"{rival.name}的前哨骑兵越过争议边界，试探你的防线。",
                nation_id=rival.nation_id,
            ),
            RivalChange(
                nation_id=rival.nation_id,
                threat_delta=6,
                relations_delta=-8,
                war_status="border_conflict",
                reason="对手认为王国内部压力正在扩大。",
            ),
            5,
        )
    return (
        ExternalEvent(
            category="opportunity",
            title=f"{rival.name}出现继承争端",
            description=f"情报显示{rival.name}的贵族正在争夺继承权，边境压力短暂下降。",
            nation_id=rival.nation_id,
        ),
        RivalChange(
            nation_id=rival.nation_id,
            threat_delta=-5,
            relations_delta=2,
            reason="邻国内部争端牵制其外部行动。",
        ),
        -3,
    )


def _find_target(command: str, state: GameState) -> str:
    for rival in state.world_map:
        if rival.name in command or rival.nation_id in command:
            return rival.nation_id
    for province in state.my_nation.provinces:
        if province.name in command or province.id in command:
            return province.id
    if "北" in command and state.world_map:
        return state.world_map[0].nation_id
    if "南" in command and len(state.world_map) > 1:
        return state.world_map[1].nation_id
    if "东" in command and len(state.world_map) > 2:
        return state.world_map[2].nation_id
    return ""


def _target_rival(state: GameState, target: str) -> RivalNation | None:
    return next(
        (
            rival
            for rival in state.world_map
            if rival.nation_id == target or rival.name == target
        ),
        None,
    )


def _target_province(state: GameState, target: str) -> Province | None:
    return next(
        (
            province
            for province in state.my_nation.provinces
            if province.id == target or province.name == target
        ),
        None,
    )


def _most_threatening_rival(state: GameState) -> RivalNation:
    return max(state.world_map, key=lambda rival: rival.threat)


def _facility_from_command(command: str) -> str:
    if "粮仓" in command:
        return "粮仓"
    if "工厂" in command or "工坊" in command:
        return "工坊"
    if "道路" in command:
        return "道路"
    if "哨塔" in command:
        return "哨塔"
    if "军营" in command:
        return "军营"
    return "要塞"


def _province_with_facility(province: Province, facility: str) -> Province:
    facilities = list(dict.fromkeys([*province.facilities, facility]))
    output = dict(province.output)
    if facility in {"要塞", "哨塔", "军营"}:
        output["army_power"] = output.get("army_power", 0) + 15
    elif facility in {"粮仓", "道路"}:
        output["stability"] = output.get("stability", 0) + 2
    else:
        output["treasury"] = output.get("treasury", 0) + 5
    return province.model_copy(update={"facilities": facilities, "output": output})


def _frontier_name(state: GameState) -> str:
    if state.world_metadata.setting == "黑暗奇幻":
        return "裂隙边陲"
    if state.world_metadata.setting == "古典帝国":
        return "新设边郡"
    return "高地边疆"


def _resolve_attack(state: GameState, rival: RivalNation, rng: random.Random) -> dict:
    military_factions = [
        faction
        for faction in state.factions
        if any(keyword in faction.power_origin for keyword in ["军", "武力", "骑士"])
        or any(keyword in "".join(faction.interests) for keyword in ["军饷", "战争", "边境"])
    ]
    faction_bonus = 0
    if military_factions:
        avg_approval = sum(faction.approval for faction in military_factions) / len(military_factions)
        faction_bonus = round((avg_approval - 50) * 1.5)
    tech_bonus = state.my_nation.tech_level * 25
    mobilization_bonus = state.my_nation.mobilization * 3
    exhaustion_penalty = state.my_nation.war_exhaustion * 2
    roll = rng.randint(-80, 80)
    player_score = (
        state.my_nation.army_power
        + tech_bonus
        + mobilization_bonus
        + faction_bonus
        - exhaustion_penalty
        + roll
    )
    enemy_score = rival.true_power + rng.randint(-60, 60)
    margin = player_score - enemy_score

    if margin >= 120:
        outcome = "胜利"
        prestige = 10
        stability = 1
        treasury = -18
        army_loss = -70
        enemy_loss = -110
        threat_delta = -14
        relations_delta = -18
        tension = 10
    elif margin >= 0:
        outcome = "惨胜"
        prestige = 6
        stability = -3
        treasury = -24
        army_loss = -120
        enemy_loss = -90
        threat_delta = -7
        relations_delta = -22
        tension = 12
    elif margin >= -120:
        outcome = "僵持"
        prestige = -2
        stability = -4
        treasury = -18
        army_loss = -95
        enemy_loss = -65
        threat_delta = 5
        relations_delta = -16
        tension = 8
    else:
        outcome = "失败"
        prestige = -9
        stability = -8
        treasury = -20
        army_loss = -150
        enemy_loss = -40
        threat_delta = 12
        relations_delta = -20
        tension = 14

    summary = (
        f"战报：对{rival.name}的行动结果为{outcome}。"
        f"我方评分 {player_score}，敌方评分 {enemy_score}。"
    )
    return {
        "treasury": treasury,
        "stability": stability,
        "prestige": prestige,
        "tension": tension,
        "summary": summary,
        "nation_change": NationChange(
            army_power_delta=army_loss,
            war_exhaustion_delta=8 if outcome in {"胜利", "惨胜"} else 12,
            reason=summary,
        ),
        "rival_change": RivalChange(
            nation_id=rival.nation_id,
            visible_power_delta=enemy_loss,
            true_power_delta=enemy_loss,
            threat_delta=threat_delta,
            relations_delta=relations_delta,
            stance="War",
            war_status="war" if outcome in {"僵持", "失败"} else "border_conflict",
            reason=summary,
        ),
        "event": ExternalEvent(
            category="war",
            title=f"对{rival.name}的军事行动：{outcome}",
            description=summary,
            nation_id=rival.nation_id,
        ),
    }


def _economy_report(stat_delta: StatDelta) -> str:
    if stat_delta.treasury > 0:
        return f"本回合财政净增 {stat_delta.treasury}。"
    if stat_delta.treasury < 0:
        return f"本回合财政支出 {-stat_delta.treasury}。"
    return "财政收支基本持平。"


def _intel_report(state: GameState) -> str:
    return state.intel_reports[-1] if state.intel_reports else "没有新的可靠情报。"


def _military_report(state: GameState) -> str:
    return (
        f"常备军战力约 {state.my_nation.army_power}，"
        f"动员 {state.my_nation.mobilization}，战争疲劳 {state.my_nation.war_exhaustion}。"
    )


def _world_narrative(events: list[ExternalEvent], report: EndTurnReport) -> str:
    if events:
        event_text = "\n".join(f"- {event.title}：{event.description}" for event in events)
        return f"\n\n外部局势：\n{event_text}"
    return f"\n\n外部局势：{report.border}"

