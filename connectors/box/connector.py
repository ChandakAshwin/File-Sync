from __future__ import annotations
from typing import Iterable, Optional

import httpx

from connectors.base import Connector, FileItem
from connectors.registry import register

API_BASE = "https://api.box.com/2.0"


@register("box")
class BoxConnector:
    name = "box"

    def build_authorize_url(self, *, client_id: str, redirect_uri: str, state: str) -> str:
        from connectors.box.auth import build_authorize_url

        return build_authorize_url(client_id=client_id, redirect_uri=redirect_uri, state=state)

    def exchange_code_for_tokens(
        self,
        *,
        client_id: str,
        client_secret: str,
        code: str,
        redirect_uri: str,
    ) -> dict:
        import anyio
        from connectors.box.auth import exchange_code_for_tokens_async

        async def _run():
            return await exchange_code_for_tokens_async(
                client_id=client_id,
                client_secret=client_secret,
                code=code,
                redirect_uri=redirect_uri,
            )

        return anyio.run(_run)

    async def exchange_code_for_tokens_async(
        self,
        *,
        client_id: str,
        client_secret: str,
        code: str,
        redirect_uri: str,
    ) -> dict:
        from connectors.box.auth import exchange_code_for_tokens_async as _exchange
        return await _exchange(
            client_id=client_id,
            client_secret=client_secret,
            code=code,
            redirect_uri=redirect_uri,
        )

    def refresh_tokens(self, *, client_id: str, client_secret: str, refresh_token: str) -> dict:
        import anyio
        from connectors.box.auth import refresh_tokens_async

        async def _run():
            return await refresh_tokens_async(
                client_id=client_id,
                client_secret=client_secret,
                refresh_token=refresh_token,
            )

        return anyio.run(_run)

    async def refresh_tokens_async(self, *, client_id: str, client_secret: str, refresh_token: str) -> dict:
        from connectors.box.auth import refresh_tokens_async as _refresh
        return await _refresh(
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
        )

    def list_all_items(self, *, access_token: str, config: dict) -> Iterable[FileItem]:
        """Recursively walk configured folders and yield FileItem for each file.

        config may include:
        - folder_ids: list[str] starting folders (default ["0"])
        - include_exts: list[str] whitelist of file extensions
        - max_size_mb: int maximum file size to include
        """
        headers = {"Authorization": f"Bearer {access_token}"}
        folder_ids = config.get("folder_ids") or ["0"]
        include_exts = {e.lower().lstrip(".") for e in (config.get("include_exts") or [])}
        max_size = None
        if (mb := config.get("max_size_mb")) is not None:
            max_size = int(mb) * 1024 * 1024

        def allowed(name: str, size: Optional[int]) -> bool:
            if include_exts:
                ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                if ext not in include_exts:
                    return False
            if max_size is not None and size is not None and size > max_size:
                return False
            return True

        with httpx.Client(timeout=60) as client:
            for folder_id in folder_ids:
                yield from self._walk_folder(client, headers, folder_id, path="", allow=allowed)

    def _walk_folder(self, client: httpx.Client, headers: dict, folder_id: str, path: str, allow) -> Iterable[FileItem]:
        # Paginate folder items
        offset = 0
        limit = 1000
        while True:
            url = f"{API_BASE}/folders/{folder_id}/items"
            params = {"limit": limit, "offset": offset, "fields": "id,name,modified_at,size,sha1,item_status"}
            resp = client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
            entries = data.get("entries", [])
            if not entries:
                break
            for e in entries:
                etype = e.get("type")
                if etype == "folder":
                    name = e.get("name") or ""
                    fid = e.get("id")
                    sub_path = f"{path}/{name}" if path else name
                    # Recurse
                    yield from self._walk_folder(client, headers, fid, sub_path, allow)
                elif etype == "file":
                    if e.get("item_status") == "trashed":
                        continue
                    name = e.get("name") or ""
                    size = e.get("size")
                    if not allow(name, size):
                        continue
                    fi = FileItem(
                        id=str(e.get("id")),
                        name=name,
                        path=path,
                        size_bytes=size,
                        mime_type=None,  # can fetch details if needed
                        modified_at=None,  # could parse e.get("modified_at")
                        checksum=e.get("sha1"),
                        source_url=None,
                    )
                    yield fi
            offset += len(entries)
            if len(entries) < limit:
                break

    def download_file(self, *, access_token: str, file_id: str) -> Iterable[bytes]:
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"{API_BASE}/files/{file_id}/content"
        with httpx.Client(timeout=None, follow_redirects=True) as client:
            with client.stream("GET", url, headers=headers) as resp:
                resp.raise_for_status()
                for chunk in resp.iter_bytes():
                    if chunk:
                        yield chunk
