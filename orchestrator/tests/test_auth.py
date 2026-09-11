"""auth.py bearer-token dependency. SECURITY.md §3."""

import pytest
from fastapi import HTTPException

from app.auth import require_bearer_token
from app.config import settings


async def test_valid_token_passes() -> None:
    await require_bearer_token(authorization=f"Bearer {settings.orch_bearer_token}")


async def test_missing_header_rejected() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await require_bearer_token(authorization="")
    assert exc_info.value.status_code == 401


async def test_wrong_token_rejected() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await require_bearer_token(authorization="Bearer wrong-token")
    assert exc_info.value.status_code == 401


async def test_wrong_scheme_rejected() -> None:
    with pytest.raises(HTTPException):
        await require_bearer_token(authorization=f"Basic {settings.orch_bearer_token}")
