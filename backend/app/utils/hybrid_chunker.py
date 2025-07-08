import json
import re
from typing import List, Dict, Any
from app.utils.text_chunker import TextChunker

def hybrid_chunk_text(text: str, filename: str) -> List[Dict[str, Any]]:
    """
    Smart chunking: detects JSON, JSONL, embedded JSON, or plain text.
    Handles:
    - JSON arrays
    - Single JSON objects
    - Long text fields inside JSON
    - JSONL (line-delimited JSON)
    - Embedded JSON in unstructured text
    - Fallback to semantic chunking
    """

    chunker = TextChunker(
        chunk_size=800,
        overlap=160,
        min_chunk_size=200,
        sentence_aware=True,
        paragraph_aware=True
    )

    chunks = []

    # Case 1: Entire file is a valid JSON array or object
    try:
        data = json.loads(text)
        if isinstance(data, list):
            print(f"[CHUNKER] Using case: JSON array from file: {filename}")
            for i, item in enumerate(data):
                if isinstance(item, dict):
                    chunks.extend(_chunk_json_object(item, filename, chunker, index_prefix=i))
                else:
                    chunks.append(_make_json_chunk(item, filename, i, len(data)))
            return chunks
        elif isinstance(data, dict):
            print(f"[CHUNKER] Using case: Single JSON object from file: {filename}")
            return _chunk_json_object(data, filename, chunker)
    except json.JSONDecodeError:
        pass

    # Case 2: JSONL (Line-delimited JSON)
    jsonl_lines = text.strip().splitlines()
    if all(_is_valid_json_line(line) for line in jsonl_lines):
        print(f"[CHUNKER] Using case: JSONL (line-delimited JSON) from file: {filename}")
        for i, line in enumerate(jsonl_lines):
            obj = json.loads(line)
            if isinstance(obj, dict):
                chunks.extend(_chunk_json_object(obj, filename, chunker, index_prefix=i))
            else:
                chunks.append(_make_json_chunk(obj, filename, i, len(jsonl_lines)))
        return chunks

    # Case 3: Embedded JSON objects inside text
    json_pattern = re.compile(r'{[\s\S]+?}', re.MULTILINE)
    last_end = 0
    embedded_jsons = []

    for match in json_pattern.finditer(text):
        candidate = match.group()
        try:
            parsed = json.loads(candidate)

            # Add preceding plain text as semantic chunks
            if match.start() > last_end:
                plain_chunk = text[last_end:match.start()]
                embedded_jsons.extend(_chunk_plain_text(plain_chunk, filename, chunker))

            parent_id = parsed.get("id") or parsed.get("doc_id") or None

            embedded_chunk = _make_json_chunk(parsed, filename, len(embedded_jsons), -1)
            embedded_chunk["record_type"] = "embedded_json_object"
            if parent_id is not None:
                embedded_chunk["parent_id"] = parent_id

            embedded_jsons.append(embedded_chunk)
            last_end = match.end()

        except json.JSONDecodeError:
            continue

    if embedded_jsons:
        if last_end < len(text):
            trailing_text = text[last_end:]
            embedded_jsons.extend(_chunk_plain_text(trailing_text, filename, chunker))
        print(f"[CHUNKER] Using case: Embedded JSON objects in text from file: {filename}")
        return embedded_jsons

    # Case 4: Fully semantic fallback
    print(f"[CHUNKER] Using case: Plain text fallback for file: {filename}")
    return _chunk_plain_text(text, filename, chunker)

def _chunk_json_object(obj: Dict[str, Any], filename: str, chunker: TextChunker, index_prefix: int = 0, parent_key: str = "") -> List[Dict[str, Any]]:
    chunks = []
    chunk_index = 0
    document_id = obj.get("id") or obj.get("doc_id") or f"{filename}_{index_prefix}"

    for key, value in obj.items():
        full_key = f"{parent_key}.{key}" if parent_key else key

        if isinstance(value, str) and len(value) > chunker.chunk_size:
            # semantic chunking for long strings
            sub_chunks = chunker.create_chunks(value)
            for sub in sub_chunks:
                chunks.append({
                    "source": filename,
                    "content_type": "application/json",
                    "text": sub['text'],
                    "original_length": len(sub['text']),
                    "json_key": full_key,
                    "chunk_number": chunk_index,
                    "document_id": document_id,
                    "record_type": "json_field_chunk"
                })
                chunk_index += 1

        elif isinstance(value, dict):
            # recursively chunk nested dict
            sub_chunks = _chunk_json_object(value, filename, chunker, index_prefix, full_key)
            chunks.extend(sub_chunks)
            chunk_index += len(sub_chunks)

        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    sub_chunks = _chunk_json_object(item, filename, chunker, index_prefix, f"{full_key}[{i}]")
                    chunks.extend(sub_chunks)
                    chunk_index += len(sub_chunks)
                else:
                    chunk_text = json.dumps({full_key: item})
                    chunks.append({
                        "source": filename,
                        "content_type": "application/json",
                        "text": chunk_text,
                        "original_length": len(chunk_text),
                        "json_key": f"{full_key}[{i}]",
                        "chunk_number": chunk_index,
                        "document_id": document_id,
                        "record_type": "json_field"
                    })
                    chunk_index += 1
        else:
            chunk_text = json.dumps({full_key: value})
            chunks.append({
                "source": filename,
                "content_type": "application/json",
                "text": chunk_text,
                "original_length": len(chunk_text),
                "json_key": full_key,
                "chunk_number": chunk_index,
                "document_id": document_id,
                "record_type": "json_field"
            })
            chunk_index += 1

    total = len(chunks)
    for c in chunks:
        c["total_chunks"] = total
    
    return chunks

def _make_json_chunk(item: Any, filename: str, index: int, total: int) -> Dict[str, Any]:
    return {
        "source": filename,
        "content_type": "application/json",
        "text": json.dumps(item, ensure_ascii=False, indent=2),
        "original_length": len(json.dumps(item)),
        "chunk_number": index,
        "total_chunks": total,
        "start_pos": 0,
        "end_pos": 0,
        "record_type": "json_object"
    }

def _chunk_plain_text(text: str, filename: str, chunker: TextChunker) -> List[Dict[str, Any]]:
    semantic_chunks = chunker.create_chunks(text)
    doc_id = f"{filename}_plain"

    return [
        {
            "source": filename,
            "content_type": "text/plain",
            "text": chunk['text'],
            "original_length": len(chunk['text']),
            "chunk_number": chunk['index'],
            "total_chunks": len(semantic_chunks),
            "start_pos": chunk['start_pos'],
            "end_pos": chunk['end_pos'],
            "is_sentence_boundary": chunk.get('is_sentence_boundary', False),
            "is_paragraph_boundary": chunk.get('is_paragraph_boundary', False),
            "record_type": "text_chunk",
            "document_id": doc_id 
        }
        for chunk in semantic_chunks
    ]

def _is_valid_json_line(line: str) -> bool:
    try:
        json.loads(line)
        return True
    except json.JSONDecodeError:
        return False