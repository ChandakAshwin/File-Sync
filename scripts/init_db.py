#!/usr/bin/env python3
"""
Initialize the minimal database schema for Wokelo File Sync.
Reads DB connection parameters from environment variables:
- POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB
or a full DATABASE_URL. Defaults match README examples.
"""

import os
from sqlalchemy import create_engine, text


def get_db_url() -> str:
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return db_url
    user = os.getenv("POSTGRES_USER", "postgres")
    pwd = os.getenv("POSTGRES_PASSWORD", "password")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "filesync")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"


def main() -> None:
    root = os.path.dirname(os.path.dirname(__file__))
    schema_path = os.path.join(root, "infra", "db", "schema.sql")
    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    with open(schema_path, "r", encoding="utf-8") as f:
        ddl = f.read()

    engine = create_engine(get_db_url())
    with engine.begin() as conn:
        conn.execute(text(ddl))

    print("Database schema initialized/verified.")


if __name__ == "__main__":
    main()
