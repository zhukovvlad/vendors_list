"""Настройки приложения из окружения (.env). Pydantic Settings v2."""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"

    # Единственная строка подключения — async-URL приложения (asyncpg).
    # Sync-URL для Alembic выводится из неё (см. database_url_sync). База одна.
    database_url: str = "postgresql+asyncpg://vendors:vendors@localhost:5432/vendors"

    # Тестовая ветка Neon (data+schema). Пусто в prod/обычном dev; задаётся
    # в backend/.env локально и в env CI-джобы. Драйвер asyncpg → хвост ssl=require.
    database_url_test: str = ""

    @field_validator("database_url_test", mode="after")
    @classmethod
    def _normalize_test_url(cls, v: str) -> str:
        """Нормализовать DATABASE_URL_TEST к каноничному async-виду.

        В CI это значение приходит «сырым» из Neon (db_url_pooled) — libpq-URI
        вида postgresql://user:pass@host/db?sslmode=require&channel_binding=require,
        без тега драйвера +asyncpg и с libpq-параметрами ssl, которые asyncpg не
        понимает. Локально в backend/.env значение уже в каноничной форме
        (postgresql+asyncpg://...?ssl=require). Приводим оба случая к одному
        виду: схема всегда postgresql+asyncpg, исходная query-строка отбрасывается
        целиком и заменяется на ?ssl=require. Идемпотентно: повторное применение
        к уже нормализованному URL не меняет его.
        """
        if not v:
            return v
        # всё после схемы, без query-строки
        authority_path = v.split("://", 1)[-1].split("?", 1)[0]
        return f"postgresql+asyncpg://{authority_path}?ssl=require"

    cors_origins: str = "http://localhost:5173"

    # Порог «залежавшегося» черновика (дни) для дашборда. Правится env, не миграцией.
    dashboard_stale_days: int = 14

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
    def database_url_test_sync(self) -> str:
        """Sync-URL (psycopg) для Alembic против тестовой ветки. Пусто, если
        database_url_test не задан. Трансформация — как у database_url_sync."""
        if not self.database_url_test:
            return ""
        url = self.database_url_test.replace("+asyncpg", "+psycopg")
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
