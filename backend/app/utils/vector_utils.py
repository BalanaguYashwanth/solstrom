from qdrant_client.http import models
from typing import List

from app.models.api.rag_pipeline import DocumentEmbedding

def pad_vector(vector: List[float], target_dimension: int) -> List[float]:
    if len(vector) >= target_dimension:
        return vector[:target_dimension]
    return vector + [0.0] * (target_dimension - len(vector))

def prepare_point(embedding: DocumentEmbedding) -> models.PointStruct:
        """Prepare point structure with optimized metadata."""
        if not isinstance(embedding, DocumentEmbedding):
            raise ValueError("Invalid embedding type")
            
        metadata = embedding.metadata.model_dump()
        
        optimized_metadata = {
            "source": metadata.get("source"),
            "content_type": metadata.get("content_type"),
            "document_id": metadata.get("document_id"),
            "chunk_number": metadata.get("chunk_number"),
            "total_chunks": metadata.get("total_chunks"),
            "text": metadata.get("text", ""),
            "text_length": metadata.get("text_length", 0)
        }
        
        # Add boundary information if available
        if "is_sentence_boundary" in metadata:
            optimized_metadata["is_sentence_boundary"] = metadata["is_sentence_boundary"]
        if "is_paragraph_boundary" in metadata:
            optimized_metadata["is_paragraph_boundary"] = metadata["is_paragraph_boundary"]
            
        return models.PointStruct(
            id=embedding.id,
            vector=embedding.values,
            payload=optimized_metadata
        )