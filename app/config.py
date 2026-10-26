"""Runtime configuration, read from environment variables (see docs §12)."""

from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict

HOSPITAL_TZ = ZoneInfo("Asia/Kolkata")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://careflow:careflow@localhost:5432/careflow"

    # LLM providers, "provider:model". Providers: groq, gemini, ollama (NFR-16).
    llm_primary: str = "groq:openai/gpt-oss-120b"
    llm_fallback: str = "gemini:gemini-3.5-flash-lite"
    groq_api_key: str | None = None
    gemini_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    llm_timeout_seconds: float = 30.0
    llm_max_output_tokens: int = 1024  # reasoning models spend part of this before answering

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
    # Encrypts patients' phone numbers (base64 of 32 random bytes). Without it a key is derived from
    # AUTH_SECRET, so changing AUTH_SECRET would make stored numbers unreadable; set both in production.
    data_key: str = ""
    # Anyone may create a patient account; both limits are per client address.
    allow_registration: bool = True
    max_registrations_per_ip_per_hour: int = 10
    max_failed_logins_per_15_min: int = 10

    # Messages by SMS and e-mail (phase 7E). Off unless a provider is chosen here AND an admin turns sending on.
    # SMS: "none", "log" (written to the server log, for trying it out), "twilio" or "webhook" (a POST to the
    # hospital's own SMS gateway). E-mail: "none", "log" or "smtp". Real providers never send in demo mode.
    sms_provider: str = "none"
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from: str = ""
    sms_webhook_url: str = ""
    sms_webhook_secret: str = ""
    email_provider: str = "none"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_security: str = "starttls"  # starttls, ssl or none
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    delivery_timeout_seconds: float = 15.0

    trace_dir: str = "traces"
    warm_up_retriever: bool = True  # load the retrieval models when the API starts

    # FR-22: the merge rule is configurable; "slot_order" = booked patients keep
    # slot order and walk-ins fill gaps, "alternate" = 1:1 booked/walk-in.
    queue_merge_rule: str = "slot_order"

    simulator_seed: int = 42


@lru_cache
def get_settings() -> Settings:
    return Settings()
