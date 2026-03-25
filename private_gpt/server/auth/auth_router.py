"""Auth API routes."""

from fastapi import APIRouter, Depends, HTTPException, Request

from private_gpt.server.auth.auth_service import AuthService
from private_gpt.server.auth.models import LoginRequest, LoginResponse, UserPublic
from private_gpt.server.utils.auth import authenticated
from private_gpt.settings.settings import settings

auth_router = APIRouter(prefix="/v1/auth", tags=["auth"])


@auth_router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest):
    if not settings().server.auth.enabled:
        raise HTTPException(status_code=400, detail="Auth is disabled in settings")
    service = AuthService()
    user, roles = service.authenticate(body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = service.issue_token(user, roles)
    return LoginResponse(
        access_token=token,
        user=UserPublic(
            user_id=str(user["user_id"]),
            username=user["username"],
            display_name=user.get("display_name"),
            roles=roles,
        ),
    )


@auth_router.get("/me", response_model=UserPublic, dependencies=[Depends(authenticated)])
def me(request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return UserPublic(
        user_id=user.get("user_id"),
        username=user.get("username"),
        display_name=user.get("display_name"),
        roles=user.get("roles") or [],
    )
