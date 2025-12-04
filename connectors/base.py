from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional, Protocol


@dataclass
class FileItem:
    """Normalized descriptor of a remote file returned by a connector.

    The fields cover what is needed for downstream storage and indexing.
    """

    id: str
    name: str
    path: Optional[str]
    size_bytes: Optional[int]
    mime_type: Optional[str]
    modified_at: Optional[datetime]
    checksum: Optional[str]
    source_url: Optional[str]


class Connector(Protocol):
    name: str

    # OAuth helpers
    def build_authorize_url(self, *, client_id: str, redirect_uri: str, state: str) -> str: ...
    def exchange_code_for_tokens(
        self,
        *,
        client_id: str,
        client_secret: str,
        code: str,
        redirect_uri: str,
    ) -> dict: ...

    def refresh_tokens(self, *, client_id: str, client_secret: str, refresh_token: str) -> dict: ...

    # Data plane
    def list_all_items(self, *, access_token: str, config: dict) -> Iterable[FileItem]: ...
    def download_file(self, *, access_token: str, file_id: str) -> Iterable[bytes]: ...
