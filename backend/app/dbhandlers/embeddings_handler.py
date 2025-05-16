import asyncio
import functools
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.http import models

from app.constants import QDRANT_COLLECTION_NAME
from app.config import QDRANT_API_URL, QDRANT_API_KEY
from app.models.api.rag_pipeline import DocumentEmbedding
from app.utils.vector_utils import prepare_point

class EmbeddingsHandler:
    """Handles embedding storage and querying in Qdrant vector database."""

    def __init__(self):
        """Initialize the Qdrant client and ensure collection exists."""
        try:
            self.client = QdrantClient(
                url=QDRANT_API_URL, 
                api_key=QDRANT_API_KEY, 
                prefer_grpc=True
            )
            self._ensure_collection_exists()
        except Exception as e:
            print(f"Error initializing EmbeddingsHandler: {str(e)}")

    def _ensure_collection_exists(self, vector_size: int = 1024):
        """Ensures the Qdrant collection exists, creates it if not."""
        try:
            if not self.client.collection_exists(collection_name=QDRANT_COLLECTION_NAME):
                self.client.create_collection(
                    collection_name=QDRANT_COLLECTION_NAME,
                    vectors_config=models.VectorParams(
                        size=vector_size,
                        distance=models.Distance.COSINE,
                        on_disk=True 
                    ),
                    optimizers_config=models.OptimizersConfigDiff(
                        indexing_threshold=1000, 
                        memmap_threshold=20000,
                        max_optimization_threads=2
                    ),
                    hnsw_config=models.HnswConfigDiff(
                        payload_m=16,
                        ef_construct=100,
                        max_indexing_threads=2
                    ),
                    wal_config=models.WalConfigDiff(
                        wal_capacity_mb=512,
                        wal_segments_ahead=1
                    )
                )

                self.client.create_payload_index(
                    collection_name=QDRANT_COLLECTION_NAME,
                    field_name="text",
                    field_schema=models.TextIndexParams(
                        type="text",
                        tokenizer="word",
                        min_token_len=2,
                        max_token_len=20,
                        lowercase=True
                    )
                )
        except Exception as e:
            print(f"Error ensuring collection exists: {str(e)}")
            raise

    async def store_embeddings(
        self, 
        embeddings: List[DocumentEmbedding]
    ) -> Dict[str, Any]:
        if not embeddings:
            return {"status": "success", "stored": 0, "failed": 0, "total": 0}
        
        batch_size = 100 

        stats = {
            "stored": 0,
            "failed": 0,
            "total": len(embeddings)
        }

        for i in range(0, len(embeddings), batch_size):
            batch = embeddings[i:i + batch_size]
            points = []

            point_chunks = [batch[j:j+20] for j in range(0, len(batch), 20)]

            for chunk in point_chunks:
                try:
                    points.extend([prepare_point(e) for e in chunk])
                except Exception as e:
                    print(f"Point preparation failed: {str(e)}")
                    stats["failed"] += len(chunk)
                    continue
        
            if not points:
                continue
            
            try:
                operation_info = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.client.upsert(
                        collection_name=QDRANT_COLLECTION_NAME,
                        points=points,
                        wait=True
                    )
                )

                stats["stored"] += len(points)
                print(f"Stored batch {i // batch_size + 1} with {len(points)} points")
            except Exception as e:
                print(f"Batch storage failed: {str(e)}")
                stats["failed"] += len(points)
       
        return stats
    
    async def query_embeddings(
        self,
        vector: List[float],
        top_k: int = 10,
        includes_values: bool = False,
        filter_condition: Optional[models.Filter] = None,
        score_threshold: Optional[float] = None
    ) -> List[Dict]:
        try:
            if not vector:
                print("Error: Empty query vector")
                return []
            
            query_params = {
                "collection_name": QDRANT_COLLECTION_NAME,
                "query_vector": vector,
                "limit": top_k,
                "with_payload": True,
                "with_vectors": includes_values
            }
            
            if filter_condition:
                query_params["query_filter"] = filter_condition
                
            if score_threshold is not None:
                query_params["score_threshold"] = score_threshold

            if hasattr(self.client, 'search_async'):
                search_results = await self.client.search_async(**query_params)
            else:
                search_results = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.client.search(**query_params)
                )

            return [
                {
                    "id": str(match.id),
                    "values": match.vector if includes_values else [],
                    "metadata": match.payload or {},
                    "score": match.score
                }
                for match in search_results
            ]
        
        except Exception as e:
            print(f"Query error: {str(e)}")
            return []