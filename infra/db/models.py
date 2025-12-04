from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, Boolean, Text, DateTime, JSON, ForeignKey, func


class Base(DeclarativeBase):
    pass


class Connector(Base):
    __tablename__ = "connector"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    source: Mapped[str] = mapped_column(String)
    input_type: Mapped[str | None] = mapped_column(String, nullable=True)
    connector_specific_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    refresh_freq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prune_freq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    indexing_start: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    time_created: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    time_updated: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())


class Credential(Base):
    __tablename__ = "credential"

    id: Mapped[int] = mapped_column(primary_key=True)
    credential_json: Mapped[dict] = mapped_column(JSON)
    user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    admin_public: Mapped[bool] = mapped_column(Boolean, default=True)
    time_created: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    time_updated: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())


class ConnectorCredentialPair(Base):
    __tablename__ = "connector_credential_pair"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    connector_id: Mapped[int] = mapped_column(ForeignKey("connector.id", ondelete="CASCADE"))
    credential_id: Mapped[int] = mapped_column(ForeignKey("credential.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String, default="ACTIVE")
    last_successful_index_time: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
    last_attempt_status: Mapped[str | None] = mapped_column(String, nullable=True)
    total_docs_indexed: Mapped[int] = mapped_column(Integer, default=0)
    time_created: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    time_updated: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())


class Document(Base):
    __tablename__ = "document"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    from_ingestion_api: Mapped[bool] = mapped_column(Boolean, default=False)
    boost: Mapped[int] = mapped_column(Integer, default=0)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    semantic_id: Mapped[str] = mapped_column(String)
    link: Mapped[str | None] = mapped_column(String, nullable=True)
    doc_updated_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
    chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_modified: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    last_synced: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)
    doc_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class DocumentByConnectorCredentialPair(Base):
    __tablename__ = "document_by_connector_credential_pair"

    id: Mapped[str] = mapped_column(ForeignKey("document.id", ondelete="CASCADE"), primary_key=True)
    connector_credential_pair_id: Mapped[int] = mapped_column(ForeignKey("connector_credential_pair.id", ondelete="CASCADE"), primary_key=True)


class IndexAttempt(Base):
    __tablename__ = "index_attempt"

    id: Mapped[int] = mapped_column(primary_key=True)
    connector_credential_pair_id: Mapped[int] = mapped_column(ForeignKey("connector_credential_pair.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String, default="NOT_STARTED")
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_docs_indexed: Mapped[int] = mapped_column(Integer, default=0)
    docs_removed_from_index: Mapped[int] = mapped_column(Integer, default=0)
    time_started: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
    time_updated: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
