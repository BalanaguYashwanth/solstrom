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
            for i, item in enumerate(data):
                if isinstance(item, dict):
                    chunks.extend(_chunk_json_object(item, filename, chunker, index_prefix=i))
                else:
                    chunks.append(_make_json_chunk(item, filename, i, len(data)))
            return chunks
        elif isinstance(data, dict):
            return _chunk_json_object(data, filename, chunker)
    except json.JSONDecodeError:
        pass

    # Case 2: JSONL (Line-delimited JSON)
    jsonl_lines = text.strip().splitlines()
    if all(_is_valid_json_line(line) for line in jsonl_lines):
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
        return embedded_jsons

    # Case 4: Fully semantic fallback
    return _chunk_plain_text(text, filename, chunker)

def _chunk_json_object(obj: Dict[str, Any], filename: str, chunker: TextChunker, index_prefix: int = 0, parent_key: str = "") -> List[Dict[str, Any]]:
    """
    Recursively traverses a JSON object, creating chunks.

    - Preserves coherent, medium-sized objects as a single 'json_subtree' chunk.
    - Chunks long text values within JSON into multiple 'json_long_text_field' chunks.
    - Captures any other leaf value (short strings, numbers, booleans) as a 'json_leaf_value' chunk to prevent data loss.
    """
    chunks = []
    chunk_index = 0
    document_id = obj.get("id") or obj.get("doc_id") or f"{filename}_{index_prefix}"

    def traverse(item, path):
        nonlocal chunk_index

        if isinstance(item, dict):
            should_preserve = (
                len(item) >= 2 and any(
                    isinstance(value, str) and len(value) > 50 or isinstance(value, (dict, list))
                    for value in item.values()
                )
            )

            raw = json.dumps(item, ensure_ascii=False)

            if should_preserve and len(raw) <= chunker.chunk_size * 1.5:
                context_enriched_text = {
                    "path": path,
                    "value": item,
                    "parent_context": _get_parent_snippet(obj, path),
                    "siblings": _get_sibling_context(obj, path)
                }
                
                chunks.append({
                    "source": filename,
                    "content_type": "application/json",
                    "text": json.dumps(context_enriched_text, ensure_ascii=False, indent=2),
                    "original_length": len(raw),
                    "json_key": path,
                    "chunk_number": chunk_index,
                    "document_id": document_id,
                    "record_type": "json_subtree",
                    "metadata": {
                        "path": path,
                        "parent_path": ".".join(path.split(".")[:-1]) if "." in path else "",
                        "depth": path.count("."),
                        "is_leaf": False
                    }
                })
                chunk_index += 1
                return

            for k, v in item.items():
                new_path = f"{path}.{k}" if path else k
                traverse(v, new_path)

        elif isinstance(item, list):
            for i, v in enumerate(item):
                new_path = f"{path}[{i}]"
                traverse(v, new_path)

        else:
            if isinstance(item, str) and len(item) > chunker.min_chunk_size:
                text_chunks = chunker.create_chunks(item)
                for i, chunk_data in enumerate(text_chunks):
                    chunks.append({
                        "source": filename,
                        "content_type": "text/plain",
                        "text": chunk_data['text'],
                        "original_length": len(chunk_data['text']),
                        "json_key": path,
                        "chunk_number": chunk_index,
                        "document_id": document_id,
                        "record_type": "json_long_text_field",
                        "metadata": {
                            "path": path,
                            "parent_path": ".".join(path.split(".")[:-1]) if "." in path else "",
                            "depth": path.count("."),
                            "is_leaf": True,
                            "split_index": i,
                            "total_splits": len(text_chunks)
                        }
                    })
                    chunk_index += 1
            
            elif item is not None and not (isinstance(item, str) and not item.strip()):
                context_enriched_text = {
                    "path": path,
                    "value": item,
                    "parent_context": _get_parent_snippet(obj, path),
                    "siblings": _get_sibling_context(obj, path)
                }
                raw_text = json.dumps(context_enriched_text, ensure_ascii=False, indent=2)
                chunks.append({
                    "source": filename,
                    "content_type": "application/json",
                    "text": raw_text,
                    "original_length": len(json.dumps(item)),
                    "json_key": path,
                    "chunk_number": chunk_index,
                    "document_id": document_id,
                    "record_type": "json_leaf_value",
                    "metadata": {
                        "path": path,
                        "parent_path": ".".join(path.split(".")[:-1]) if "." in path else "",
                        "depth": path.count("."),
                        "is_leaf": True
                    }
                })
                chunk_index += 1

    traverse(obj, parent_key)

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
    
def _get_parent_snippet(root: Dict[str, Any], path: str, max_depth: int = 2) -> Any:
    """Extract a partial subtree for context using JSON path traversal"""
    keys = re.split(r"\.|\[|\]", path)
    keys = [k for k in keys if k]

    try:
        current = root
        for depth, key in enumerate(keys[:len(keys) - max_depth]):
            if key.isdigit():
                current = current[int(key)]
            else:
                current = current.get(key, {})
        return current
    except Exception:
        return None
    
def _get_sibling_context(root: Dict[str, Any], path: str) -> Dict[str, Any]:
    keys = re.split(r"\.|\[|\]", path)
    keys = [k for k in keys if k]

    try:
        current = root
        for key in keys[:-1]:
            current = current[int(key)] if key.isdigit() else current[key]

        if isinstance(current, dict):
            return {k: v for k, v in current.items() if k != keys[-1]}
    except Exception:
        pass
    return {}