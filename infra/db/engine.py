from __future__ import annotations
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from config.settings import settings
from infra.db import models

_engine = create_engine(settings.DB_URL or settings.DATABASE_URL, pool_pre_ping=True, future=True)
_SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency to provide a DB session and ensure cleanup."""
    db: Session = _SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db_schema() -> None:
    """Create tables if they don't exist (uses SQLAlchemy models metadata)."""
    models.Base.metadata.create_all(bind=_engine)
