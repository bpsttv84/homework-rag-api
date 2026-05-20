"""Application settings from environment."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")

    qdrant_url: str = Field(default="http://localhost:6333", alias="QDRANT_URL")
    qdrant_api_key: str | None = Field(default=None, alias="QDRANT_API_KEY")
    qdrant_chunks_collection: str = Field(default="rag_chunks", alias="QDRANT_CHUNKS_COLLECTION")
    qdrant_cache_collection: str = Field(default="rag_cache", alias="QDRANT_CACHE_COLLECTION")

    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/costs.db",
        alias="DATABASE_URL",
    )

    langfuse_public_key: str | None = Field(default=None, alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str | None = Field(default=None, alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="https://cloud.langfuse.com", alias="LANGFUSE_HOST")

    admin_api_key: str = Field(default="change-me-admin", alias="ADMIN_API_KEY")
    llm_concurrency: int = Field(default=20, alias="LLM_CONCURRENCY")
    embedding_model: str = Field(default="all-MiniLM-L6-v2", alias="EMBEDDING_MODEL")

    data_dir: Path = Field(default=Path("data"))
    source_document: Path = Field(default=Path("data/source.md"))

    cache_similarity_threshold: float = 0.92
    cache_ttl_hours: int = 1
    rag_top_k: int = 3
    max_message_chars: int = 4000
    openrouter_timeout_s: float = 15.0

    @property
    def langfuse_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
