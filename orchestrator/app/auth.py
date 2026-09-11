"""Bearer-token dependency shared by /query and /chat. SECURITY.md §3."""

import hmac

from fastapi import Header, HTTPException

from app.config import settings


async def require_bearer_token(authorization: str = Header(default="")) -> None:
    scheme, _, token = authorization.partition(" ")
    if scheme != "Bearer" or not hmac.compare_digest(token, settings.orch_bearer_token):
        raise HTTPException(status_code=401, detail="missing or invalid bearer token")
