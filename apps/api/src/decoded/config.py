from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "decoded-api"
    version: str = "0.1.0"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://decoded:decoded_dev@localhost:5432/decoded"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"

    # Enrichment (all optional — pipeline still runs without them)
    openalex_email: Optional[str] = None  # for polite pool
    semantic_scholar_api_key: Optional[str] = None  # optional but recommended

    llama_cloud_api_key: Optional[str] = None

    openai_api_key: Optional[str] = None
    embedding_model_small: str = "text-embedding-3-small"
    embedding_model_large: str = "text-embedding-3-large"

    anthropic_api_key: Optional[str] = None
    decoder_model_fast: str = "claude-haiku-4-5-20251001"
    decoder_model_deep: str = "claude-sonnet-4-6"
    decoder_prompt_version: str = "v1"

    cors_origins: list[str] = [
        "http://localhost:3000",
        "https://turbo-cod-q4jwrjw96qpc99ww-3000.app.github.dev/",
    ]

    cohere_api_key: Optional[str] = None
    rerank_model: str = "rerank-v3.5"
    search_retrieve_k: int = 40   # candidatos do Qdrant
    search_return_k: int = 10     # resultados finais

    clerk_secret_key: Optional[str] = None
    clerk_jwks_url: Optional[str] = None  # https://SEU-APP.clerk.accounts.dev/.well-known/jwks.json
    clerk_issuer: Optional[str] = None    # https://SEU-APP.clerk.accounts.dev

    langfuse_public_key: Optional[str] = None
    langfuse_secret_key: Optional[str] = None
    langfuse_host: str = "https://cloud.langfuse.com"

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: Optional[str] = None

    mode_prompt_version: str = "v1"
    mode_generation_timeout_s: float = 180.0

    dspy_generator_model: str = "openai/gpt-5.6-luna"
    dspy_judge_model: str = "openai/gpt-5.6-terra"

    openai_analogy_model: str = "gpt-5.6-luna"

    mlflow_tracking_uri: str = "sqlite:///mlflow.db"
    mlflow_experiment_prefix: str = "decoded"

    site_url: str = "http://localhost:3000"
    digest_subject_model: str = "claude-haiku-4-5-20251001"

    resend_api_key: Optional[str] = None
    resend_webhook_secret: Optional[str] = None
    digest_from_email: str = "Decoded <onboarding@resend.dev>"
    digest_reply_to: Optional[str] = None

    # Free tier do Resend: 100/dia, 2 req/s
    digest_send_rate_per_second: float = 2.0
    digest_daily_cap: int = 100

    posthog_api_key: Optional[str] = None
    posthog_host: str = "https://us.i.posthog.com"

    podcast_script_model: str = "claude-sonnet-4-6"

    elevenlabs_api_key: Optional[str] = None
    elevenlabs_voice_id: Optional[str] = None
    elevenlabs_model: str = "eleven_turbo_v2_5"

    r2_account_id: Optional[str] = None
    r2_access_key_id: Optional[str] = None
    r2_secret_access_key: Optional[str] = None
    r2_bucket: str = "decoded-audio"
    r2_public_url: Optional[str] = None

    # Teto de gasto — TTS cobra por caractere
    podcast_daily_budget_usd: float = 3.0

settings = Settings()