from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Knowledge Base Configuration
    KB_PATH: Path = Path("./knowledge-bases/default")

    # OpenAI Configuration
    OPENAI_API_KEY: str | None = None
    OPENAI_BASE_URL: str | None = None
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIM: int = 1536

    # System Configuration
    LOG_LEVEL: str = "INFO"
    DUCKDB_CONFIG: dict[str, Any] = {"memory_limit": "2GB", "threads": "4"}

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def model_post_init(self, __context: Any) -> None:
        """Ensure KB_PATH is absolute."""
        if not self.KB_PATH.is_absolute():
            self.KB_PATH = self.KB_PATH.resolve()


settings = Settings()
