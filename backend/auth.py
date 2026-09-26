from __future__ import annotations

import os
from typing import Annotated

from clerk_backend_api import AuthenticateRequestOptions, authenticate_request
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.fal_api import PROJECT_ROOT

load_dotenv(PROJECT_ROOT / ".env")
bearer = HTTPBearer(auto_error=False)


def require_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> str:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Sign in to continue", headers={"WWW-Authenticate": "Bearer"})
    secret = os.getenv("CLERK_SECRET_KEY")
    parties = [item.strip() for item in os.getenv("CLERK_AUTHORIZED_PARTIES", "").split(",") if item.strip()]
    if not secret or not parties:
        raise HTTPException(status_code=503, detail="Clerk is not configured")
    try:
        state = authenticate_request(
            request,
            AuthenticateRequestOptions(
                secret_key=secret,
                jwt_key=os.getenv("CLERK_JWT_KEY") or None,
                authorized_parties=parties,
                accepts_token=["session_token"],
            ),
        )
    except Exception as error:
        raise HTTPException(status_code=401, detail="Invalid session", headers={"WWW-Authenticate": "Bearer"}) from error
    if not state.is_signed_in or not state.payload or not state.payload.get("sub"):
        raise HTTPException(status_code=401, detail="Sign in to continue", headers={"WWW-Authenticate": "Bearer"})
    return str(state.payload["sub"])


UserId = Annotated[str, Depends(require_user)]
