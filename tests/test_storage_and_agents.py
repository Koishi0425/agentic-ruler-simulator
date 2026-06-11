from __future__ import annotations

import asyncio

from backend.agents import AgentOrchestrator
from backend.models import GameCreateRequest
from backend.settings import Settings
from backend.storage import GameStore


def test_store_can_create_turn_list_resolution_and_rollback(tmp_path) -> None:
    settings = Settings(
        use_mock_llm=True,
        database_path=tmp_path / "ars_test.db",
    )
    orchestrator = AgentOrchestrator(settings)
    state, opening = asyncio.run(
        orchestrator.create_game(
            GameCreateRequest(
                preset="架空中世纪",
                custom_setting="",
                ruler_name="测试王",
            )
        )
    )
    store = GameStore(settings.database_path)
    game_id = store.create_game("测试存档", state, opening)

    result = asyncio.run(orchestrator.resolve_turn(state, "加税并修复边境要塞"))
    store.save_turn(
        game_id=game_id,
        turn_number=result.turn_number,
        command=result.command,
        narrative=result.narrative,
        state=result.state,
        resolution_json=result.model_dump_json(),
    )

    latest = store.get_state(game_id)
    assert latest.turn_number == 1

    last_turn = store.list_turns(game_id)[-1]
    assert last_turn.command == "加税并修复边境要塞"
    assert last_turn.resolution["turn_number"] == 1
    assert last_turn.resolution["reactions"]

    rolled_back = store.rollback(game_id, 0)
    assert rolled_back.turn_number == 0
    assert len(store.list_turns(game_id)) == 1


def test_mock_agent_flow_returns_structured_turn(tmp_path) -> None:
    settings = Settings(
        use_mock_llm=True,
        database_path=tmp_path / "ars_test.db",
    )
    orchestrator = AgentOrchestrator(settings)
    state, _ = asyncio.run(
        orchestrator.create_game(
            GameCreateRequest(
                preset="古典帝国",
                custom_setting="",
                ruler_name="执政官",
            )
        )
    )
    result = asyncio.run(orchestrator.resolve_turn(state, "提高关税，补发军团军饷"))

    assert result.turn_number == 1
    assert len(result.reactions) == len(state.factions)
    assert result.state.global_stats.treasury >= 0
    assert all(0 <= faction.approval <= 100 for faction in result.state.factions)

