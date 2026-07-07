"""Настройки приложения из окружения (.env). Pydantic Settings v2."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"
    log_level: str = "INFO"

    # Единственная строка подключения — async-URL приложения (asyncpg).
    # Sync-URL для Alembic выводится из неё (см. database_url_sync). База одна.
    database_url: str = "postgresql+asyncpg://vendors:vendors@localhost:5432/vendors"

    cors_origins: str = "http://localhost:5173"

    # --- OIDC ---
    oidc_issuer: str = ""
    oidc_audience: str = ""
    oidc_jwks_url: str = ""
    oidc_roles_claim: str = "roles"
    oidc_username_claim: str = "preferred_username"

    # --- Dev-обход аутентификации (в prod ОБЯЗАН быть False) ---
    auth_dev_bypass: bool = True
    auth_dev_user: str = "dev@local"
    auth_dev_role: str = "admin"

    @property
    def database_url_sync(self) -> str:
        """Sync-URL для Alembic, выведенный из единственного DATABASE_URL.

        Отличие только в «разъёме»: async-драйвер asyncpg меняем на sync-psycopg,
        а asyncpg-параметр ssl=require — на libpq-шный sslmode=require, понятный
        psycopg. Хост/база/пользователь те же — БД одна.
        """
        url = self.database_url.replace("+asyncpg", "+psycopg")
        return url.replace("ssl=require", "sslmode=require")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()
