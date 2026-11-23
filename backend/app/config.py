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
    # Adresse publique des pages (ex. https://veille.mesoutilsagile.com) : liens dans les messages
    url_publique: str = ""
    # E-mail (Gmail : smtp.gmail.com, port 587, mot de passe d'application)
    smtp_hote: str = ""
    smtp_port: int = 587
    smtp_utilisateur: str = ""
    smtp_mot_de_passe: SecretStr = SecretStr("")
    email_destinataire: str = ""
    email_expediteur: str = ""
    # vps = production : mot de passe des pages obligatoire
    environnement: str = "local"
    # Vide = pas de protection (usage local). Renseigne = pages et API protegees.
    mot_de_passe_pages: SecretStr = SecretStr("")

    @property
    def db_path(self) -> Path:
        p = Path(self.veille_db_path)
        return p if p.is_absolute() else BACKEND_DIR / p


@lru_cache
def get_settings() -> Settings:
    return Settings()
