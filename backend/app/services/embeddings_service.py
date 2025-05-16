import numpy as np
from FlagEmbedding import FlagModel
from qdrant_client.http import models 
from typing import List, Optional

from app.dbhandlers.embeddings_handler import EmbeddingsHandler
from app.utils.vector_utils import pad_vector

class EmbeddingService:
    model = FlagModel(
        'BAAI/bge-small-en-v1.5',
        query_instruction_for_retrieval="Represent this sentence for searching relevant passages:",
        use_fp16=False 
    )

    @staticmethod
    def create_embeddings(text: str) -> List[float]:
        embeddings = EmbeddingService.model.encode(text)
        embeddings = np.array(embeddings)

        norm = np.linalg.norm(embeddings)
        if norm > 0:
            embeddings = embeddings / norm 

        return pad_vector(embeddings.tolist(), 1024)

    @staticmethod
    async def get_embeddings(
        vector: List[float],
        limit: int = 10,
        threshold: Optional[float] = None,
        includes_values: bool = False,
        filter_condition: Optional[models.Filter] = None
    ):
        embeddings_handler = EmbeddingsHandler()
        raw_results = await embeddings_handler.query_embeddings(
            vector=vector,
            top_k=limit,
            includes_values=includes_values,
            filter_condition=filter_condition,
            score_threshold=threshold
        )

        return raw_results
