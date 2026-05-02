from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from typing import AsyncGenerator
import structlog

from app.config import settings

logger = structlog.get_logger()

engine = create_async_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=not settings.is_production,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    """Crée les tables manquantes et vérifie la connexion DB."""
    import app.models.db  # noqa — enregistre tous les modèles dans Base.metadata
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables verified")


async def close_db() -> None:
    await engine.dispose()
    logger.info("Database connection closed")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency FastAPI pour injecter une session DB."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
