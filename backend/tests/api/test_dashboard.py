"""GET /dashboard: контракт авторизации."""

import pytest

pytestmark = pytest.mark.db


async def test_requires_auth(client, no_auth_bypass) -> None:
    resp = await client.get("/dashboard")
    assert resp.status_code == 401
