"""SQLAlchemy engine and session helpers."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from qualiagent.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_session() -> Generator[Session]:
    """Yield a database session and close it afterwards.

    Yields:
        An open SQLAlchemy ``Session``.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
