"""
Authentication API routes.

Provides register, login, and profile endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from src.models.base import get_session
from src.models.user import User, UserRole
from src.auth import hash_password, verify_password, create_token, get_current_user

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=5)
    password: str = Field(..., min_length=6)
    display_name: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    token: str
    user: "UserProfile"


class UserProfile(BaseModel):
    id: str
    email: str
    display_name: str | None
    role: str
    is_active: bool
    portfolio_id: str | None
    created_at: str


class UpdateProfileRequest(BaseModel):
    display_name: str | None = None


def _user_profile(user: User) -> UserProfile:
    return UserProfile(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role.value if user.role else "user",
        is_active=user.is_active,
        portfolio_id=user.portfolio_id,
        created_at=user.created_at.isoformat() + "Z" if user.created_at else "",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(
    payload: RegisterRequest,
    session: AsyncSession = Depends(get_session),
):
    """Create a new user account."""
    # Check duplicate
    result = await session.execute(
        select(User).where(User.email == payload.email.lower().strip())
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        id=str(uuid4()),
        email=payload.email.lower().strip(),
        hashed_password=hash_password(payload.password),
        display_name=payload.display_name,
        role=UserRole.USER,
        is_active=True,
    )
    session.add(user)
    await session.flush()

    token = create_token(user.id, user.email, user.role.value)
    return AuthResponse(token=token, user=_user_profile(user))


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_session),
):
    """Authenticate and receive a JWT token."""
    result = await session.execute(
        select(User).where(User.email == payload.email.lower().strip())
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    token = create_token(user.id, user.email, user.role.value)
    return AuthResponse(token=token, user=_user_profile(user))


@router.get("/me", response_model=UserProfile)
async def get_profile(user: User = Depends(get_current_user)):
    """Get current authenticated user profile."""
    return _user_profile(user)


@router.put("/me", response_model=UserProfile)
async def update_profile(
    payload: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Update current user profile."""
    if payload.display_name is not None:
        user.display_name = payload.display_name
    return _user_profile(user)
