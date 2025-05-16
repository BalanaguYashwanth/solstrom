import hashlib
import re
import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Dict, Any

from app.services.embeddings_service import EmbeddingService
from app.models.api.rag_pipeline import DocumentEmbedding, DocumentMetadata
from app.utils.text_chunker import TextChunker

async def process_batch(batch: List[Dict], stats: Dict, embedding_queue: asyncio.Queue):
        """Process a batch of documents and add to queue"""
        for doc in batch:
            if isinstance(doc, dict):
                stats['chunks_processed'] += 1
                await embedding_queue.put(doc)
                print(f"Chunk {stats['chunks_processed']} queued")

async def embedding_consumer(
        custom_metadata: Optional[Dict], 
        stats: Dict,
        embedding_queue: asyncio.Queue,
        stop_event: asyncio.Event,
        executor: ThreadPoolExecutor,
        embeddings_handler
):
    """Consumer that processes embeddings from queue"""
    while not stop_event.is_set() or not embedding_queue.empty():
        try:
            doc = await asyncio.wait_for(embedding_queue.get(), timeout=1.0)
            embedding = await generate_embeddings_batch([doc], custom_metadata, executor)

            if embedding:
                stats['embeddings_generated'] += 1
                print(f"Generated embedding {stats['embeddings_generated']}")
                storage_result = await embeddings_handler.store_embeddings([embedding])

                if storage_result['stored'] == 1:
                    stats['stored_embeddings'] = stats.get('stored_embeddings', 0) + 1
                else:
                    stats['failed_storage'] = stats.get('failed_storage', 0) + 1
                    print(f"Failed to store embedding {stats['embeddings_generated']}")
                    
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            stats['failed_embeddings'] += 1
            print(f"Embedding failed: {str(e)}")

async def process_text_file(text: str, filename: str) -> List[Dict]:
    """Process text file into chunks with overlapping context"""
    
    chunker = TextChunker(
        chunk_size=1000,  
        overlap=200,
        min_chunk_size=200,
        sentence_aware=True,
        paragraph_aware=True      
    )
    chunks = chunker.create_chunks(text)
    
    result = []
    for chunk in chunks:
        result.append({
            "source": filename,
            "content_type": "text/plain",
            "text": chunk['text'],
            "original_length": len(chunk['text']), 
            "chunk_number": chunk['index'],
            "total_chunks": len(chunks),
            "start_pos": chunk['start_pos'],
            "end_pos": chunk['end_pos'],
            "is_sentence_boundary": chunk.get('is_sentence_boundary', False),
            "is_paragraph_boundary": chunk.get('is_paragraph_boundary', False),
            "record_type": "text_chunk"
        })

    return result

async def generate_embeddings_batch(
    batch: List[Dict], 
    custom_metadata: Optional[Dict],
    executor: ThreadPoolExecutor
) -> List[DocumentEmbedding]:
    """Generate embeddings for a single document"""
    if not batch:
        return None
    loop = asyncio.get_event_loop()
    try:
        embedding = await loop.run_in_executor(
            executor,
            functools.partial(create_document_embedding, batch[0], custom_metadata)
        )
        return embedding
    except Exception as e:
        print(f"Embedding generation error: {str(e)}")
        return None
 
def create_document_embedding(
    document: Dict,
    custom_metadata: Optional[Dict] = None
) -> DocumentEmbedding:
    """Create embedding for a text chunk"""
    try:
        text_to_hash = document['text'] + document['source'] + str(document['chunk_number'])
        content_hash = hashlib.sha256(text_to_hash.encode()).hexdigest()
        int_id = int(content_hash[:15], 16) 

        embedding_text = document['text'] 
        embedding_values = EmbeddingService.create_embeddings(embedding_text)
        
        metadata = DocumentMetadata(
            source=document['source'],
            content_type=document['content_type'],
            text=document['text'],
            document_id=f"doc_{int_id}",
            text_length=document.get('original_length', len(document['text'])),
            truncated=False,
            record_type=document['record_type'],
            chunk_number=document['chunk_number'],
            total_chunks=document['total_chunks'],
            custom_fields=custom_metadata or {}
        )

        return DocumentEmbedding(
            id=int_id,
            values=embedding_values,
            metadata=metadata
        )
    except Exception as e:
        print(f"Error creating embedding: {str(e)}")
        raise

def format_context_texts(query_response: List[Dict]) -> List[str]:
    """Extract and format text from query response"""
    return [
        item['metadata']['text'] 
        for item in query_response 
        if isinstance(item, dict) and 
           'metadata' in item and 
           isinstance(item['metadata'], dict) and 
           'text' in item['metadata']
    ]
    
def extract_source_info(document: Dict[str, Any]) -> Dict[str, Any]:
    metadata = document.get("metadata", {})
    text = metadata.get("text", "")

    if "source_name" not in metadata:
        match = re.search(r'"source_name"\s*:\s*"([^"]+)"', text)
        if match:
            metadata["source_name"] = match.group(1).strip()

    if "source_url" not in metadata:
        match = re.search(r'"source_url"\s*:\s*"([^"]+)"', text)
        if match:
            metadata["source_url"] = match.group(1).strip()
        elif (url_match := re.search(r'(https?://[^\s]+)', text)):
            metadata["source_url"] = url_match.group(1).strip()
        elif "source_name" in metadata:
            normalized = (
                unicodedata.normalize("NFKD", metadata["source_name"])
                .encode("ascii", "ignore")
                .decode("utf-8")
            )
            slug = (
                re.sub(r"[^\w\s-]", "", normalized)
                .strip()
                .lower()
                .replace(" ", "-")
            )
            metadata["source_url"] = f"https://{slug}.com"

    document["metadata"] = metadata
    return document