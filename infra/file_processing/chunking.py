"""
Document chunking service for splitting text into searchable chunks
"""
from __future__ import annotations
import re
from typing import List, Dict, Any
from dataclasses import dataclass


@dataclass
class DocumentChunk:
    """Represents a chunk of a document with metadata"""
    chunk_id: str
    text: str
    chunk_index: int
    start_char: int
    end_char: int
    token_count: int
    metadata: Dict[str, Any]


class DocumentChunker:
    """Splits documents into overlapping chunks for better search"""
    
    def __init__(self, 
                 chunk_size: int = 512, 
                 overlap_size: int = 50,
                 min_chunk_size: int = 100):
        """
        Initialize chunker with specified parameters
        
        Args:
            chunk_size: Target size of each chunk in tokens (approximate)
            overlap_size: Number of tokens to overlap between chunks
            min_chunk_size: Minimum chunk size to avoid tiny chunks
        """
        self.chunk_size = chunk_size
        self.overlap_size = overlap_size
        self.min_chunk_size = min_chunk_size
    
    def chunk_document(self, doc_id: str, text: str, metadata: Dict[str, Any] = None) -> List[DocumentChunk]:
        """
        Split a document into chunks
        
        Args:
            doc_id: Unique identifier for the document
            text: Full text content to chunk
            metadata: Additional metadata to include with each chunk
            
        Returns:
            List of DocumentChunk objects
        """
        if not text or len(text.strip()) < self.min_chunk_size:
            return []
        
        metadata = metadata or {}
        
        # Split into sentences first for better chunk boundaries
        sentences = self._split_into_sentences(text)
        if not sentences:
            return []
        
        chunks = []
        current_chunk_text = ""
        current_start = 0
        chunk_index = 0
        sentence_start = 0
        
        for sentence in sentences:
            # Estimate if adding this sentence would exceed chunk size
            potential_text = current_chunk_text + (" " if current_chunk_text else "") + sentence
            potential_tokens = self._estimate_tokens(potential_text)
            
            if potential_tokens > self.chunk_size and current_chunk_text:
                # Create chunk from current text
                chunk = self._create_chunk(
                    doc_id, current_chunk_text, chunk_index, 
                    current_start, sentence_start, metadata
                )
                chunks.append(chunk)
                
                # Start new chunk with overlap
                overlap_text = self._get_overlap_text(current_chunk_text)
                current_chunk_text = overlap_text + (" " if overlap_text else "") + sentence
                current_start = max(0, sentence_start - len(overlap_text))
                chunk_index += 1
            else:
                # Add sentence to current chunk
                current_chunk_text = potential_text
                if not current_chunk_text.strip():
                    current_start = sentence_start
            
            sentence_start += len(sentence) + 1  # +1 for space
        
        # Handle final chunk
        if current_chunk_text.strip() and len(current_chunk_text.strip()) >= self.min_chunk_size:
            chunk = self._create_chunk(
                doc_id, current_chunk_text, chunk_index,
                current_start, len(text), metadata
            )
            chunks.append(chunk)
        
        return chunks
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences using regex patterns"""
        # Clean up text
        text = re.sub(r'\s+', ' ', text.strip())
        
        # Split on sentence boundaries
        sentence_pattern = r'(?<=[.!?])\s+(?=[A-Z])|(?<=\.)\s+(?=\d)|(?<=[.!?])\s*\n+\s*'
        sentences = re.split(sentence_pattern, text)
        
        # Filter out empty sentences and very short ones
        sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 10]
        
        return sentences
    
    def _estimate_tokens(self, text: str) -> int:
        """Rough token count estimation (1 token ≈ 4 characters)"""
        return max(1, len(text) // 4)
    
    def _get_overlap_text(self, text: str) -> str:
        """Get overlap text from the end of current chunk"""
        words = text.split()
        if len(words) <= self.overlap_size:
            return text
        
        overlap_words = words[-self.overlap_size:]
        return " ".join(overlap_words)
    
    def _create_chunk(self, doc_id: str, text: str, chunk_index: int,
                     start_char: int, end_char: int, metadata: Dict[str, Any]) -> DocumentChunk:
        """Create a DocumentChunk object"""
        chunk_id = f"{doc_id}#chunk_{chunk_index}"
        token_count = self._estimate_tokens(text)
        
        chunk_metadata = {
            **metadata,
            "parent_doc_id": doc_id,
            "chunk_index": chunk_index,
            "is_chunk": True
        }
        
        return DocumentChunk(
            chunk_id=chunk_id,
            text=text.strip(),
            chunk_index=chunk_index,
            start_char=start_char,
            end_char=end_char,
            token_count=token_count,
            metadata=chunk_metadata
        )


class SmartChunker(DocumentChunker):
    """Enhanced chunker that respects document structure"""
    
    def chunk_document(self, doc_id: str, text: str, metadata: Dict[str, Any] = None) -> List[DocumentChunk]:
        """
        Smart chunking that tries to respect paragraph and section boundaries
        """
        if not text or len(text.strip()) < self.min_chunk_size:
            return []
        
        metadata = metadata or {}
        
        # First try to split by paragraphs
        paragraphs = self._split_into_paragraphs(text)
        if not paragraphs:
            # Fallback to sentence-based chunking
            return super().chunk_document(doc_id, text, metadata)
        
        chunks = []
        current_chunk_text = ""
        current_start = 0
        chunk_index = 0
        para_start = 0
        
        for paragraph in paragraphs:
            potential_text = current_chunk_text + ("\n\n" if current_chunk_text else "") + paragraph
            potential_tokens = self._estimate_tokens(potential_text)
            
            if potential_tokens > self.chunk_size and current_chunk_text:
                # Create chunk from current paragraphs
                chunk = self._create_chunk(
                    doc_id, current_chunk_text, chunk_index,
                    current_start, para_start, metadata
                )
                chunks.append(chunk)
                
                # Check if single paragraph is too large
                if self._estimate_tokens(paragraph) > self.chunk_size:
                    # Split large paragraph using sentence-based approach
                    para_chunks = super().chunk_document(
                        f"{doc_id}_para_{chunk_index}", paragraph, metadata
                    )
                    for para_chunk in para_chunks:
                        para_chunk.chunk_id = f"{doc_id}#chunk_{chunk_index}"
                        para_chunk.metadata["parent_doc_id"] = doc_id
                        para_chunk.metadata["chunk_index"] = chunk_index
                        chunks.append(para_chunk)
                        chunk_index += 1
                    
                    current_chunk_text = ""
                    current_start = para_start + len(paragraph) + 2
                else:
                    # Start new chunk with this paragraph
                    current_chunk_text = paragraph
                    current_start = para_start
                    chunk_index += 1
            else:
                # Add paragraph to current chunk
                current_chunk_text = potential_text
                if not current_chunk_text.strip():
                    current_start = para_start
            
            para_start += len(paragraph) + 2  # +2 for double newline
        
        # Handle final chunk
        if current_chunk_text.strip() and len(current_chunk_text.strip()) >= self.min_chunk_size:
            chunk = self._create_chunk(
                doc_id, current_chunk_text, chunk_index,
                current_start, len(text), metadata
            )
            chunks.append(chunk)
        
        return chunks
    
    def _split_into_paragraphs(self, text: str) -> List[str]:
        """Split text into paragraphs"""
        # Split on double newlines or significant whitespace
        paragraphs = re.split(r'\n\s*\n', text.strip())
        
        # Filter out very short paragraphs
        paragraphs = [p.strip() for p in paragraphs if p.strip() and len(p.strip()) > 50]
        
        return paragraphs