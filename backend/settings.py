from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel


ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")


class Settings(BaseModel):
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    llm_timeout_seconds: float = float(os.getenv("ARS_LLM_TIMEOUT_SECONDS", "600"))
    use_mock_llm: bool = os.getenv("ARS_USE_MOCK_LLM", "").lower() in {
        "1",
        "true",
        "yes",
    }
    database_path: Path = Path(os.getenv("ARS_DATABASE_PATH", ROOT_DIR / "data" / "ars.db"))


def get_settings() -> Settings:
    return Settings()
