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


class Province(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    province_type: str = Field(min_length=1)
    facilities: list[str] = Field(default_factory=list)
    output: dict[str, int] = Field(default_factory=dict)
    adjacent_targets: list[str] = Field(default_factory=list)


class MyNation(BaseModel):
    provinces: list[Province] = Field(default_factory=list)
    army_power: int = Field(default=500, ge=0, le=5000)
    tech_level: int = Field(default=2, ge=1, le=10)
    mobilization: int = Field(default=0, ge=0, le=100)
    war_exhaustion: int = Field(default=0, ge=0, le=100)


class RivalNation(BaseModel):
    nation_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    stance: Literal["Hostile", "Neutral", "Ally", "War"]
    visible_power: int = Field(ge=0, le=5000)
    true_power: int = Field(ge=0, le=5000)
    threat: int = Field(ge=0, le=100)
    relations: int = Field(ge=-100, le=100)
    description: str = ""
    war_status: Literal["peace", "border_conflict", "war"] = "peace"
    claims: list[str] = Field(default_factory=list)
    fog_of_war: int = Field(default=35, ge=0, le=100)


class ActionIntent(BaseModel):
    action_type: Literal[
        "expand",
        "diplomacy",
        "mobilize",
        "build",
        "attack",
        "domestic_policy",
    ]
    target: str = ""
    details: str = ""


class NationChange(BaseModel):
    army_power_delta: int = 0
    tech_level_delta: int = 0
    mobilization_delta: int = 0
    war_exhaustion_delta: int = 0
    added_provinces: list[Province] = Field(default_factory=list)
    province_updates: list[Province] = Field(default_factory=list)
    reason: str = ""


class RivalChange(BaseModel):
    nation_id: str
    visible_power_delta: int = 0
    true_power_delta: int = 0
    threat_delta: int = 0
    relations_delta: int = 0
    stance: Literal["Hostile", "Neutral", "Ally", "War"] | None = None
    war_status: Literal["peace", "border_conflict", "war"] | None = None
    reason: str = ""


class ExternalEvent(BaseModel):
    category: Literal["border", "diplomacy", "war", "trade", "intel", "opportunity"]
    title: str
    description: str
    nation_id: str = ""


class EndTurnReport(BaseModel):
    economy: str = "财政维持惯性，尚无显著变化。"
    border: str = "边境暂时平静。"
    intel: str = "没有新的可靠情报。"
    factions: str = "派系仍在观察王座的方向。"
    military: str = "军队保持常备状态。"


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
    my_nation: MyNation = Field(default_factory=MyNation)
    world_map: list[RivalNation] = Field(default_factory=list)
    world_tension: int = Field(default=25, ge=0, le=100)
    intel_reports: list[str] = Field(default_factory=list)
    end_turn_report: EndTurnReport = Field(default_factory=EndTurnReport)
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
    nation_changes: list[NationChange] = Field(default_factory=list)
    rival_changes: list[RivalChange] = Field(default_factory=list)
    external_events: list[ExternalEvent] = Field(default_factory=list)
    end_turn_report: EndTurnReport = Field(default_factory=EndTurnReport)
    world_tension_delta: int = 0
    intel_updates: list[str] = Field(default_factory=list)
    crisis_changes: list[str] = Field(default_factory=list, max_length=5)
    history_title: str = "未命名回合"
    history_summary: str


class TurnResolution(BaseModel):
    game_id: str
    turn_number: int
    command: str
    action_intents: list[ActionIntent] = Field(default_factory=list)
    reactions: list[FactionReaction]
    narrative: str
    stat_changes: StatDelta
    faction_changes: list[FactionChange]
    nation_changes: list[NationChange] = Field(default_factory=list)
    rival_changes: list[RivalChange] = Field(default_factory=list)
    external_events: list[ExternalEvent] = Field(default_factory=list)
    end_turn_report: EndTurnReport = Field(default_factory=EndTurnReport)
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
