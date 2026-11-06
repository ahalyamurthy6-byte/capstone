from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    SMALL_MODEL: str = "ollama:qwen2.5:3b"
    MID_MODEL: str = "ollama:qwen2.5:7b"
    JUDGE_MODEL: str = "ollama:llama3.1:8b"
    EMBED_MODEL: str = "nomic-embed-text"
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    PHOENIX_ENDPOINT: str = "http://localhost:6006"
    DOCS_DIR: str = "./data/uploads"
    MCP_MODE: str = "http"
    MCP_HOST: str = "localhost"
    TRACING: str = "on"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
