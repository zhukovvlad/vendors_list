"""Аутентификация (корпоративный OIDC) и авторизация (роли viewer/admin).

Свою аутентификацию не пишем — токен выдаёт SSO (Entra ID / Keycloak), мы
только валидируем его подпись по JWKS издателя и достаём логин + роль.

Роли живут в API, не в БД (пока их две и личности — в SSO):
* ``viewer`` — любой аутентифицированный: чтение.
* ``admin``  — редактирование стандартов, ``freeze_release``, соглашения, проекты.

В dev (``AUTH_DEV_BYPASS=true``) проверка токена пропускается и запрос идёт
под фиктивным пользователем — удобно для локальной разработки без SSO.
В prod bypass ЗАПРЕЩЁН (проверяется при старте приложения).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)

Role = str  # "viewer" | "admin"


@dataclass(frozen=True)
class CurrentUser:
    username: str
    role: Role

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


@lru_cache
def _jwks_client(jwks_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(jwks_url)


def _extract_role(claims: dict[str, Any], settings: Settings) -> Role:
    raw = claims.get(settings.oidc_roles_claim, [])
    roles = raw if isinstance(raw, list) else [raw]
    return "admin" if "admin" in roles else "viewer"


async def require_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    """Валидирует токен и возвращает текущего пользователя."""
    if settings.auth_dev_bypass and not settings.is_prod:
        return CurrentUser(username=settings.auth_dev_user, role=settings.auth_dev_role)

    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")

    try:
        signing_key = _jwks_client(settings.oidc_jwks_url).get_signing_key_from_jwt(
            creds.credentials
        )
        claims = jwt.decode(
            creds.credentials,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer or None,
            options={"require": ["exp", "iat"]},
        )
    except jwt.PyJWTError as exc:  # noqa: BLE001 — любую ошибку токена -> 401
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {exc}") from exc

    username = claims.get(settings.oidc_username_claim) or claims.get("sub")
    if not username:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token has no username claim")

    return CurrentUser(username=str(username), role=_extract_role(claims, settings))


async def require_admin(user: CurrentUser = Depends(require_user)) -> CurrentUser:
    """Гейт для пишущих/административных эндпоинтов."""
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin role required")
    return user
