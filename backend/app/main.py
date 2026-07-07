"""FastAPI-приложение: точка входа, CORS, монтирование роутеров.

Схема БД — источник истины (schema-first). API строится ПОВЕРХ готовых вьюх и
функций (``listing_live``, ``release_listing``, ``compliance.*``, ``freeze_release``);
расчёт статусов/звезды в коде не дублируется.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import dispose_engine
from .routers import compliance, listings, meta, releases


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    if settings.is_prod and settings.auth_dev_bypass:
        raise RuntimeError("AUTH_DEV_BYPASS must be false in production")
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Vendors API",
        version="0.1.0",
        summary="Учёт вендор-листов и соответствия проектов стандартам",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    for module in (meta, listings, releases, compliance):
        app.include_router(module.router)

    return app


app = create_app()
