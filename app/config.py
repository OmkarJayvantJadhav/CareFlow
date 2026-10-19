"""Runtime configuration, read from environment variables (see docs §12)."""

from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict

HOSPITAL_TZ = ZoneInfo("Asia/Kolkata")
HOSPITAL_NAME = "Indravani General Hospital"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://careflow:careflow@localhost:5432/careflow"

    llm_primary: str = "groq:llama-3.3-70b-versatile"
    llm_fallback: str = "gemini:gemini-2.0-flash"
    groq_api_key: str | None = None
    gemini_api_key: str | None = None

    max_messages_per_session: int = 20
    prompt_token_budget: int = 3000
    rag_top_k: int = 4
    demo_mode: bool = True

    # FR-22: the merge rule is configurable; "slot_order" = booked patients keep
    # slot order and walk-ins fill gaps, "alternate" = 1:1 booked/walk-in.
    queue_merge_rule: str = "slot_order"

    simulator_seed: int = 42


@lru_cache
def get_settings() -> Settings:
    return Settings()
