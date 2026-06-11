from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


def clamp(value: int, minimum: int = 0, maximum: int = 100) -> int:
    return max(minimum, min(maximum, value))


class Leader(BaseModel):
    name: str = Field(min_length=1)
    traits: list[str] = Field(default_factory=list)


class Faction(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    power_origin: str = Field(min_length=1)
    interests: list[str] = Field(default_factory=list)
    clout: int = Field(ge=0, le=100)
    approval: int = Field(ge=0, le=100)
    leader: Leader
    memory_summary: str = ""


class WorldMetadata(BaseModel):
    setting: str = Field(min_length=1)
    era: str = Field(min_length=1)
    key_resource: str = Field(min_length=1)
    ruler_name: str = "无名统治者"
    scenario_prompt: str = ""


class GlobalStats(BaseModel):
    treasury: int = Field(ge=0, le=999)
    stability: int = Field(ge=0, le=100)
    prestige: int = Field(ge=0, le=100)
    legitimacy: int = Field(ge=0, le=100)


class HistoryEntry(BaseModel):
    turn_number: int = Field(ge=0)
    title: str
    command: str
    summary: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GameState(BaseModel):
    game_id: str
    turn_number: int = Field(ge=0)
    world_metadata: WorldMetadata
    global_stats: GlobalStats
    factions: list[Faction] = Field(min_length=3, max_length=5)
    current_crises: list[str] = Field(default_factory=list, max_length=5)
    history_log: list[HistoryEntry] = Field(default_factory=list)

    @field_validator("factions")
    @classmethod
    def faction_ids_must_be_unique(cls, factions: list[Faction]) -> list[Faction]:
        ids = [faction.id for faction in factions]
        if len(ids) != len(set(ids)):
            raise ValueError("Faction ids must be unique.")
        return factions


class StatDelta(BaseModel):
    treasury: int = 0
    stability: int = 0
    prestige: int = 0
    legitimacy: int = 0


class FactionChange(BaseModel):
    faction_id: str
    approval_delta: int = 0
    clout_delta: int = 0
    reason: str = ""


class FactionReaction(BaseModel):
    faction_id: str
    stance: Literal["support", "oppose", "bargain", "neutral"]
    public_statement: str
    private_intent: str = ""
    demand: str = ""
    proposed_stat_effects: StatDelta = Field(default_factory=StatDelta)
    proposed_faction_change: FactionChange


class ArbiterResolution(BaseModel):
    narrative: str
    stat_changes: StatDelta = Field(default_factory=StatDelta)
    faction_changes: list[FactionChange] = Field(default_factory=list)
    crisis_changes: list[str] = Field(default_factory=list, max_length=5)
    history_title: str = "未命名回合"
    history_summary: str


class TurnResolution(BaseModel):
    game_id: str
    turn_number: int
    command: str
    reactions: list[FactionReaction]
    narrative: str
    stat_changes: StatDelta
    faction_changes: list[FactionChange]
    state: GameState


class GameCreateRequest(BaseModel):
    preset: str = "架空中世纪"
    custom_setting: str = ""
    ruler_name: str = "无名统治者"


class TurnRequest(BaseModel):
    command: str = Field(min_length=1, max_length=2000)


class RollbackRequest(BaseModel):
    turn_number: int = Field(ge=0)


class GameSummary(BaseModel):
    game_id: str
    title: str
    current_turn: int
    created_at: datetime
    updated_at: datetime


class GameCreateResponse(BaseModel):
    game_id: str
    opening_narrative: str
    state: GameState


class TurnRecord(BaseModel):
    turn_number: int
    command: str
    narrative: str
    created_at: datetime
    resolution: dict[str, Any] = Field(default_factory=dict)
