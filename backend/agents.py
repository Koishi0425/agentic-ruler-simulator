from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel

from .models import (
    ArbiterResolution,
    Faction,
    FactionChange,
    FactionReaction,
    GameCreateRequest,
    GameState,
    GlobalStats,
    HistoryEntry,
    Leader,
    StatDelta,
    TurnResolution,
    WorldMetadata,
    clamp,
)
from .settings import Settings


ModelT = TypeVar("ModelT", bound=BaseModel)


PRESET_SCENARIOS = {
    "架空中世纪": "一个刚经历继承危机的封建王国，贵族、教会、行会与边境军镇彼此牵制。",
    "古典帝国": "一个横跨内海的古典帝国，元老院、军团、行省总督与神庙集团争夺国家方向。",
    "黑暗奇幻": "一个被灾厄侵蚀的王座，旧贵族、猎巫团、秘法学院与边民共同面对未知威胁。",
}


@dataclass
class LLMGateway:
    settings: Settings

    @property
    def real_llm_available(self) -> bool:
        if self.settings.use_mock_llm or not self.settings.openai_api_key:
            return False
        try:
            import langchain_openai  # noqa: F401
        except Exception:
            return False
        return True

    async def structured(self, schema: type[ModelT], messages: list[tuple[str, str]]) -> ModelT:
        if not self.real_llm_available:
            raise RuntimeError("Real LLM is not configured.")

        from langchain_openai import ChatOpenAI

        kwargs = {
            "model": self.settings.openai_model,
            "api_key": self.settings.openai_api_key,
            "temperature": 0.7,
            "timeout": self.settings.llm_timeout_seconds,
        }
        if self.settings.openai_base_url:
            kwargs["base_url"] = self.settings.openai_base_url

        llm = ChatOpenAI(**kwargs)
        structured_llm = llm.with_structured_output(schema)
        return await asyncio.wait_for(
            structured_llm.ainvoke(messages),
            timeout=self.settings.llm_timeout_seconds + 5,
        )


class AgentOrchestrator:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.llm = LLMGateway(settings)

    async def create_game(self, request: GameCreateRequest) -> tuple[GameState, str]:
        if self.llm.real_llm_available:
            try:
                return await self._create_game_with_llm(request)
            except Exception:
                return self._create_game_mock(request)
        return self._create_game_mock(request)

    async def resolve_turn(self, state: GameState, command: str) -> TurnResolution:
        reactions = await asyncio.gather(
            *[self._react_as_faction(state, faction, command) for faction in state.factions]
        )
        if self.llm.real_llm_available:
            try:
                arbiter = await self._resolve_with_llm(state, command, reactions)
            except Exception:
                arbiter = self._resolve_mock(state, command, reactions)
        else:
            arbiter = self._resolve_mock(state, command, reactions)
        next_state = self._apply_resolution(state, command, arbiter)
        return TurnResolution(
            game_id=state.game_id,
            turn_number=next_state.turn_number,
            command=command,
            reactions=reactions,
            narrative=arbiter.narrative,
            stat_changes=arbiter.stat_changes,
            faction_changes=arbiter.faction_changes,
            state=next_state,
        )

    async def _create_game_with_llm(self, request: GameCreateRequest) -> tuple[GameState, str]:
        scenario = self._scenario_text(request)
        messages = [
            (
                "system",
                "你是 Agentic Ruler Simulator 的 Arbiter。请生成一个中文策略游戏开局，输出必须符合结构。",
            ),
            (
                "human",
                f"统治者：{request.ruler_name}\n剧本：{scenario}\n生成 3-5 个派系、初始危机和开场叙事。",
            ),
        ]

        class InitialWorld(BaseModel):
            world_metadata: WorldMetadata
            global_stats: GlobalStats
            factions: list[Faction]
            current_crises: list[str]
            opening_narrative: str

        world = await self.llm.structured(InitialWorld, messages)
        game_id = str(uuid.uuid4())
        state = GameState(
            game_id=game_id,
            turn_number=0,
            world_metadata=world.world_metadata,
            global_stats=world.global_stats,
            factions=world.factions[:5],
            current_crises=world.current_crises[:5],
            history_log=[
                HistoryEntry(
                    turn_number=0,
                    title="王座初立",
                    command="START GAME",
                    summary=world.opening_narrative,
                )
            ],
        )
        return state, world.opening_narrative

    def _create_game_mock(self, request: GameCreateRequest) -> tuple[GameState, str]:
        scenario = self._scenario_text(request)
        preset = request.preset if request.preset in PRESET_SCENARIOS else "架空中世纪"
        if preset == "古典帝国":
            metadata = WorldMetadata(
                setting="古典帝国",
                era="内海霸权的裂隙年代",
                key_resource="粮秣",
                ruler_name=request.ruler_name,
                scenario_prompt=scenario,
            )
            factions = [
                Faction(
                    id="fac_senate",
                    name="元老院贵族",
                    power_origin="法统与财富",
                    interests=["维持贵族特权", "控制税赋", "限制军人干政"],
                    clout=32,
                    approval=55,
                    leader=Leader(name="卢修斯·瓦罗", traits=["傲慢", "谨慎"]),
                    memory_summary="他们记得每一位绕过元老院的执政官。",
                ),
                Faction(
                    id="fac_legions",
                    name="边境军团",
                    power_origin="武力",
                    interests=["军饷", "荣誉", "边境扩张"],
                    clout=30,
                    approval=58,
                    leader=Leader(name="盖娅·马尔凯拉", traits=["鲁莽", "忠诚"]),
                    memory_summary="军团以胜利和按时发饷衡量王座。",
                ),
                Faction(
                    id="fac_temples",
                    name="神庙同盟",
                    power_origin="信仰",
                    interests=["祭祀预算", "道德秩序", "神权豁免"],
                    clout=18,
                    approval=60,
                    leader=Leader(name="大祭司塞维娅", traits=["神秘", "顽固"]),
                    memory_summary="神庙相信天象比诏书更长久。",
                ),
                Faction(
                    id="fac_provinces",
                    name="行省总督",
                    power_origin="地方行政",
                    interests=["自治权", "贸易安全", "低税负"],
                    clout=20,
                    approval=50,
                    leader=Leader(name="提图斯·阿奎拉", traits=["务实", "贪婪"]),
                    memory_summary="他们总在计算首都还能给地方留下多少余地。",
                ),
            ]
        elif preset == "黑暗奇幻":
            metadata = WorldMetadata(
                setting="黑暗奇幻",
                era="灾厄阴影下的摄政年代",
                key_resource="圣火余烬",
                ruler_name=request.ruler_name,
                scenario_prompt=scenario,
            )
            factions = [
                Faction(
                    id="fac_nobles",
                    name="旧血贵族",
                    power_origin="土地与血统",
                    interests=["封地完整", "继承特权", "排斥新贵"],
                    clout=28,
                    approval=52,
                    leader=Leader(name="灰堡女伯爵伊莲", traits=["冷酷", "守旧"]),
                    memory_summary="他们把每一次让步都视为王权软弱的证据。",
                ),
                Faction(
                    id="fac_witchhunters",
                    name="猎巫团",
                    power_origin="武装信仰",
                    interests=["清剿异端", "扩大审判权", "获得补给"],
                    clout=26,
                    approval=62,
                    leader=Leader(name="铁面审判官罗恩", traits=["狂热", "强硬"]),
                    memory_summary="他们只相信火焰净化后的沉默。",
                ),
                Faction(
                    id="fac_mages",
                    name="秘法学院",
                    power_origin="知识与魔法",
                    interests=["研究自由", "遗物开掘", "免受审判"],
                    clout=22,
                    approval=48,
                    leader=Leader(name="星塔院长梅瑞尔", traits=["理性", "野心"]),
                    memory_summary="学院认为灾厄是问题，也是机会。",
                ),
                Faction(
                    id="fac_frontier",
                    name="边民盟约",
                    power_origin="边境生存网络",
                    interests=["减税", "防线修复", "粮食支援"],
                    clout=24,
                    approval=56,
                    leader=Leader(name="狼渡镇长卡德", traits=["坚韧", "多疑"]),
                    memory_summary="边民相信首都的承诺通常来得太晚。",
                ),
            ]
        else:
            metadata = WorldMetadata(
                setting="架空中世纪",
                era="继承危机后的摄政初年",
                key_resource="银税",
                ruler_name=request.ruler_name,
                scenario_prompt=scenario,
            )
            factions = [
                Faction(
                    id="fac_nobility",
                    name="高地诸侯",
                    power_origin="封地与骑士",
                    interests=["维护封臣特权", "降低王室税负", "扩大领地自治"],
                    clout=34,
                    approval=52,
                    leader=Leader(name="罗德里克公爵", traits=["骄傲", "顽固"]),
                    memory_summary="诸侯刚在继承会议上勉强承认新王。",
                ),
                Faction(
                    id="fac_clergy",
                    name="圣坛教会",
                    power_origin="信仰与教育",
                    interests=["教产豁免", "道德权威", "救济预算"],
                    clout=24,
                    approval=64,
                    leader=Leader(name="奥蕾莉亚主教", traits=["仁慈", "精明"]),
                    memory_summary="教会愿意祝福王冠，但不愿成为王室的钱袋。",
                ),
                Faction(
                    id="fac_guilds",
                    name="自由行会",
                    power_origin="贸易与工坊",
                    interests=["商路安全", "低关税", "城市自治"],
                    clout=22,
                    approval=57,
                    leader=Leader(name="铸币师贝伦", traits=["务实", "贪婪"]),
                    memory_summary="行会在内战中借给王室一大笔钱。",
                ),
                Faction(
                    id="fac_marshal",
                    name="王家军镇",
                    power_origin="常备军",
                    interests=["军饷", "边境要塞", "战争荣耀"],
                    clout=20,
                    approval=60,
                    leader=Leader(name="女元帅塞拉", traits=["忠诚", "急躁"]),
                    memory_summary="军镇认为和平只是在为下一场战争做准备。",
                ),
            ]

        game_id = str(uuid.uuid4())
        opening = (
            f"{metadata.ruler_name}登上王座时，{metadata.era}仍在宫廷的石墙间回响。"
            f"国库尚可支撑数季，民心却还在观望。{metadata.key_resource}成为所有争论的核心，"
            "每个派系都愿意献上忠诚，也都在等待一个能证明王权方向的决定。"
        )
        state = GameState(
            game_id=game_id,
            turn_number=0,
            world_metadata=metadata,
            global_stats=GlobalStats(treasury=100, stability=72, prestige=50, legitimacy=58),
            factions=factions,
            current_crises=["继承合法性仍受质疑", "边境补给线紧张", "首都物价上涨"],
            history_log=[
                HistoryEntry(
                    turn_number=0,
                    title="王座初立",
                    command="START GAME",
                    summary=opening,
                )
            ],
        )
        return state, opening

    async def _react_as_faction(
        self, state: GameState, faction: Faction, command: str
    ) -> FactionReaction:
        if self.llm.real_llm_available:
            try:
                messages = [
                    (
                        "system",
                        "你是一个策略游戏派系 Agent。根据派系利益和领袖人格，用中文输出结构化反馈。",
                    ),
                    (
                        "human",
                        json.dumps(
                            {
                                "game_state": state.model_dump(mode="json"),
                                "faction": faction.model_dump(mode="json"),
                                "player_command": command,
                            },
                            ensure_ascii=False,
                        ),
                    ),
                ]
                return await self.llm.structured(FactionReaction, messages)
            except Exception:
                return self._react_mock(state, faction, command)
        return self._react_mock(state, faction, command)

    def _react_mock(
        self, state: GameState, faction: Faction, command: str
    ) -> FactionReaction:
        lower_command = command.lower()
        text = command
        stance: str = "neutral"
        approval_delta = 0
        clout_delta = 0
        treasury = 0
        stability = 0
        prestige = 0
        legitimacy = 0

        interest_hits = sum(1 for interest in faction.interests if interest[:2] in text)
        if any(keyword in text for keyword in ["加税", "征税", "提高税", "关税"]):
            treasury += 12
            approval_delta -= 6
            stability -= 2
            stance = "oppose" if "低税" in "".join(faction.interests) or "减税" in "".join(faction.interests) else "bargain"
        if any(keyword in text for keyword in ["军", "边境", "要塞", "战争", "征兵"]):
            if any(origin in faction.power_origin for origin in ["武力", "常备军"]) or "军饷" in faction.interests:
                approval_delta += 8
                clout_delta += 2
                prestige += 4
                stance = "support"
            else:
                approval_delta -= 2
        if any(keyword in text for keyword in ["教会", "神庙", "信仰", "祭祀", "救济"]):
            if any(origin in faction.power_origin for origin in ["信仰", "武装信仰"]) or "道德权威" in faction.interests:
                approval_delta += 8
                legitimacy += 3
                stance = "support"
            else:
                approval_delta -= 1
        if any(keyword in text for keyword in ["贸易", "商路", "工坊", "城市", "市场"]):
            if any(origin in faction.power_origin for origin in ["贸易", "财富"]) or "商路安全" in faction.interests:
                approval_delta += 8
                treasury += 4
                stance = "support"
            else:
                approval_delta -= 1
        if any(keyword in text for keyword in ["自治", "特权", "贵族", "封臣", "元老院"]):
            if any(word in "".join(faction.interests) for word in ["特权", "自治"]):
                approval_delta += 7
                legitimacy -= 2
                stance = "support"
            else:
                approval_delta -= 3
        if any(keyword in lower_command for keyword in ["purge", "execute"]) or any(
            keyword in text for keyword in ["处决", "清洗", "镇压"]
        ):
            stability -= 8
            prestige += 3
            approval_delta += 3 if faction.approval > 60 else -7
            stance = "bargain" if approval_delta > 0 else "oppose"
        if interest_hits:
            approval_delta += min(6, interest_hits * 2)
            stance = "support" if approval_delta > 0 else stance

        if stance == "neutral" and approval_delta < 0:
            stance = "oppose"
        elif stance == "neutral" and approval_delta > 0:
            stance = "support"
        elif stance == "neutral":
            stance = "bargain"

        tone = self._tone_for(faction)
        statement = (
            f"{faction.leader.name}{tone}："
            f"“{self._stance_sentence(stance, faction, command)}”"
        )
        demand = self._demand_for(faction, stance)
        return FactionReaction(
            faction_id=faction.id,
            stance=stance,  # type: ignore[arg-type]
            public_statement=statement,
            private_intent=f"{faction.name}会把这项政策记入自己的利益账本。",
            demand=demand,
            proposed_stat_effects=StatDelta(
                treasury=treasury,
                stability=stability,
                prestige=prestige,
                legitimacy=legitimacy,
            ),
            proposed_faction_change=FactionChange(
                faction_id=faction.id,
                approval_delta=approval_delta,
                clout_delta=clout_delta,
                reason=demand,
            ),
        )

    async def _resolve_with_llm(
        self, state: GameState, command: str, reactions: list[FactionReaction]
    ) -> ArbiterResolution:
        messages = [
            (
                "system",
                "你是 The Arbiter，中枢协调者。综合派系反馈，输出严格结构化的回合结算。",
            ),
            (
                "human",
                json.dumps(
                    {
                        "game_state": state.model_dump(mode="json"),
                        "player_command": command,
                        "faction_reactions": [
                            reaction.model_dump(mode="json") for reaction in reactions
                        ],
                    },
                    ensure_ascii=False,
                ),
            ),
        ]
        return await self.llm.structured(ArbiterResolution, messages)

    def _resolve_mock(
        self, state: GameState, command: str, reactions: list[FactionReaction]
    ) -> ArbiterResolution:
        stat_changes = StatDelta()
        faction_changes: list[FactionChange] = []
        support = 0
        oppose = 0
        for reaction in reactions:
            stat_changes.treasury += reaction.proposed_stat_effects.treasury
            stat_changes.stability += reaction.proposed_stat_effects.stability
            stat_changes.prestige += reaction.proposed_stat_effects.prestige
            stat_changes.legitimacy += reaction.proposed_stat_effects.legitimacy
            faction_changes.append(reaction.proposed_faction_change)
            support += 1 if reaction.stance == "support" else 0
            oppose += 1 if reaction.stance == "oppose" else 0

        stat_changes.treasury = round(stat_changes.treasury / max(1, len(reactions)))
        stat_changes.stability = round(stat_changes.stability / max(1, len(reactions)))
        stat_changes.prestige = round(stat_changes.prestige / max(1, len(reactions)))
        stat_changes.legitimacy = round(stat_changes.legitimacy / max(1, len(reactions)))

        if support > oppose:
            stat_changes.legitimacy += 2
            mood = "多数派系暂时接受了王座的方向"
        elif oppose > support:
            stat_changes.stability -= 3
            mood = "宫廷里的反对声开始连成一片"
        else:
            mood = "各方态度分裂，政策仍悬在权力天平上"

        narrative = (
            f"你宣布：{command}\n\n"
            f"{mood}。账房、传令官与侍从在殿门之间奔走，"
            "每个人都知道这不是一个孤立命令，而是一条新的因果链。"
        )
        crisis_changes = list(state.current_crises)
        if stat_changes.stability < -5 and "地方骚动扩大" not in crisis_changes:
            crisis_changes.append("地方骚动扩大")
        if stat_changes.treasury > 8:
            crisis_changes = [c for c in crisis_changes if c != "首都物价上涨"]
        return ArbiterResolution(
            narrative=narrative,
            stat_changes=stat_changes,
            faction_changes=faction_changes,
            crisis_changes=crisis_changes[:5],
            history_title=f"第 {state.turn_number + 1} 回合政令",
            history_summary=mood,
        )

    def _apply_resolution(
        self, state: GameState, command: str, resolution: ArbiterResolution
    ) -> GameState:
        stats = state.global_stats.model_copy(
            update={
                "treasury": clamp(
                    state.global_stats.treasury + resolution.stat_changes.treasury, 0, 999
                ),
                "stability": clamp(
                    state.global_stats.stability + resolution.stat_changes.stability
                ),
                "prestige": clamp(
                    state.global_stats.prestige + resolution.stat_changes.prestige
                ),
                "legitimacy": clamp(
                    state.global_stats.legitimacy + resolution.stat_changes.legitimacy
                ),
            }
        )
        change_by_id = {change.faction_id: change for change in resolution.faction_changes}
        factions: list[Faction] = []
        for faction in state.factions:
            change = change_by_id.get(faction.id)
            if not change:
                factions.append(faction)
                continue
            memory = faction.memory_summary
            if change.reason:
                memory = f"{memory} 最近一次政令影响：{change.reason}"[-240:]
            factions.append(
                faction.model_copy(
                    update={
                        "approval": clamp(faction.approval + change.approval_delta),
                        "clout": clamp(faction.clout + change.clout_delta),
                        "memory_summary": memory,
                    }
                )
            )
        next_turn = state.turn_number + 1
        history = [
            *state.history_log[-19:],
            HistoryEntry(
                turn_number=next_turn,
                title=resolution.history_title,
                command=command,
                summary=resolution.history_summary,
            ),
        ]
        return state.model_copy(
            deep=True,
            update={
                "turn_number": next_turn,
                "global_stats": stats,
                "factions": factions,
                "current_crises": resolution.crisis_changes[:5],
                "history_log": history,
            },
        )

    def _scenario_text(self, request: GameCreateRequest) -> str:
        base = PRESET_SCENARIOS.get(request.preset, PRESET_SCENARIOS["架空中世纪"])
        custom = request.custom_setting.strip()
        return f"{base}\n玩家补充：{custom}" if custom else base

    def _tone_for(self, faction: Faction) -> str:
        traits = set(faction.leader.traits)
        if traits & {"鲁莽", "急躁", "强硬", "狂热"}:
            return "猛地按住桌沿"
        if traits & {"谨慎", "精明", "务实", "理性"}:
            return "低声权衡片刻"
        if traits & {"冷酷", "傲慢", "骄傲"}:
            return "抬起下巴"
        return "缓缓开口"

    def _stance_sentence(self, stance: str, faction: Faction, command: str) -> str:
        if stance == "support":
            return f"{faction.name}可以支持这道命令，但王座应记得谁承担了代价。"
        if stance == "oppose":
            return f"这道命令会伤到我们的根基，若强行推进，宫廷不会安静。"
        if stance == "bargain":
            return f"方向并非不可接受，但我们需要补偿、承诺，或者一个更体面的说法。"
        return f"我们会观察它如何落地，再决定是否把沉默变成支持。"

    def _demand_for(self, faction: Faction, stance: str) -> str:
        first_interest = faction.interests[0] if faction.interests else "获得明确承诺"
        if stance == "support":
            return f"希望王座后续优先考虑：{first_interest}"
        if stance == "oppose":
            return f"要求撤回或缓和政策，并保障：{first_interest}"
        return f"愿意谈判，但条件围绕：{first_interest}"
