"""
Advanced Elasticsearch indexing with chunking, embeddings, hybrid search, and enhanced metadata
"""
from __future__ import annotations
import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
import json

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk, scan

from infra.file_processing.chunking import SmartChunker, DocumentChunk
from infra.file_processing.embeddings import create_embedding_service, EmbeddingService
from config.settings import settings

logger = logging.getLogger(__name__)


class AdvancedElasticsearchIndex:
    """
    Advanced Elasticsearch indexing with chunking, embeddings, and hybrid search capabilities
    """
    
    def __init__(self, 
                 index_name: str = "documents_advanced",
                 chunk_size: int = 512,
                 chunk_overlap: int = 50,
                 embedding_model: str = "all-MiniLM-L6-v2",
                 enable_embeddings: bool = True):
        """
        Initialize the advanced index
        
        Args:
            index_name: Name of the Elasticsearch index
            chunk_size: Size of document chunks in tokens
            chunk_overlap: Overlap between chunks in tokens
            embedding_model: Sentence transformer model for embeddings
            enable_embeddings: Whether to generate and store embeddings
        """
        self.index_name = index_name
        self.enable_embeddings = enable_embeddings
        
        # Initialize Elasticsearch client
        try:
            self.es = Elasticsearch(
                [settings.ELASTICSEARCH_URL],
                request_timeout=30,
                max_retries=3,
                retry_on_timeout=True
            )
            if not self.es.ping():
                raise Exception("Cannot connect to Elasticsearch")
            logger.info(f"Connected to Elasticsearch at {settings.ELASTICSEARCH_URL}")
        except Exception as e:
            logger.error(f"Failed to connect to Elasticsearch: {e}")
            raise
        
        # Initialize chunking service
        self.chunker = SmartChunker(
            chunk_size=chunk_size,
            overlap_size=chunk_overlap,
            min_chunk_size=100
        )
        
        # Initialize embedding service if enabled
        self.embedding_service: Optional[EmbeddingService] = None
        if enable_embeddings:
            try:
                self.embedding_service = create_embedding_service(
                    use_cache=True,
                    model_name=embedding_model
                )
                logger.info(f"Embeddings enabled with model: {embedding_model}")
            except Exception as e:
                logger.error(f"Failed to initialize embeddings: {e}")
                logger.info("Continuing without embeddings support")
                self.enable_embeddings = False
        
        # Ensure index exists with proper mapping
        self._ensure_index_exists()
    
    def _ensure_index_exists(self):
        """Create index with proper mapping if it doesn't exist"""
        if self.es.indices.exists(index=self.index_name):
            logger.info(f"Index {self.index_name} already exists")
            return
        
        # Define mapping
        mapping = self._create_index_mapping()
        
        try:
            self.es.indices.create(
                index=self.index_name,
                body={
                    "settings": {
                        "number_of_shards": 1,
                        "number_of_replicas": 0,
                        "analysis": {
                            "analyzer": {
                                "content_analyzer": {
                                    "type": "standard",
                                    "stopwords": "_english_"
                                }
                            }
                        }
                    },
                    "mappings": mapping
                }
            )
            logger.info(f"Created index {self.index_name} with advanced mapping")
        except Exception as e:
            logger.error(f"Failed to create index: {e}")
            raise
    
    def _create_index_mapping(self) -> Dict[str, Any]:
        """Create the index mapping with support for embeddings and enhanced metadata"""
        mapping = {
            "properties": {
                # Document identification
                "doc_id": {"type": "keyword"},
                "chunk_id": {"type": "keyword"},
                "parent_doc_id": {"type": "keyword"},
                
                # Content fields
                "title": {
                    "type": "text",
                    "analyzer": "content_analyzer",
                    "fields": {
                        "keyword": {"type": "keyword"},
                        "exact": {"type": "text", "analyzer": "keyword"}
                    }
                },
                "text": {
                    "type": "text",
                    "analyzer": "content_analyzer"
                },
                "content_preview": {"type": "text"},
                
                # Chunk-specific fields
                "is_chunk": {"type": "boolean"},
                "chunk_index": {"type": "integer"},
                "chunk_start": {"type": "integer"},
                "chunk_end": {"type": "integer"},
                "token_count": {"type": "integer"},
                
                # Enhanced metadata
                "source": {"type": "keyword"},
                "file_type": {"type": "keyword"},
                "file_extension": {"type": "keyword"},
                "file_size": {"type": "long"},
                "file_path": {"type": "keyword"},
                "mime_type": {"type": "keyword"},
                
                # Timestamps
                "created_at": {"type": "date"},
                "modified_at": {"type": "date"},
                "indexed_at": {"type": "date"},
                "last_updated": {"type": "date"},
                
                # URLs and links
                "link": {"type": "keyword"},
                "source_url": {"type": "keyword"},
                
                # Additional metadata
                "metadata": {
                    "type": "object",
                    "dynamic": True
                },
                
                # Search optimization
                "search_text": {
                    "type": "text",
                    "analyzer": "content_analyzer"
                },
                
                # Scoring fields
                "boost": {"type": "float"},
                "quality_score": {"type": "float"}
            }
        }
        
        # Add embedding field if embeddings are enabled
        if self.enable_embeddings and self.embedding_service:
            embedding_dim = self.embedding_service.dimension
            mapping["properties"]["embedding"] = {
                "type": "dense_vector",
                "dims": embedding_dim,
                "index": True,
                "similarity": "cosine"
            }
            logger.info(f"Added embedding field with {embedding_dim} dimensions")
        
        return mapping
    
    def index_document(self,
                      doc_id: str,
                      title: str,
                      text: str,
                      link: Optional[str] = None,
                      metadata: Optional[Dict[str, Any]] = None,
                      file_path: Optional[str] = None,
                      enable_chunking: bool = True) -> Dict[str, Any]:
        """
        Index a document with chunking, embeddings, and enhanced metadata
        
        Args:
            doc_id: Unique document identifier
            title: Document title
            text: Full document text
            link: Optional link to the document
            metadata: Additional metadata
            file_path: Path to the source file
            enable_chunking: Whether to split the document into chunks
            
        Returns:
            Dictionary with indexing results
        """
        if not text.strip():
            logger.warning(f"Empty text for document {doc_id}, skipping")
            return {"status": "skipped", "reason": "empty_text"}
        
        metadata = metadata or {}
        
        # Extract enhanced metadata
        enhanced_metadata = self._extract_enhanced_metadata(
            doc_id, title, text, link, metadata, file_path
        )
        
        try:
            if enable_chunking and len(text) > 1000:  # Only chunk larger documents
                return self._index_document_with_chunks(
                    doc_id, title, text, enhanced_metadata
                )
            else:
                return self._index_single_document(
                    doc_id, title, text, enhanced_metadata
                )
        except Exception as e:
            logger.error(f"Failed to index document {doc_id}: {e}")
            return {"status": "error", "error": str(e)}
    
    def _extract_enhanced_metadata(self,
                                 doc_id: str,
                                 title: str,
                                 text: str,
                                 link: Optional[str],
                                 metadata: Dict[str, Any],
                                 file_path: Optional[str]) -> Dict[str, Any]:
        """Extract enhanced metadata from document information"""
        enhanced = {
            "doc_id": doc_id,
            "title": title,
            "link": link,
            "indexed_at": datetime.utcnow().isoformat(),
            "text_length": len(text),
            "word_count": len(text.split()),
            **metadata
        }
        
        # Extract file information if available
        if file_path:
            from pathlib import Path
            path = Path(file_path)
            enhanced.update({
                "file_path": str(path),
                "file_name": path.name,
                "file_extension": path.suffix.lower().lstrip('.'),
                "file_size": path.stat().st_size if path.exists() else None
            })
            
            # Determine file type
            ext = path.suffix.lower()
            if ext in ['.pdf']:
                enhanced["file_type"] = "pdf"
            elif ext in ['.doc', '.docx']:
                enhanced["file_type"] = "document"
            elif ext in ['.ppt', '.pptx']:
                enhanced["file_type"] = "presentation"
            elif ext in ['.xls', '.xlsx']:
                enhanced["file_type"] = "spreadsheet"
            elif ext in ['.txt', '.md']:
                enhanced["file_type"] = "text"
            else:
                enhanced["file_type"] = "other"
        
        # Extract source information
        if doc_id.startswith("box:"):
            enhanced["source"] = "box"
            enhanced["source_id"] = doc_id.replace("box:", "")
        
        # Calculate quality score based on text characteristics
        enhanced["quality_score"] = self._calculate_quality_score(text)
        
        # Create search-optimized text
        search_components = [title, text]
        if metadata.get("semantic_id"):
            search_components.append(str(metadata["semantic_id"]))
        enhanced["search_text"] = " ".join(filter(None, search_components))
        
        return enhanced
    
    def _calculate_quality_score(self, text: str) -> float:
        """Calculate a quality score for the document based on text characteristics"""
        if not text:
            return 0.0
        
        # Basic metrics
        word_count = len(text.split())
        char_count = len(text)
        sentence_count = len([s for s in text.split('.') if s.strip()])
        
        # Calculate scores (0-1 range)
        length_score = min(1.0, word_count / 1000)  # Longer documents get higher scores up to 1000 words
        readability_score = min(1.0, sentence_count / (word_count / 20)) if word_count > 0 else 0.0  # Average sentence length
        
        # Combine scores
        quality_score = (length_score * 0.6 + readability_score * 0.4)
        return round(quality_score, 3)
    
    def _index_single_document(self,
                             doc_id: str,
                             title: str,
                             text: str,
                             metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Index a document without chunking"""
        doc = {
            "chunk_id": doc_id,
            "text": text,
            "content_preview": text[:500] + ("..." if len(text) > 500 else ""),
            "is_chunk": False,
            "chunk_index": 0,
            "token_count": len(text) // 4,  # Rough estimate
            **metadata
        }
        
        # Generate embedding if enabled
        if self.enable_embeddings and self.embedding_service:
            embedding = self.embedding_service.encode_text(text)
            if embedding:
                doc["embedding"] = embedding
        
        try:
            self.es.index(index=self.index_name, id=doc_id, body=doc)
            logger.info(f"Indexed single document {doc_id}")
            return {"status": "success", "chunks": 1, "doc_id": doc_id}
        except Exception as e:
            logger.error(f"Failed to index single document {doc_id}: {e}")
            raise
    
    def _index_document_with_chunks(self,
                                  doc_id: str,
                                  title: str,
                                  text: str,
                                  metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Index a document split into chunks"""
        # Generate chunks
        chunks = self.chunker.chunk_document(doc_id, text, metadata)
        
        if not chunks:
            logger.warning(f"No chunks generated for document {doc_id}")
            return {"status": "skipped", "reason": "no_chunks"}
        
        # Prepare documents for bulk indexing
        docs_to_index = []
        
        # Generate embeddings for all chunks if enabled
        embeddings = []
        if self.enable_embeddings and self.embedding_service:
            chunk_texts = [chunk.text for chunk in chunks]
            embeddings = self.embedding_service.encode_batch(chunk_texts)
        
        for i, chunk in enumerate(chunks):
            doc = {
                "chunk_id": chunk.chunk_id,
                "parent_doc_id": doc_id,
                "text": chunk.text,
                "content_preview": chunk.text[:300] + ("..." if len(chunk.text) > 300 else ""),
                "is_chunk": True,
                "chunk_index": chunk.chunk_index,
                "chunk_start": chunk.start_char,
                "chunk_end": chunk.end_char,
                "token_count": chunk.token_count,
                **chunk.metadata
            }
            
            # Add embedding if available
            if embeddings and i < len(embeddings) and embeddings[i]:
                doc["embedding"] = embeddings[i]
            
            docs_to_index.append({
                "_index": self.index_name,
                "_id": chunk.chunk_id,
                "_source": doc
            })
        
        # Bulk index all chunks
        try:
            success_count, errors = bulk(self.es, docs_to_index)
            if errors:
                logger.warning(f"Some chunks failed to index for {doc_id}: {len(errors)} errors")
            
            logger.info(f"Indexed document {doc_id} as {len(chunks)} chunks ({success_count} successful)")
            return {
                "status": "success",
                "chunks": len(chunks),
                "successful": success_count,
                "errors": len(errors) if errors else 0,
                "doc_id": doc_id
            }
        except Exception as e:
            logger.error(f"Failed to bulk index chunks for {doc_id}: {e}")
            raise
    
    def hybrid_search(self,
                     query: str,
                     size: int = 10,
                     semantic_weight: float = 0.5,
                     keyword_weight: float = 0.5,
                     filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Perform hybrid search combining keyword and semantic similarity
        
        Args:
            query: Search query
            size: Number of results to return
            semantic_weight: Weight for semantic similarity (0-1)
            keyword_weight: Weight for keyword matching (0-1)
            filters: Optional filters to apply
            
        Returns:
            Search results with combined scoring
        """
        if not query.strip():
            return {"hits": {"hits": []}, "took": 0}
        
        # Prepare filters
        filter_clauses = []
        if filters:
            for field, value in filters.items():
                if isinstance(value, list):
                    filter_clauses.append({"terms": {field: value}})
                else:
                    filter_clauses.append({"term": {field: value}})
        
        # Build hybrid query
        if self.enable_embeddings and self.embedding_service:
            return self._hybrid_search_with_embeddings(
                query, size, semantic_weight, keyword_weight, filter_clauses
            )
        else:
            return self._keyword_only_search(query, size, filter_clauses)
    
    def _hybrid_search_with_embeddings(self,
                                     query: str,
                                     size: int,
                                     semantic_weight: float,
                                     keyword_weight: float,
                                     filter_clauses: List[Dict]) -> Dict[str, Any]:
        """Perform hybrid search with embeddings"""
        # Generate query embedding
        query_embedding = self.embedding_service.encode_text(query)
        if not query_embedding:
            logger.warning("Failed to generate query embedding, falling back to keyword search")
            return self._keyword_only_search(query, size, filter_clauses)
        
        # Build query components
        queries = []
        
        # Keyword query component
        if keyword_weight > 0:
            keyword_query = {
                "bool": {
                    "should": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": ["title^2", "search_text", "text"],
                                "type": "best_fields",
                                "fuzziness": "AUTO"
                            }
                        },
                        {
                            "match_phrase": {
                                "text": {
                                    "query": query,
                                    "boost": 2.0
                                }
                            }
                        }
                    ]
                }
            }
            queries.append({"query": keyword_query, "weight": keyword_weight})
        
        # Semantic query component
        if semantic_weight > 0:
            semantic_query = {
                "script_score": {
                    "query": {"match_all": {}},
                    "script": {
                        "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                        "params": {"query_vector": query_embedding}
                    }
                }
            }
            queries.append({"query": semantic_query, "weight": semantic_weight})
        
        # Combine queries using rank feature
        search_body = {
            "size": size,
            "query": {
                "bool": {
                    "should": [q["query"] for q in queries],
                    "filter": filter_clauses if filter_clauses else []
                }
            },
            "highlight": {
                "fields": {
                    "text": {"fragment_size": 150, "number_of_fragments": 3},
                    "title": {}
                }
            },
            "_source": {
                "excludes": ["embedding"]  # Don't return large embedding vectors
            }
        }
        
        try:
            response = self.es.search(index=self.index_name, body=search_body)
            return self._process_search_results(response, query)
        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            return {"hits": {"hits": []}, "took": 0, "error": str(e)}
    
    def _keyword_only_search(self,
                           query: str,
                           size: int,
                           filter_clauses: List[Dict]) -> Dict[str, Any]:
        """Perform keyword-only search"""
        search_body = {
            "size": size,
            "query": {
                "bool": {
                    "should": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": ["title^3", "search_text^2", "text"],
                                "type": "best_fields",
                                "fuzziness": "AUTO"
                            }
                        },
                        {
                            "match_phrase": {
                                "text": {
                                    "query": query,
                                    "boost": 2.0
                                }
                            }
                        },
                        {
                            "wildcard": {
                                "title.keyword": f"*{query}*"
                            }
                        }
                    ],
                    "filter": filter_clauses if filter_clauses else []
                }
            },
            "highlight": {
                "fields": {
                    "text": {"fragment_size": 150, "number_of_fragments": 3},
                    "title": {}
                }
            }
        }
        
        try:
            response = self.es.search(index=self.index_name, body=search_body)
            return self._process_search_results(response, query)
        except Exception as e:
            logger.error(f"Keyword search failed: {e}")
            return {"hits": {"hits": []}, "took": 0, "error": str(e)}
    
    def _process_search_results(self, response: Dict, query: str) -> Dict[str, Any]:
        """Process and enhance search results"""
        # Group chunks by parent document
        doc_groups = {}
        for hit in response["hits"]["hits"]:
            source = hit["_source"]
            parent_id = source.get("parent_doc_id", source.get("doc_id", hit["_id"]))
            
            if parent_id not in doc_groups:
                doc_groups[parent_id] = {
                    "chunks": [],
                    "max_score": hit["_score"],
                    "doc_info": source
                }
            
            doc_groups[parent_id]["chunks"].append({
                "chunk_id": hit["_id"],
                "score": hit["_score"],
                "text": source.get("text", ""),
                "highlight": hit.get("highlight", {}),
                "chunk_index": source.get("chunk_index", 0)
            })
            
            # Update max score
            if hit["_score"] > doc_groups[parent_id]["max_score"]:
                doc_groups[parent_id]["max_score"] = hit["_score"]
        
        # Sort and format results
        sorted_docs = sorted(doc_groups.items(), key=lambda x: x[1]["max_score"], reverse=True)
        
        formatted_results = []
        for doc_id, doc_data in sorted_docs:
            # Sort chunks by score
            chunks = sorted(doc_data["chunks"], key=lambda x: x["score"], reverse=True)
            
            result = {
                "doc_id": doc_id,
                "title": doc_data["doc_info"].get("title", ""),
                "score": doc_data["max_score"],
                "source": doc_data["doc_info"].get("source", ""),
                "link": doc_data["doc_info"].get("link"),
                "file_type": doc_data["doc_info"].get("file_type"),
                "indexed_at": doc_data["doc_info"].get("indexed_at"),
                "chunks": chunks[:3],  # Top 3 chunks per document
                "total_chunks": len(chunks)
            }
            
            formatted_results.append(result)
        
        return {
            "query": query,
            "total": len(formatted_results),
            "took": response["took"],
            "results": formatted_results
        }
    
    def delete_document(self, doc_id: str) -> Dict[str, Any]:
        """Delete a document and all its chunks"""
        try:
            # Delete by parent document ID (handles both single docs and chunks)
            delete_query = {
                "bool": {
                    "should": [
                        {"term": {"doc_id": doc_id}},
                        {"term": {"parent_doc_id": doc_id}},
                        {"term": {"chunk_id": doc_id}}
                    ]
                }
            }
            
            response = self.es.delete_by_query(
                index=self.index_name,
                body={"query": delete_query}
            )
            
            deleted_count = response.get("deleted", 0)
            logger.info(f"Deleted {deleted_count} documents/chunks for {doc_id}")
            
            return {"status": "success", "deleted": deleted_count}
            
        except Exception as e:
            logger.error(f"Failed to delete document {doc_id}: {e}")
            return {"status": "error", "error": str(e)}
    
    def get_index_stats(self) -> Dict[str, Any]:
        """Get statistics about the index"""
        try:
            stats = self.es.indices.stats(index=self.index_name)
            count_resp = self.es.count(index=self.index_name)
            
            # Count chunks vs full documents
            chunk_count = self.es.count(
                index=self.index_name,
                body={"query": {"term": {"is_chunk": True}}}
            )["count"]
            
            full_doc_count = count_resp["count"] - chunk_count
            
            return {
                "total_documents": count_resp["count"],
                "full_documents": full_doc_count,
                "chunks": chunk_count,
                "index_size": stats["indices"][self.index_name]["total"]["store"]["size_in_bytes"],
                "embeddings_enabled": self.enable_embeddings
            }
        except Exception as e:
            logger.error(f"Failed to get index stats: {e}")
            return {"error": str(e)}


# Factory function for backward compatibility
def create_advanced_index(index_name: str = "documents_advanced",
                        enable_embeddings: bool = True) -> AdvancedElasticsearchIndex:
    """Create an advanced Elasticsearch index instance"""
    return AdvancedElasticsearchIndex(
        index_name=index_name,
        enable_embeddings=enable_embeddings
    )