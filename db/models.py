from __future__ import annotations
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base


class Credential(Base):
    __tablename__ = "credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector: Mapped[str] = mapped_column(String(50), index=True)
    # OAuth client credentials (for trial/dev; consider encryption for prod)
    client_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    client_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # OAuth tokens
    access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    scopes: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    cc_pairs: Mapped[list[CCPair]] = relationship(back_populates="credential")


class CCPair(Base):
    __tablename__ = "cc_pairs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector: Mapped[str] = mapped_column(String(50), index=True)

    credential_id: Mapped[int] = mapped_column(ForeignKey("credentials.id", ondelete="RESTRICT"))
    credential: Mapped[Credential] = relationship(back_populates="cc_pairs")

    # Arbitrary configuration, e.g., folder IDs or filters
    config: Mapped[dict] = mapped_column(JSON, default=dict)

    # Sync state, like cursors or timestamps
    state: Mapped[dict] = mapped_column(JSON, default=dict)

    # Optional cron string for scheduled incremental runs
    schedule_cron: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    documents: Mapped[list[Document]] = relationship(back_populates="ccpair", cascade="all, delete-orphan")
    runs: Mapped[list[Run]] = relationship(back_populates="ccpair", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ccpair_id: Mapped[int] = mapped_column(ForeignKey("cc_pairs.id", ondelete="CASCADE"), index=True)
    ccpair: Mapped[CCPair] = relationship(back_populates="documents")

    source_id: Mapped[str] = mapped_column(String(255), index=True)
    version: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    name: Mapped[str] = mapped_column(String(1024))
    path: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    modified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    checksum: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    storage_path: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    indexed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("ccpair_id", "source_id", name="uq_documents_ccpair_source"),
    )


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ccpair_id: Mapped[int] = mapped_column(ForeignKey("cc_pairs.id", ondelete="CASCADE"), index=True)
    ccpair: Mapped[CCPair] = relationship(back_populates="runs")

    type: Mapped[str] = mapped_column(String(32))  # backfill | incremental | prune
    status: Mapped[str] = mapped_column(String(32))  # queued | running | success | failed

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    counts: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

