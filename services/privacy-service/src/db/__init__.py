"""Database initialization module for privacy-service."""
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from .models import Base


async def init_db(database_url: str) -> AsyncEngine:
    """Initialize database and create tables."""
    engine = create_async_engine(database_url, echo=False, future=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    return engine


def get_session_maker(engine: AsyncEngine) -> sessionmaker:
    """Create async session maker."""
    return sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
