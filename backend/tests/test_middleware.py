"""Тесты ASGI RequestIdMiddleware: генерация/переиспользование/санитайз request_id
+ строка лога запроса. Своё минимальное Starlette-приложение, без БД."""

from __future__ import annotations

import logging

from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from app.middleware import RequestIdMiddleware, _incoming_request_id, _sanitize


def _build_app() -> Starlette:
    async def ping(request):
        return PlainTextResponse("pong")

    app = Starlette(routes=[Route("/ping", ping)])
    app.add_middleware(RequestIdMiddleware)
    return app


def test_sanitize_strips_control_and_truncates():
    assert "\x00" not in _sanitize("a\x00b\x1f")
    assert _sanitize("a\x00b") == "ab"
    assert len(_sanitize("x" * 100)) == 64


def test_incoming_request_id_generates_when_absent():
    rid = _incoming_request_id({"headers": []})
    assert len(rid) == 8  # uuid4().hex[:8]


def test_incoming_request_id_reuses_header():
    scope = {"headers": [(b"x-request-id", b"abc123")]}
    assert _incoming_request_id(scope) == "abc123"


def test_incoming_request_id_regenerates_when_header_all_control():
    scope = {"headers": [(b"x-request-id", b"\x00\x01")]}
    assert len(_incoming_request_id(scope)) == 8  # пусто после санитайза → фоллбэк


async def test_response_carries_request_id_header():
    transport = ASGITransport(app=_build_app())
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/ping")
    assert r.status_code == 200
    assert len(r.headers["x-request-id"]) == 8


async def test_response_reuses_incoming_request_id():
    transport = ASGITransport(app=_build_app())
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/ping", headers={"X-Request-ID": "abc123"})
    assert r.headers["x-request-id"] == "abc123"


async def test_request_line_is_logged(caplog):
    # app.request пропагирует до root; caplog вешает свой хендлер — свой в тесте не нужен.
    with caplog.at_level(logging.INFO, logger="app.request"):
        transport = ASGITransport(app=_build_app())
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            await c.get("/ping")
    assert any("/ping" in rec.getMessage() for rec in caplog.records)
