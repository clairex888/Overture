"""
Authentication API routes.

Provides register, login, profile, and admin endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
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


class SetupAdminResponse(BaseModel):
    success: bool
    message: str


@router.post("/setup-admin", response_model=SetupAdminResponse)
async def setup_admin(session: AsyncSession = Depends(get_session)):
    """Create or reset the master admin account.

    This is an unauthenticated endpoint intended for initial setup.
    It always resets the admin password to the default so the account
    is recoverable even if the JWT secret or hash rounds changed.
    """
    result = await session.execute(
        select(User).where(User.email == "admin@overture.ai")
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.hashed_password = hash_password("admin123")
        existing.is_active = True
        return SetupAdminResponse(
            success=True,
            message="Master admin password has been reset.",
        )

    user = User(
        id=str(uuid4()),
        email="admin@overture.ai",
        hashed_password=hash_password("admin123"),
        display_name="Master Admin",
        role=UserRole.ADMIN,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return SetupAdminResponse(
        success=True,
        message="Master admin account created.",
    )


# ---------------------------------------------------------------------------
# Admin endpoints (admin-only)
# ---------------------------------------------------------------------------


def _require_admin(user: User) -> None:
    """Raise 403 if user is not an admin."""
    if not user.role or user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")


class AdminUserInfo(BaseModel):
    id: str
    email: str
    display_name: str | None
    role: str
    is_active: bool
    has_portfolio: bool
    created_at: str


class AdminStats(BaseModel):
    total_users: int
    active_users: int
    admin_count: int
    users_with_portfolios: int
    recent_registrations: list[AdminUserInfo]
    all_users: list[AdminUserInfo]
    idea_count: int
    trade_count: int
    knowledge_count: int


@router.get("/admin/stats", response_model=AdminStats)
async def admin_stats(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get platform-wide stats. Admin only."""
    _require_admin(user)

    # User stats
    total = (await session.execute(select(func.count()).select_from(User))).scalar() or 0
    active = (await session.execute(
        select(func.count()).select_from(User).where(User.is_active.is_(True))
    )).scalar() or 0
    admins = (await session.execute(
        select(func.count()).select_from(User).where(User.role == UserRole.ADMIN)
    )).scalar() or 0
    with_portfolios = (await session.execute(
        select(func.count()).select_from(User).where(User.portfolio_id.isnot(None))
    )).scalar() or 0

    # All users (ordered by created_at desc)
    result = await session.execute(
        select(User).order_by(User.created_at.desc())
    )
    all_users_rows = result.scalars().all()

    def _to_admin_info(u: User) -> AdminUserInfo:
        return AdminUserInfo(
            id=u.id,
            email=u.email,
            display_name=u.display_name,
            role=u.role.value if u.role else "user",
            is_active=u.is_active,
            has_portfolio=bool(u.portfolio_id),
            created_at=u.created_at.isoformat() + "Z" if u.created_at else "",
        )

    all_users = [_to_admin_info(u) for u in all_users_rows]
    recent = all_users[:10]  # 10 most recent

    # Activity counts (lightweight — just row counts)
    idea_count = 0
    trade_count = 0
    knowledge_count = 0
    try:
        from src.models.idea import Idea
        idea_count = (await session.execute(
            select(func.count()).select_from(Idea)
        )).scalar() or 0
    except Exception:
        pass
    try:
        from src.models.trade import Trade
        trade_count = (await session.execute(
            select(func.count()).select_from(Trade)
        )).scalar() or 0
    except Exception:
        pass
    try:
        from src.models.knowledge import KnowledgeEntry
        knowledge_count = (await session.execute(
            select(func.count()).select_from(KnowledgeEntry)
        )).scalar() or 0
    except Exception:
        pass

    return AdminStats(
        total_users=total,
        active_users=active,
        admin_count=admins,
        users_with_portfolios=with_portfolios,
        recent_registrations=recent,
        all_users=all_users,
        idea_count=idea_count,
        trade_count=trade_count,
        knowledge_count=knowledge_count,
    )
