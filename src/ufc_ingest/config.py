"""Configuración desde el entorno. Los secretos viven en `.env` (ignorado por git)
o en los secretos de GitHub Actions; nunca en el repositorio."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    database_url: str = "postgresql://postgres:postgres@localhost:55432/postgres"
    schema_dir: Path = ROOT / "schema"


settings = Settings()
