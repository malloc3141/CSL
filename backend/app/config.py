from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    pipeline: str = "mock"
    # Send exception details to the client in error events. Keep off in production.
    debug: bool = False

    openrouter_api_key: str = ""
    openrouter_model: str = ""
    openrouter_model_fast: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_app_url: str = ""
    openrouter_app_title: str = "CSL"
    llm_concurrency: int = 8
    llm_timeout_seconds: float = 60.0

    database_path: str = "data/csl.db"
    cors_origins: str = "http://localhost:3000"
    access_code: str = ""
    admin_token: str = ""

    # Cost and abuse guards
    max_turns: int = 60
    max_active_sessions: int = 20
    sessions_per_ip_per_hour: int = 30
    max_user_message_chars: int = 2000
    session_idle_minutes: int = 30

    # One pipeline call (select / speak / update) may take at most this long.
    turn_timeout_seconds: float = 90.0

    # Reading time between two agent messages at speed 1.0:
    #   clamp(base + chars * per_char, max)
    pace_base_seconds: float = 2.5
    pace_seconds_per_char: float = 0.06
    pace_max_seconds: float = 20.0

    # Mock pipeline: delay between streamed chunks, to imitate typing.
    mock_chunk_delay: float = 0.03
    # Baseline pipeline: number of peer agents.
    peer_count: int = 2

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
