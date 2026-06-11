from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .agents import AgentOrchestrator
from .models import (
    GameCreateRequest,
    GameCreateResponse,
    GameState,
    GameSummary,
    RollbackRequest,
    TurnRecord,
    TurnRequest,
    TurnResolution,
)
from .settings import Settings, get_settings
from .storage import GameNotFoundError, GameStore, TurnNotFoundError


app = FastAPI(title="Agentic Ruler Simulator", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_store(settings: Settings = Depends(get_settings)) -> GameStore:
    return GameStore(settings.database_path)


def get_orchestrator(settings: Settings = Depends(get_settings)) -> AgentOrchestrator:
    return AgentOrchestrator(settings)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/games", response_model=GameCreateResponse)
async def create_game(
    request: GameCreateRequest,
    store: GameStore = Depends(get_store),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
) -> GameCreateResponse:
    state, opening = await orchestrator.create_game(request)
    title = f"{state.world_metadata.setting} · {state.world_metadata.ruler_name}"
    game_id = store.create_game(title=title, state=state, opening_narrative=opening)
    state.game_id = game_id
    return GameCreateResponse(game_id=game_id, opening_narrative=opening, state=state)


@app.get("/api/games", response_model=list[GameSummary])
def list_games(store: GameStore = Depends(get_store)) -> list[GameSummary]:
    return store.list_games()


@app.get("/api/games/{game_id}/state", response_model=GameState)
def get_state(game_id: str, store: GameStore = Depends(get_store)) -> GameState:
    try:
        return store.get_state(game_id)
    except GameNotFoundError:
        raise HTTPException(status_code=404, detail="Save not found.") from None
    except TurnNotFoundError:
        raise HTTPException(status_code=404, detail="Turn not found.") from None


@app.post("/api/games/{game_id}/turns", response_model=TurnResolution)
async def play_turn(
    game_id: str,
    request: TurnRequest,
    store: GameStore = Depends(get_store),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
) -> TurnResolution:
    try:
        state = store.get_state(game_id)
    except GameNotFoundError:
        raise HTTPException(status_code=404, detail="Save not found.") from None
    result = await orchestrator.resolve_turn(state, request.command)
    store.save_turn(
        game_id=game_id,
        turn_number=result.turn_number,
        command=request.command,
        narrative=result.narrative,
        state=result.state,
        resolution_json=result.model_dump_json(),
    )
    return result


@app.get("/api/games/{game_id}/turns", response_model=list[TurnRecord])
def list_turns(game_id: str, store: GameStore = Depends(get_store)) -> list[TurnRecord]:
    try:
        return store.list_turns(game_id)
    except GameNotFoundError:
        raise HTTPException(status_code=404, detail="Save not found.") from None


@app.post("/api/games/{game_id}/rollback", response_model=GameState)
def rollback(
    game_id: str, request: RollbackRequest, store: GameStore = Depends(get_store)
) -> GameState:
    try:
        return store.rollback(game_id, request.turn_number)
    except GameNotFoundError:
        raise HTTPException(status_code=404, detail="Save not found.") from None
    except TurnNotFoundError:
        raise HTTPException(status_code=404, detail="Turn not found.") from None

