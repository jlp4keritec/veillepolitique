"""Configuration lue depuis backend/.env (valeurs par defaut modifiables par J)."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Secrets : SecretStr evite qu'ils apparaissent dans les logs
    anthropic_api_key: SecretStr = SecretStr("")
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_chat_id: str = ""

    budget_mensuel_eur: float = Field(default=50.0, ge=0)

    backend_port: int = 8710
    veille_db_path: str = "data/veille.db"
    fuseau_horaire: str = "Europe/Paris"
    scheduler_actif: bool = True
    # Vide = pas de protection (usage local). Renseigne = pages et API protegees.
    mot_de_passe_pages: SecretStr = SecretStr("")

    @property
    def db_path(self) -> Path:
        p = Path(self.veille_db_path)
        return p if p.is_absolute() else BACKEND_DIR / p


@lru_cache
def get_settings() -> Settings:
    return Settings()
