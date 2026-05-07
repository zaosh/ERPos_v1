"""
Test fixtures: async DB, test client, mock users.
Uses a separate test database (thrift_store_test).
"""
import asyncio
import os
import sys

import pytest
import pytest_asyncio
import fakeredis.aioredis
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

os.environ.setdefault("SECRET_KEY", "test_secret_key_that_is_at_least_64_characters_long_for_testing_only")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://thrift_user:thrift_pass@localhost:5432/thrift_store_test")
os.environ.setdefault("IMAGE_STORAGE_PATH", "/tmp/thrift_images_test")
os.environ.setdefault("IMAGE_BASE_URL", "http://localhost:8000/images")

from auth import create_access_token, hash_password
from database import get_db
from dependencies import get_redis
from main import app
from models import Base, User, Item, UserRole, ItemCategory, ItemType, ItemCondition, ItemStatus
from decimal import Decimal


TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://thrift_user:thrift_pass@localhost:5432/thrift_store_test",
)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine):
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def fake_redis():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield redis
    await redis.flushall()
    await redis.aclose()


@pytest_asyncio.fixture
async def client(db_session, fake_redis):
    async def override_db():
        yield db_session

    async def override_redis():
        return fake_redis

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_redis] = override_redis
    app.state.redis = fake_redis

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def staff_user(db_session) -> User:
    user = User(
        username="staff_test",
        password_hash=hash_password("password123"),
        role=UserRole.staff,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_user(db_session) -> User:
    user = User(
        username="admin_test",
        password_hash=hash_password("password123"),
        role=UserRole.admin,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def staff_headers(staff_user) -> dict:
    token = create_access_token(user_id=staff_user.id, role="staff", username=staff_user.username)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(admin_user) -> dict:
    token = create_access_token(user_id=admin_user.id, role="admin", username=admin_user.username)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def test_item(db_session, staff_user) -> Item:
    item = Item(
        barcode="THR-20260429-00001",
        category=ItemCategory.tshirt,
        color="black",
        type=ItemType.band,
        label="ACDC",
        size="L",
        condition=ItemCondition.good,
        price=Decimal("12.00"),
        status=ItemStatus.in_stock,
        created_by=staff_user.id,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item
