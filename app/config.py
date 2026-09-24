from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"

    # Transcripts longer than this (in characters) are summarized with map-reduce:
    # each chunk is condensed into timestamped notes, then the notes are summarized.
    chunk_threshold_chars: int = 100_000
    chunk_size_chars: int = 40_000

    cache_ttl_seconds: int = 60 * 60 * 24
    cache_max_entries: int = 256

    # Optional: route transcript requests through a proxy (YouTube often blocks cloud IPs).
    transcript_proxy_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
