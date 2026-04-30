import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import verify_password, create_access_token, decode_token, CREDENTIALS_EXCEPTION
from config import settings
from database import get_db
from dependencies import get_current_user, get_redis
from models.user import User
from schemas.user import LoginRequest, TokenResponse, UserResponse, UserCreate
from auth import hash_password

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    token = create_access_token(user_id=user.id, role=user.role.value, username=user.username)

    return TokenResponse(
        access_token=token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_HOURS * 3600,
        user=UserResponse.model_validate(user),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    current_user: User = Depends(get_current_user),
):
    token = create_access_token(
        user_id=current_user.id,
        role=current_user.role.value,
        username=current_user.username,
    )
    return TokenResponse(
        access_token=token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_HOURS * 3600,
        user=UserResponse.model_validate(current_user),
    )


@router.post("/logout", status_code=200)
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    redis_client: aioredis.Redis = Depends(get_redis),
):
    auth = request.headers.get("Authorization", "")
    token = auth.split(" ", 1)[-1] if " " in auth else ""
    if token:
        try:
            payload = decode_token(token)
            exp = payload.get("exp", 0)
            ttl = max(int(exp - datetime.now(timezone.utc).timestamp()), 1)
            await redis_client.set(f"blacklist:{token}", "1", ex=ttl)
        except Exception:
            pass
    return {"detail": "Logged out"}


@router.post("/users", response_model=UserResponse, status_code=201)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from models.user import UserRole
    if current_user.role not in (UserRole.admin, UserRole.superadmin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already taken")

    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        role=body.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)
