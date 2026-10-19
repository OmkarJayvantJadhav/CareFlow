"""Runtime configuration, read from environment variables (see docs §12)."""

from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict

HOSPITAL_TZ = ZoneInfo("Asia/Kolkata")
HOSPITAL_NAME = "Indravani General Hospital"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://careflow:careflow@localhost:5432/careflow"

    # LLM providers, "provider:model". Providers: groq, gemini, ollama (NFR-16).
    llm_primary: str = "groq:llama-3.3-70b-versatile"
    llm_fallback: str = "gemini:gemini-2.0-flash"
    groq_api_key: str | None = None
    gemini_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    llm_timeout_seconds: float = 30.0
    llm_max_output_tokens: int = 512

    max_messages_per_session: int = 20
    max_messages_per_ip_per_hour: int = 60
    max_message_chars: int = 1000
    prompt_token_budget: int = 3000
    max_agent_steps: int = 6
    rag_top_k: int = 4
    rag_candidates: int = 12
    demo_mode: bool = True

    # Retrieval models. "auto" uses the neural model when it can be loaded and
    # falls back to the local implementation otherwise; "local" forces the fallback.
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_backend: str = "auto"
    reranker_model: str = "BAAI/bge-reranker-v2-m3-int8"
    reranker_backend: str = "auto"
    model_cache_dir: str | None = None

    # Demo bearer tokens are signed with this secret; set it in production.
    auth_secret: str = "careflow-demo-secret-change-me"
    token_ttl_hours: int = 12

    trace_dir: str = "traces"

    # FR-22: the merge rule is configurable; "slot_order" = booked patients keep
    # slot order and walk-ins fill gaps, "alternate" = 1:1 booked/walk-in.
    queue_merge_rule: str = "slot_order"

    simulator_seed: int = 42


@lru_cache
def get_settings() -> Settings:
    return Settings()
