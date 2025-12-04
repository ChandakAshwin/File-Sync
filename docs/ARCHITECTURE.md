# Wokelo File Sync — Architecture Overview

Goal: a clean, modular layout where connectors are easy to add and the runtime layers are separated.

- connectors/: Connector framework and implementations (Box, etc.).
- pipelines/: Orchestration of use-cases (indexing, pruning), call connectors and infra only.
- infra/: Adapters (DB, storage, search). No business logic.
- workers/: Task entrypoints (Celery/RQ) that call pipelines and return results.
- core/: Domain types/services with no infra or external SDK imports.
- config/: Configuration (Pydantic BaseSettings) and logging.
- scripts/: One-shot developer utilities.
- docs/: How-to guides.

Adding a connector:
1) Copy connectors/box to connectors/<newsource>.
2) Implement load_all() and list_ids() at minimum (SlimConnector for prune).
3) Register it in connectors/registry.py.
4) Pipelines and workers do not change.
