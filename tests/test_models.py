from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.models import (
    Faction,
    GameState,
    GlobalStats,
    Leader,
    WorldMetadata,
    clamp,
)


def make_faction(faction_id: str) -> Faction:
    return Faction(
        id=faction_id,
        name=f"派系 {faction_id}",
        power_origin="测试权力",
        interests=["测试诉求"],
        clout=30,
        approval=50,
        leader=Leader(name="测试领袖", traits=["谨慎"]),
    )


def test_game_state_requires_unique_faction_ids() -> None:
    with pytest.raises(ValidationError):
        GameState(
            game_id="game",
            turn_number=0,
            world_metadata=WorldMetadata(
                setting="测试世界",
                era="测试时代",
                key_resource="测试资源",
            ),
            global_stats=GlobalStats(
                treasury=100,
                stability=70,
                prestige=50,
                legitimacy=60,
            ),
            factions=[make_faction("fac_1"), make_faction("fac_1"), make_faction("fac_3")],
        )


def test_clamp_keeps_values_in_bounds() -> None:
    assert clamp(-10) == 0
    assert clamp(42) == 42
    assert clamp(120) == 100
    assert clamp(120, 0, 999) == 120

