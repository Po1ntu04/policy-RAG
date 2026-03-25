"""Auth API models."""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")


class UserPublic(BaseModel):
    user_id: str
    username: str
    display_name: str | None = None
    roles: list[str] = []


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic
