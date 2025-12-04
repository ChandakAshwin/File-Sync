"""
Embeddings service for generating semantic embeddings from text
"""
from __future__ import annotations
import logging
from typing import List, Optional, Dict, Any
import numpy as np

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for generating text embeddings using sentence transformers"""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize embedding service
        
        Args:
            model_name: Name of the sentence transformer model to use
                       Default is a lightweight, fast model good for semantic search
        """
        self.model_name = model_name
        self._model = None
        self._model_dimension = None
    
    def _ensure_model_loaded(self):
        """Lazy load the sentence transformer model"""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info(f"Loading embedding model: {self.model_name}")
                self._model = SentenceTransformer(self.model_name)
                
                # Get model dimension by encoding a test string
                test_embedding = self._model.encode("test")
                self._model_dimension = len(test_embedding)
                logger.info(f"Model loaded, embedding dimension: {self._model_dimension}")
                
            except ImportError:
                raise ImportError(
                    "sentence-transformers is required for embeddings. "
                    "Install with: pip install sentence-transformers"
                )
            except Exception as e:
                logger.error(f"Failed to load embedding model {self.model_name}: {e}")
                raise
    
    @property
    def dimension(self) -> int:
        """Get the embedding dimension of the model"""
        self._ensure_model_loaded()
        return self._model_dimension
    
    def encode_text(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding for a single text
        
        Args:
            text: Text to encode
            
        Returns:
            List of floats representing the embedding, or None if encoding fails
        """
        if not text or not text.strip():
            return None
            
        try:
            self._ensure_model_loaded()
            
            # Truncate very long texts to avoid memory issues
            if len(text) > 8000:  # Rough character limit
                text = text[:8000] + "..."
                
            embedding = self._model.encode(text, convert_to_tensor=False)
            
            # Ensure it's a list of floats
            if hasattr(embedding, 'tolist'):
                embedding = embedding.tolist()
            
            return embedding
            
        except Exception as e:
            logger.error(f"Failed to encode text: {e}")
            return None
    
    def encode_batch(self, texts: List[str], batch_size: int = 32) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple texts efficiently
        
        Args:
            texts: List of texts to encode
            batch_size: Number of texts to process in each batch
            
        Returns:
            List of embeddings (same order as input texts)
        """
        if not texts:
            return []
        
        try:
            self._ensure_model_loaded()
            
            # Filter out empty texts but remember their positions
            text_positions = []
            filtered_texts = []
            
            for i, text in enumerate(texts):
                if text and text.strip():
                    # Truncate very long texts
                    if len(text) > 8000:
                        text = text[:8000] + "..."
                    filtered_texts.append(text)
                    text_positions.append(i)
            
            if not filtered_texts:
                return [None] * len(texts)
            
            # Generate embeddings in batches
            all_embeddings = []
            for i in range(0, len(filtered_texts), batch_size):
                batch = filtered_texts[i:i + batch_size]
                
                try:
                    batch_embeddings = self._model.encode(
                        batch, 
                        convert_to_tensor=False,
                        show_progress_bar=False
                    )
                    
                    # Convert to list format
                    if hasattr(batch_embeddings, 'tolist'):
                        batch_embeddings = batch_embeddings.tolist()
                    
                    # Handle single embedding case
                    if len(batch) == 1 and not isinstance(batch_embeddings[0], list):
                        batch_embeddings = [batch_embeddings.tolist()]
                    
                    all_embeddings.extend(batch_embeddings)
                    
                except Exception as e:
                    logger.error(f"Failed to encode batch {i//batch_size + 1}: {e}")
                    # Add None for failed batch
                    all_embeddings.extend([None] * len(batch))
            
            # Reconstruct full result list with None for empty inputs
            result = [None] * len(texts)
            for pos, embedding in zip(text_positions, all_embeddings):
                result[pos] = embedding
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to encode batch: {e}")
            return [None] * len(texts)
    
    def compute_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """
        Compute cosine similarity between two embeddings
        
        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
            
        Returns:
            Cosine similarity score between -1 and 1
        """
        try:
            vec1 = np.array(embedding1)
            vec2 = np.array(embedding2)
            
            # Compute cosine similarity
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            similarity = dot_product / (norm1 * norm2)
            return float(similarity)
            
        except Exception as e:
            logger.error(f"Failed to compute similarity: {e}")
            return 0.0


class CachedEmbeddingService(EmbeddingService):
    """Embedding service with simple in-memory caching"""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2", cache_size: int = 1000):
        super().__init__(model_name)
        self.cache_size = cache_size
        self._cache: Dict[str, List[float]] = {}
    
    def encode_text(self, text: str) -> Optional[List[float]]:
        """Encode text with caching support"""
        if not text or not text.strip():
            return None
        
        # Create cache key (hash of normalized text)
        cache_key = str(hash(text.strip().lower()))
        
        # Check cache first
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Generate embedding
        embedding = super().encode_text(text)
        
        # Cache the result
        if embedding is not None:
            # Simple LRU: remove oldest if cache is full
            if len(self._cache) >= self.cache_size:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
            
            self._cache[cache_key] = embedding
        
        return embedding


# Factory function to create appropriate embedding service
def create_embedding_service(use_cache: bool = True, 
                           model_name: str = "all-MiniLM-L6-v2") -> EmbeddingService:
    """
    Create an embedding service instance
    
    Args:
        use_cache: Whether to use caching (recommended)
        model_name: Sentence transformer model name
        
    Returns:
        EmbeddingService instance
    """
    if use_cache:
        return CachedEmbeddingService(model_name)
    else:
        return EmbeddingService(model_name)