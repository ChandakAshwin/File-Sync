"""Elasticsearch indexing with advanced features and backward compatibility"""
from __future__ import annotations

import os
import logging
from typing import Dict, Any, Optional
from elasticsearch import Elasticsearch, helpers

# Import advanced indexing
try:
    from .advanced_index import AdvancedElasticsearchIndex, create_advanced_index
    ADVANCED_AVAILABLE = True
except ImportError:
    ADVANCED_AVAILABLE = False

logger = logging.getLogger(__name__)

# Ensure API versioning for 8.x client compatibility with 7.x server
os.environ.setdefault("ELASTIC_CLIENT_APIVERSIONING", "true")

ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
ELASTICSEARCH_INDEX_NAME = os.getenv("ELASTICSEARCH_INDEX_NAME", "documents")

# Global advanced index instance
_advanced_index: Optional[AdvancedElasticsearchIndex] = None
_use_advanced = os.getenv("USE_ADVANCED_INDEXING", "true").lower() == "true"


def get_client() -> Elasticsearch:
    return Elasticsearch(ELASTICSEARCH_URL)


def get_advanced_index() -> Optional[AdvancedElasticsearchIndex]:
    """Get or create the advanced index instance"""
    global _advanced_index
    if _advanced_index is None and ADVANCED_AVAILABLE and _use_advanced:
        try:
            _advanced_index = create_advanced_index(
                index_name="documents_advanced",
                enable_embeddings=True
            )
            logger.info("Advanced indexing enabled")
        except Exception as e:
            logger.warning(f"Failed to initialize advanced indexing, falling back to basic: {e}")
    return _advanced_index


def ensure_index(client: Elasticsearch) -> None:
    if not client.indices.exists(index=ELASTICSEARCH_INDEX_NAME):
        client.indices.create(index=ELASTICSEARCH_INDEX_NAME, ignore=400)


def index_document(doc_id: str, title: str, text: str, link: str | None = None, metadata: dict | None = None) -> dict:
    """Index a document with advanced features if available"""
    # Try advanced indexing first
    advanced_index = get_advanced_index()
    if advanced_index:
        try:
            result = advanced_index.index_document(
                doc_id=doc_id,
                title=title,
                text=text,
                link=link,
                metadata=metadata or {},
                file_path=metadata.get("file_path") if metadata else None,
                enable_chunking=True
            )
            logger.debug(f"Advanced indexing result for {doc_id}: {result}")
            return result
        except Exception as e:
            logger.error(f"Advanced indexing failed for {doc_id}, falling back to basic: {e}")
    
    # Fallback to basic indexing
    client = get_client()
    ensure_index(client)
    body = {
        "title": title,
        "text": text,
        "link": link,
        "metadata": metadata or {},
    }
    client.index(index=ELASTICSEARCH_INDEX_NAME, id=doc_id, document=body, refresh=True)
    return {"status": "success", "method": "basic", "doc_id": doc_id}


def delete_document(doc_id: str) -> dict:
    """Delete a document using advanced features if available"""
    # Try advanced deletion first
    advanced_index = get_advanced_index()
    if advanced_index:
        try:
            return advanced_index.delete_document(doc_id)
        except Exception as e:
            logger.error(f"Advanced deletion failed for {doc_id}, falling back to basic: {e}")
    
    # Fallback to basic deletion
    client = get_client()
    try:
        client.delete(index=ELASTICSEARCH_INDEX_NAME, id=doc_id, refresh=True)
        return {"status": "success", "method": "basic", "deleted": 1}
    except Exception as e:
        logger.error(f"Basic deletion failed for {doc_id}: {e}")
        return {"status": "error", "error": str(e)}


def search(q: str, size: int = 10, **kwargs) -> dict:
    """Search documents with advanced features if available"""
    # Try advanced search first
    advanced_index = get_advanced_index()
    if advanced_index:
        try:
            results = advanced_index.hybrid_search(
                query=q,
                size=size,
                semantic_weight=kwargs.get("semantic_weight", 0.5),
                keyword_weight=kwargs.get("keyword_weight", 0.5),
                filters=kwargs.get("filters")
            )
            
            # Convert to backward-compatible format
            return {
                "hits": {
                    "total": {"value": results.get("total", 0)},
                    "hits": [
                        {
                            "_id": result["doc_id"],
                            "_score": result["score"],
                            "_source": {
                                "title": result["title"],
                                "text": result["chunks"][0]["text"][:500] if result["chunks"] else "",
                                "link": result["link"],
                                "metadata": {
                                    "source": result["source"],
                                    "file_type": result.get("file_type"),
                                    "indexed_at": result.get("indexed_at"),
                                    "chunks": len(result["chunks"])
                                }
                            },
                            "highlight": result["chunks"][0].get("highlight", {}) if result["chunks"] else {}
                        }
                        for result in results.get("results", [])
                    ]
                },
                "took": results.get("took", 0)
            }
        except Exception as e:
            logger.error(f"Advanced search failed, falling back to basic: {e}")
    
    # Fallback to basic search
    client = get_client()
    ensure_index(client)
    res = client.search(
        index=ELASTICSEARCH_INDEX_NAME,
        query={
            "multi_match": {
                "query": q,
                "fields": ["title^2", "text"],
            }
        },
        size=size,
    )
    return res


# Advanced search functions (only available if advanced indexing is enabled)
def semantic_search(query: str, size: int = 10, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Perform semantic search (advanced feature)"""
    advanced_index = get_advanced_index()
    if not advanced_index:
        raise RuntimeError("Advanced indexing not available for semantic search")
    return advanced_index.hybrid_search(
        query=query, size=size, semantic_weight=1.0, keyword_weight=0.0, filters=filters
    )


def keyword_search(query: str, size: int = 10, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Perform keyword-only search (advanced feature)"""
    advanced_index = get_advanced_index()
    if not advanced_index:
        raise RuntimeError("Advanced indexing not available for keyword search")
    return advanced_index.hybrid_search(
        query=query, size=size, semantic_weight=0.0, keyword_weight=1.0, filters=filters
    )


def hybrid_search(query: str, size: int = 10, semantic_weight: float = 0.5, 
                 keyword_weight: float = 0.5, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Perform hybrid search (advanced feature)"""
    advanced_index = get_advanced_index()
    if not advanced_index:
        raise RuntimeError("Advanced indexing not available for hybrid search")
    return advanced_index.hybrid_search(
        query=query, size=size, semantic_weight=semantic_weight, 
        keyword_weight=keyword_weight, filters=filters
    )


def get_index_stats() -> Dict[str, Any]:
    """Get index statistics"""
    advanced_index = get_advanced_index()
    if advanced_index:
        return advanced_index.get_index_stats()
    
    # Basic stats
    client = get_client()
    try:
        count_resp = client.count(index=ELASTICSEARCH_INDEX_NAME)
        return {
            "total_documents": count_resp["count"],
            "method": "basic",
            "embeddings_enabled": False
        }
    except Exception as e:
        return {"error": str(e)}


# Configuration
def use_advanced_indexing(enable: bool = True):
    """Enable or disable advanced indexing"""
    global _use_advanced
    _use_advanced = enable
    if not enable:
        global _advanced_index
        _advanced_index = None
