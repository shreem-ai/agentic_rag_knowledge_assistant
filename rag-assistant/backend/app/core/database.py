from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

DATABASE_URL = f"sqlite+aiosqlite:///{settings.DB_PATH}"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    """Create all tables on startup and reset stuck processing documents."""
    async with engine.begin() as conn:
        from app.models import document, conversation  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)

    # Documents left in "processing" state from a previous crash will never
    # complete — mark them as error so the UI doesn't show them as pending.
    from sqlalchemy import update
    from app.models.document import Document
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Document)
            .where(Document.status == "processing")
            .values(status="error", error_message="Server restarted during ingestion.")
        )
        await session.commit()


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
