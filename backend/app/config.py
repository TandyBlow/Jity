
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_file: Path = Path("data/jity.sqlite3")
    knowledge_dir: Path = Path("../knowledge")
    rulebook_file: Path = Path("../RULEBOOK.md")
    campaigns_dir: Path = Path("data/campaigns")
    frontend_origin: str = "http://localhost:3000"
    deepseek_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-v4-flash"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
