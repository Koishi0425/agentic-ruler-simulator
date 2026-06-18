from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .models import GameState, GameSummary, TurnRecord
from .world import ensure_world_state


class GameNotFoundError(Exception):
    pass


class TurnNotFoundError(Exception):
    pass


class GameStore:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS games (
                    game_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    current_turn INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS turns (
                    game_id TEXT NOT NULL,
                    turn_number INTEGER NOT NULL,
                    command TEXT NOT NULL,
                    narrative TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    resolution_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (game_id, turn_number),
                    FOREIGN KEY (game_id) REFERENCES games(game_id) ON DELETE CASCADE
                )
                """
            )

    def create_game(self, title: str, state: GameState, opening_narrative: str) -> str:
        now = datetime.now(UTC).isoformat()
        game_id = state.game_id or str(uuid.uuid4())
        state.game_id = game_id
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO games (game_id, title, current_turn, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (game_id, title, state.turn_number, now, now),
            )
            conn.execute(
                """
                INSERT INTO turns (
                    game_id, turn_number, command, narrative, state_json,
                    resolution_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    game_id,
                    0,
                    "START GAME",
                    opening_narrative,
                    state.model_dump_json(),
                    json.dumps({"opening_narrative": opening_narrative}, ensure_ascii=False),
                    now,
                ),
            )
        return game_id

    def list_games(self) -> list[GameSummary]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT game_id, title, current_turn, created_at, updated_at
                FROM games
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [
            GameSummary(
                game_id=row["game_id"],
                title=row["title"],
                current_turn=row["current_turn"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            for row in rows
        ]

    def get_state(self, game_id: str) -> GameState:
        with self.connect() as conn:
            game = conn.execute(
                "SELECT current_turn FROM games WHERE game_id = ?", (game_id,)
            ).fetchone()
            if not game:
                raise GameNotFoundError(game_id)
            row = conn.execute(
                """
                SELECT state_json FROM turns
                WHERE game_id = ? AND turn_number = ?
                """,
                (game_id, game["current_turn"]),
            ).fetchone()
        if not row:
            raise TurnNotFoundError(f"{game_id}@{game['current_turn']}")
        return ensure_world_state(GameState.model_validate_json(row["state_json"]))

    def save_turn(
        self,
        game_id: str,
        turn_number: int,
        command: str,
        narrative: str,
        state: GameState,
        resolution_json: str,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with self.connect() as conn:
            game = conn.execute(
                "SELECT game_id FROM games WHERE game_id = ?", (game_id,)
            ).fetchone()
            if not game:
                raise GameNotFoundError(game_id)
            conn.execute(
                """
                INSERT OR REPLACE INTO turns (
                    game_id, turn_number, command, narrative, state_json,
                    resolution_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    game_id,
                    turn_number,
                    command,
                    narrative,
                    state.model_dump_json(),
                    resolution_json,
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE games
                SET current_turn = ?, updated_at = ?
                WHERE game_id = ?
                """,
                (turn_number, now, game_id),
            )

    def list_turns(self, game_id: str) -> list[TurnRecord]:
        with self.connect() as conn:
            game = conn.execute(
                "SELECT game_id FROM games WHERE game_id = ?", (game_id,)
            ).fetchone()
            if not game:
                raise GameNotFoundError(game_id)
            rows = conn.execute(
                """
                SELECT turn_number, command, narrative, resolution_json, created_at
                FROM turns
                WHERE game_id = ?
                ORDER BY turn_number ASC
                """,
                (game_id,),
            ).fetchall()
        return [
            TurnRecord(
                turn_number=row["turn_number"],
                command=row["command"],
                narrative=row["narrative"],
                created_at=datetime.fromisoformat(row["created_at"]),
                resolution=json.loads(row["resolution_json"]),
            )
            for row in rows
        ]

    def rollback(self, game_id: str, turn_number: int) -> GameState:
        with self.connect() as conn:
            game = conn.execute(
                "SELECT game_id FROM games WHERE game_id = ?", (game_id,)
            ).fetchone()
            if not game:
                raise GameNotFoundError(game_id)
            row = conn.execute(
                """
                SELECT state_json FROM turns
                WHERE game_id = ? AND turn_number = ?
                """,
                (game_id, turn_number),
            ).fetchone()
            if not row:
                raise TurnNotFoundError(f"{game_id}@{turn_number}")
            now = datetime.now(UTC).isoformat()
            conn.execute(
                "DELETE FROM turns WHERE game_id = ? AND turn_number > ?",
                (game_id, turn_number),
            )
            conn.execute(
                """
                UPDATE games
                SET current_turn = ?, updated_at = ?
                WHERE game_id = ?
                """,
                (turn_number, now, game_id),
            )
        return ensure_world_state(GameState.model_validate_json(row["state_json"]))
