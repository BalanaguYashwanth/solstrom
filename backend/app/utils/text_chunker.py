import re
from typing import List, Dict

class TextChunker:
    def __init__(
        self,
        chunk_size: int = 800,
        overlap: int = 160,
        min_chunk_size: int = 200,
        sentence_aware: bool = True,
        paragraph_aware: bool = True
    ):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.min_chunk_size = min_chunk_size
        self.sentence_aware = sentence_aware
        self.paragraph_aware = paragraph_aware
        self.sentence_endings = re.compile(r'[.!?]\s+')
        self.paragraph_breaks = re.compile(r'\n\s*\n')
        
    def create_chunks(self, text: str) -> List[Dict]:
        """Split text into chunks with intelligent overlapping and boundary awareness"""
        chunks = []
        text_length = len(text)
        start = 0
        index = 0
        
        while start < text_length:
            # Calculate initial end position
            end = min(start + self.chunk_size, text_length)

             # Find boundaries in one pass
            if self.sentence_aware or self.paragraph_aware:
                search_start = max(start, end - self.overlap)
                search_end = min(text_length, end + self.overlap)

                # Look for both sentence and paragraph boundaries simultaneously
                best_boundary = end
                for match in self.sentence_endings.finditer(text, search_start, search_end):
                    if match.end() <= end:
                        best_boundary = match.end()
                
                for match in self.paragraph_breaks.finditer(text, search_start, search_end):
                    if match.end() <= end and match.end() > best_boundary:
                        best_boundary = match.end()
                
                end = best_boundary if best_boundary > start else end

            # Skip empty chunks
            if end <= start:
                start += self.chunk_size - self.overlap
                continue
            
            chunks.append({
                'index': index,
                'text': text[start:end],
                'start_pos': start,
                'end_pos': end,
                'is_sentence_boundary': self._is_sentence_boundary(text, end),
                'is_paragraph_boundary': self._is_paragraph_boundary(text, end)
            })
            
            index += 1
            # Calculate next start position with overlap
            start = max(end - self.overlap, start + (self.chunk_size // 2))
            
        return chunks
    
    def _is_sentence_boundary(self, text: str, pos: int) -> bool:
        """Optimized boundary check"""
        if pos >= len(text):
            return True
        return bool(self.sentence_endings.match(text[pos-1:pos+1]))
    
    def _is_paragraph_boundary(self, text: str, pos: int) -> bool:
        """Optimized boundary check"""
        if pos >= len(text):
            return True
        return bool(self.paragraph_breaks.match(text[pos-1:pos+1]))