# Connector Guide

This guide explains how to add a new connector in Wokelo File Sync.

1) Copy an existing connector
- Duplicate connectors/box/ → connectors/<newsource>/
- Keep the same file layout: connector.py, auth.py (if needed), client.py (optional)

2) Implement the interfaces
- Implement at least LoadConnector.load_all() and SlimConnector.list_ids()
- Optionally implement PollConnector.poll_since() if you need incremental updates

3) Register your connector
```python
# connectors/registry.py
from connectors.registry import register
from connectors.newsource.connector import NewSourceConnector

register("newsource", NewSourceConnector)
```

4) Keep business logic out of the connector
- Connectors should only talk to the external API and map responses → SimpleDoc
- Pipelines will handle DB writes and local storage sync via infra/

5) Test
- Unit test mapping logic with mocked HTTP responses
- End-to-end: run a pipeline using your connector and verify DB & local storage
