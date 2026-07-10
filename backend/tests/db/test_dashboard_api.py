"""GET /dashboard: форма ответа, is_stale по порогу, деградация детекта."""

import pytest

from tests import factories as f

pytestmark = pytest.mark.db


async def test_shape(client, as_viewer) -> None:
    body = (await client.get("/dashboard")).json()
    assert set(body) == {"summary", "drafts"}
    assert set(body["summary"]) == {
        "positions_active",
        "releases_published",
        "drafts_open",
        "vendors_total",
        "vendors_with_agreement",
        "merge_candidate_pairs",
    }
    assert isinstance(body["drafts"], list)


async def test_stale_flag_by_threshold(client, as_viewer, db_conn) -> None:
    bt = await f.make_building_type(db_conn, code="st-bt")
    rid = await f.make_release(db_conn, building_type_id=bt, status="open")
    # состарить черновик: created_at на 100 дней назад (правок listing нет → fallback)
    from sqlalchemy import text

    await db_conn.execute(
        text("UPDATE release SET created_at = now() - interval '100 days' WHERE id = :r"),
        {"r": rid},
    )
    drafts = {d["release_id"]: d for d in (await client.get("/dashboard")).json()["drafts"]}
    assert drafts[rid]["is_stale"] is True


async def test_merge_detect_failure_degrades_not_500(client, as_viewer, monkeypatch) -> None:
    from app.routers import dashboard as dash

    async def _boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(dash, "count_merge_candidates", _boom)
    resp = await client.get("/dashboard")
    assert resp.status_code == 200
    assert resp.json()["summary"]["merge_candidate_pairs"] is None
