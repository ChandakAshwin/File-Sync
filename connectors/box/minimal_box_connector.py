#!/usr/bin/env python3
"""
Ultra-minimal Box connector using just requests
Copied into WokeloFileSync and adjusted imports
"""

import json
import requests
from datetime import datetime
from typing import List, Dict, Any, Optional

import logging
logger = logging.getLogger(__name__)

class SimpleDocument:
    """Simple document model"""
    def __init__(self, 
                 document_id: str,
                 title: str,
                 content: str = "",
                 link: str = "",
                 updated_at: Optional[datetime] = None,
                 metadata: Optional[Dict[str, Any]] = None):
        self.id = document_id
        self.title = title
        self.content = content
        self.link = link
        self.updated_at = updated_at or datetime.utcnow()
        self.metadata = metadata or {}
        
    def __str__(self):
        return f"Document(id={self.id}, title={self.title})"

class MinimalBoxConnector:
    """Ultra-minimal Box connector using requests"""
    
    def __init__(self, batch_size: int = 10):
        self.batch_size = batch_size
        self.access_token = None
        
    def load_credentials(self, credentials: Dict[str, Any]) -> None:
        """Load Box credentials with token manager"""
        from connectors.box.auth import BoxTokenManager
        self.token_manager = BoxTokenManager()
        self.access_token = self.token_manager.get_valid_access_token()
        if not self.access_token:
            raise ValueError("Unable to get valid Box access token")
        logger.info("Box credentials loaded with token manager")
        
    def validate_connection(self) -> bool:
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            response = requests.get('https://api.box.com/2.0/users/me', headers=headers)
            if response.status_code == 200:
                user_data = response.json()
                logger.info(f"Box connection valid - user: {user_data.get('name', 'Unknown')}")
                return True
            else:
                logger.error(f"Box connection failed: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Box connection validation failed: {e}")
            return False
    
    def get_files(self, 
                  root_folder_id: str = "0", 
                  max_files: int = 50) -> List[SimpleDocument]:
        """Get files from Box (first page of a folder)."""
        if not self.access_token:
            raise ValueError("Box access token not loaded")
        documents = []
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            url = f'https://api.box.com/2.0/folders/{root_folder_id}/items'
            params = {
                'limit': min(max_files, 100),
                'fields': 'id,name,type,size,modified_at'
            }
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            items = response.json().get('entries', [])
            logger.info(f"Found {len(items)} items in Box folder {root_folder_id}")
            for item in items:
                if item.get('type') == 'file':
                    try:
                        file_id = item.get('id')
                        file_name = item.get('name', f'File_{file_id}')
                        modified_at_raw = item.get('modified_at')
                        try:
                            updated_at = datetime.fromisoformat(modified_at_raw.replace('Z', '+00:00')) if modified_at_raw else datetime.utcnow()
                        except Exception:
                            updated_at = datetime.utcnow()
                        logger.info(f"Processing Box file: {file_name} (ID: {file_id})")
                        document = SimpleDocument(
                            document_id=f"box:{file_id}",
                            title=file_name,
                            content=f"Box file: {file_name}",
                            link=f"https://app.box.com/file/{file_id}",
                            updated_at=updated_at,
                            metadata={
                                "source": "box",
                                "file_id": file_id,
                                "size": str(item.get('size', 0)),
                                "type": "file",
                                "modified_at": modified_at_raw or updated_at.isoformat()
                            }
                        )
                        documents.append(document)
                        logger.info(f"Created document for {file_name}")
                    except Exception as e:
                        logger.error(f"Failed to process Box file {item.get('id', 'unknown')}: {e}")
                        continue
                elif item.get('type') == 'folder':
                    logger.info(f"Found folder: {item.get('name', 'Unknown')} (skipping)")
            logger.info(f"Successfully processed {len(documents)} documents from Box")
            return documents
        except Exception as e:
            logger.error(f"Error getting files from Box: {e}")
            raise

    def get_all_file_ids(self, root_folder_id: str = "0", max_pages: int = 100) -> list[str]:
        """
        Return a list of all Box file IDs under the specified folder (non-recursive),
        paginating through all items. This is used for safe deletion pruning.
        """
        if not self.access_token:
            raise ValueError("Box access token not loaded")
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        url = f'https://api.box.com/2.0/folders/{root_folder_id}/items'
        limit = 100
        offset = 0
        page = 0
        all_ids: list[str] = []
        while page < max_pages:
            params = {
                'limit': limit,
                'offset': offset,
                'fields': 'id,name,type'
            }
            resp = requests.get(url, headers=headers, params=params)
            resp.raise_for_status()
            entries = resp.json().get('entries', [])
            file_ids = [e['id'] for e in entries if e.get('type') == 'file']
            all_ids.extend(file_ids)
            if len(entries) < limit:
                break
            offset += limit
            page += 1
        logger.info(f"Collected {len(all_ids)} file IDs from Box (folder {root_folder_id})")
        return all_ids
