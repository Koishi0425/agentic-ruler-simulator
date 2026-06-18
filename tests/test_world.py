from __future__ import annotations

import random

from backend.agents import AgentOrchestrator
from backend.models import GameCreateRequest, GameState
from backend.settings import Settings
from backend.world import (
    ensure_world_state,
    parse_action_intents,
    resolve_world_actions,
)


def make_state() -> GameState:
    settings = Settings(use_mock_llm=True)
    orchestrator = AgentOrchestrator(settings)
    state, _ = __import__("asyncio").run(
        orchestrator.create_game(
            GameCreateRequest(
                preset="架空中世纪",
                custom_setting="",
                ruler_name="测试王",
            )
        )
    )
    return state


def test_new_game_contains_geopolitical_state() -> None:
    state = make_state()

    assert state.my_nation.provinces
    assert len(state.world_map) == 3
    assert state.world_tension > 0
    assert state.end_turn_report.border


def test_legacy_state_is_backfilled() -> None:
    state = make_state()
    payload = state.model_dump()
    payload.pop("my_nation")
    payload.pop("world_map")
    legacy = GameState.model_validate(payload)

    fixed = ensure_world_state(legacy)

    assert fixed.my_nation.provinces
    assert fixed.world_map


def test_parse_strategic_actions() -> None:
    state = make_state()

    intents = parse_action_intents("动员边境军镇并进攻北境汗国", state)

    assert {intent.action_type for intent in intents} >= {"mobilize", "attack"}
    assert any(intent.target == "rival_north" for intent in intents)


def test_diplomacy_reduces_target_threat() -> None:
    state = make_state()
    intents = parse_action_intents("派使者改善与南洋商贸邦联关系", state)

    _, _, rival_changes, _, _, tension_delta, _, _ = resolve_world_actions(
        state, "派使者改善与南洋商贸邦联关系", intents
    )

    change = next(item for item in rival_changes if item.nation_id == "rival_south")
    assert change.threat_delta < 0
    assert change.relations_delta > 0
    assert tension_delta < 0


def test_mobilize_and_build_change_nation() -> None:
    state = make_state()
    command = "动员边境军镇，并在铁矿区修筑要塞"
    intents = parse_action_intents(command, state)

    stats, nation_changes, _, _, _, _, _, _ = resolve_world_actions(state, command, intents)

    assert stats.treasury < 0
    assert sum(change.army_power_delta for change in nation_changes) > 0
    assert any(change.province_updates for change in nation_changes)


def test_attack_generates_war_event_and_losses() -> None:
    state = make_state()
    intents = parse_action_intents("进攻北境汗国边境矿山", state)

    stats, nation_changes, rival_changes, events, _, tension_delta, _, _ = resolve_world_actions(
        state, "进攻北境汗国边境矿山", intents
    )

    assert stats.treasury < 0
    assert sum(change.army_power_delta for change in nation_changes) < 0
    assert any(change.nation_id == "rival_north" for change in rival_changes)
    assert any(event.category == "war" for event in events)
    assert tension_delta > 0
