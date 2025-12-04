# Local storage adapter copied from your current project
# Kept mostly as-is to preserve behavior; namespaced under infra/storage.

import os
import json
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy import create_engine, text

from connectors.box.auth import BoxTokenManager
from config.settings import settings


class LocalStorage:
    """Downloads and syncs indexed documents to local storage."""

    def __init__(self, access_token: Optional[str] = None):
        self.documents_dir = Path("documents/box")
        self.metadata_dir = Path("documents/metadata")
        self.base_url = "https://api.box.com/2.0"
        self.documents_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(settings.DB_URL)
        self._access_token = access_token
        self.token_manager = None if access_token else BoxTokenManager()

    def _get_headers(self) -> Dict[str, str]:
        if self._access_token:
            return {
                'Authorization': f"Bearer {self._access_token}",
                'Content-Type': 'application/json'
            }
        if not self.token_manager or not self.token_manager.test_connection():
            raise Exception("Box authentication failed")
        credentials = self.token_manager.credentials
        if not credentials or 'box_access_token' not in credentials:
            raise Exception("No valid access token available")
        return {
            'Authorization': f"Bearer {credentials['box_access_token']}",
            'Content-Type': 'application/json'
        }

    def get_indexed_documents(self) -> List[Dict[str, Any]]:
        with self.engine.connect() as conn:
            result = conn.execute(text(
                """
                SELECT id, semantic_id, link, doc_updated_at, last_modified, doc_metadata
                FROM document
                WHERE id LIKE 'box:%'
                ORDER BY last_modified DESC
                """
            ))
            documents = []
            for row in result:
                box_file_id = row[0].replace('box:', '')
                documents.append({
                    'document_id': row[0],
                    'box_file_id': box_file_id,
                    'semantic_id': row[1],
                    'box_link': row[2],
                    'doc_updated_at': row[3],
                    'last_modified': row[4],
                    'metadata': row[5] if row[5] else {}
                })
            return documents

    def get_local_file_info(self, box_file_id: str) -> Optional[Dict[str, Any]]:
        pattern = f"{box_file_id}_*"
        matches = list(self.documents_dir.glob(pattern))
        if not matches:
            return None
        local_file = matches[0]
        if local_file.exists():
            stat = local_file.stat()
            return {
                'local_path': str(local_file),
                'local_size': stat.st_size,
                'local_modified': datetime.fromtimestamp(stat.st_mtime),
                'exists': True
            }
        return None

    def download_box_file(self, box_file_id: str, filename: str = None) -> Optional[str]:
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Get metadata then download redirect
            if not filename:
                logger.info(f"Getting file info for Box file {box_file_id}")
                info_resp = requests.get(
                    f"{self.base_url}/files/{box_file_id}",
                    headers=self._get_headers(),
                    params={'fields': 'name,size,modified_at'},
                    timeout=30
                )
                logger.info(f"File info response: {info_resp.status_code}")
                if info_resp.status_code != 200:
                    logger.error(f"Failed to get file info: {info_resp.status_code} - {info_resp.text}")
                    return None
                filename = info_resp.json().get('name', f'document_{box_file_id}')
                logger.info(f"File name: {filename}")
            
            logger.info(f"Getting download URL for Box file {box_file_id}")
            resp = requests.get(
                f"{self.base_url}/files/{box_file_id}/content",
                headers=self._get_headers(),
                timeout=60,
                stream=True,
                allow_redirects=False
            )
            logger.info(f"Download redirect response: {resp.status_code}")
            
            if resp.status_code != 302:
                logger.error(f"Expected 302 redirect, got {resp.status_code}: {resp.text}")
                return None
                
            download_url = resp.headers.get('Location')
            if not download_url:
                logger.error("No download URL in Location header")
                return None
                
            logger.info(f"Downloading from: {download_url[:100]}...")
            dl = requests.get(download_url, timeout=120, stream=True)
            dl.raise_for_status()
            
            safe_filename = f"{box_file_id}_{self._sanitize_filename(filename)}"
            local_path = self.documents_dir / safe_filename
            logger.info(f"Saving to: {local_path}")
            
            with open(local_path, 'wb') as f:
                for chunk in dl.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
            logger.info(f"Successfully downloaded {box_file_id} to {local_path}")
            return str(local_path)
            
        except Exception as e:
            logger.error(f"Error downloading Box file {box_file_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _sanitize_filename(self, filename: str) -> str:
        for ch in '<>:"/\\|?*':
            filename = filename.replace(ch, '_')
        return filename[:200]

    def needs_update(self, doc_info: Dict[str, Any], local_info: Dict[str, Any]) -> bool:
        if not local_info:
            return True
        doc_updated = doc_info.get('doc_updated_at')
        if doc_updated and local_info.get('local_modified'):
            if isinstance(doc_updated, str):
                try:
                    doc_updated = datetime.fromisoformat(doc_updated.replace('Z', '+00:00'))
                except Exception:
                    return True
            if doc_updated > local_info['local_modified']:
                return True
        return False

    def sync_all_documents(self) -> Dict[str, int]:
        indexed = self.get_indexed_documents()
        stats = {'total': len(indexed), 'downloaded': 0, 'updated': 0, 'skipped': 0, 'errors': 0}
        for doc in indexed:
            box_file_id = doc['box_file_id']
            local_info = self.get_local_file_info(box_file_id)
            if local_info:
                if self.needs_update(doc, local_info):
                    try:
                        os.remove(local_info['local_path'])
                    except Exception:
                        pass
                    path = self.download_box_file(box_file_id)
                    if path:
                        stats['updated'] += 1
                        self._save_sync_metadata(box_file_id, path, doc)
                    else:
                        stats['errors'] += 1
                else:
                    stats['skipped'] += 1
            else:
                path = self.download_box_file(box_file_id)
                if path:
                    stats['downloaded'] += 1
                    self._save_sync_metadata(box_file_id, path, doc)
                else:
                    stats['errors'] += 1
        return stats

    def _save_sync_metadata(self, box_file_id: str, local_path: str, doc_info: Dict[str, Any]) -> None:
        metadata = {
            'box_file_id': box_file_id,
            'document_id': doc_info['document_id'],
            'local_path': local_path,
            'synced_at': datetime.utcnow().isoformat(),
            'box_link': doc_info.get('box_link'),
            'doc_updated_at': doc_info.get('doc_updated_at'),
            'original_metadata': doc_info.get('metadata', {})
        }
        meta_file = self.metadata_dir / f"{box_file_id}_sync.json"
        with open(meta_file, 'w') as f:
            json.dump(metadata, f, indent=2, default=str)

    def cleanup_orphaned_files(self) -> int:
        indexed = self.get_indexed_documents()
        indexed_ids = {doc['box_file_id'] for doc in indexed}
        orphaned = 0
        for file in self.documents_dir.glob("*_*"):
            if not file.is_file():
                continue
            parts = file.name.split('_', 1)
            if len(parts) < 2:
                continue
            box_id = parts[0]
            if box_id not in indexed_ids:
                try:
                    file.unlink()
                    meta = self.metadata_dir / f"{box_id}_sync.json"
                    if meta.exists():
                        meta.unlink()
                    orphaned += 1
                except Exception:
                    pass
        return orphaned
