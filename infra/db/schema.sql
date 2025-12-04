-- Minimal schema for Wokelo File Sync
-- Only the tables and columns used by the worker and local storage logic

-- connector: data source definitions (Box, etc.)
CREATE TABLE IF NOT EXISTS connector (
  id SERIAL PRIMARY KEY,
  name VARCHAR NOT NULL,
  source VARCHAR NOT NULL,            -- 'box'
  input_type VARCHAR NULL,            -- optional
  connector_specific_config JSON NULL,
  refresh_freq INTEGER NULL,
  prune_freq INTEGER NULL,
  indexing_start TIMESTAMP NULL,
  disabled BOOLEAN DEFAULT FALSE,
  time_created TIMESTAMP DEFAULT NOW(),
  time_updated TIMESTAMP DEFAULT NOW()
);

-- credential: JSON credentials (OAuth tokens)
CREATE TABLE IF NOT EXISTS credential (
  id SERIAL PRIMARY KEY,
  credential_json JSON NOT NULL,
  user_id VARCHAR NULL,
  admin_public BOOLEAN DEFAULT TRUE,
  time_created TIMESTAMP DEFAULT NOW(),
  time_updated TIMESTAMP DEFAULT NOW()
);

-- connector_credential_pair: links connector to credentials
CREATE TABLE IF NOT EXISTS connector_credential_pair (
  id SERIAL PRIMARY KEY,
  name VARCHAR NULL,
  connector_id INTEGER NOT NULL REFERENCES connector(id) ON DELETE CASCADE,
  credential_id INTEGER NOT NULL REFERENCES credential(id) ON DELETE CASCADE,
  status VARCHAR DEFAULT 'ACTIVE',           -- ACTIVE/PAUSED/FAILED
  last_successful_index_time TIMESTAMP NULL,
  last_attempt_status VARCHAR NULL,          -- SUCCESS/FAILED/IN_PROGRESS/NOT_STARTED
  total_docs_indexed INTEGER DEFAULT 0,
  time_created TIMESTAMP DEFAULT NOW(),
  time_updated TIMESTAMP DEFAULT NOW()
);

-- document: metadata for synced docs
CREATE TABLE IF NOT EXISTS document (
  id VARCHAR PRIMARY KEY,                   -- e.g. 'box:1234567'
  from_ingestion_api BOOLEAN DEFAULT FALSE,
  boost INTEGER DEFAULT 0,
  hidden BOOLEAN DEFAULT FALSE,
  semantic_id VARCHAR NOT NULL,
  link VARCHAR NULL,
  doc_updated_at TIMESTAMP NULL,
  chunk_count INTEGER NULL,
  last_modified TIMESTAMP DEFAULT NOW(),
  last_synced TIMESTAMP NULL,
  is_public BOOLEAN DEFAULT TRUE,
  doc_metadata JSON NULL
);

-- document_by_connector_credential_pair: association table
CREATE TABLE IF NOT EXISTS document_by_connector_credential_pair (
  id VARCHAR NOT NULL REFERENCES document(id) ON DELETE CASCADE,
  connector_credential_pair_id INTEGER NOT NULL REFERENCES connector_credential_pair(id) ON DELETE CASCADE,
  PRIMARY KEY (id, connector_credential_pair_id)
);

-- index_attempt: tracks indexing runs
CREATE TABLE IF NOT EXISTS index_attempt (
  id SERIAL PRIMARY KEY,
  connector_credential_pair_id INTEGER NOT NULL REFERENCES connector_credential_pair(id) ON DELETE CASCADE,
  status VARCHAR DEFAULT 'NOT_STARTED',
  error_msg TEXT NULL,
  new_docs_indexed INTEGER DEFAULT 0,
  docs_removed_from_index INTEGER DEFAULT 0,
  time_started TIMESTAMP NULL,
  time_updated TIMESTAMP DEFAULT NOW()
);
