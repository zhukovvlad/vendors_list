"""API проектов и выбора поверх вьюх. RBAC, коды 201/403/401/404/409.
Записи идут через tx-override (SAVEPOINT) в общее тест-соединение и откатываются."""

import pytest

from tests import factories as f

pytestmark = pytest.mark.db


async def test_create_project_as_admin(client, as_admin, db_conn) -> None:
    seg = await f.get_segment_id(db_conn, name="Бизнес")
    resp = await client.post(
        "/projects", json={"code": "API-P1", "name": "Проект", "segment_id": seg}
    )
    assert resp.status_code == 201
    assert resp.json()["code"] == "API-P1"


async def test_create_project_forbidden_for_viewer(client, as_viewer, db_conn) -> None:
    seg = await f.get_segment_id(db_conn, name="Бизнес")
    resp = await client.post(
        "/projects", json={"code": "API-P2", "name": "Проект", "segment_id": seg}
    )
    assert resp.status_code == 403


async def test_list_projects_returns_created(client, as_admin, db_conn) -> None:
    seg = await f.get_segment_id(db_conn, name="Бизнес")
    await client.post("/projects", json={"code": "API-P3", "name": "N", "segment_id": seg})
    resp = await client.get("/projects")
    assert resp.status_code == 200
    assert "API-P3" in [p["code"] for p in resp.json()]


async def test_summary_404_for_unknown_project(client, as_admin) -> None:
    resp = await client.get("/projects/999999/summary")
    assert resp.status_code == 404


async def test_duplicate_project_code_409(client, as_admin, db_conn) -> None:
    seg = await f.get_segment_id(db_conn, name="Бизнес")
    await client.post("/projects", json={"code": "API-DUP", "name": "N", "segment_id": seg})
    resp = await client.post(
        "/projects", json={"code": "API-DUP", "name": "N2", "segment_id": seg}
    )
    assert resp.status_code == 409


async def test_projects_requires_auth_401(client, no_auth_bypass) -> None:
    resp = await client.get("/projects")
    assert resp.status_code == 401
