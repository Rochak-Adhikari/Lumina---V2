"""Message Chunker for Lumina Continuity.

Splits long natural-language messages into coherent, bounded semantic chunks
while preserving source spans and context across chunk boundaries.
"""
from dataclasses import dataclass
import hashlib
import re
from typing import List, Tuple


@dataclass
class TextChunk:
    chunk_id: str
    index: int
    text: str
    start_char: int
    end_char: int
    total_chunks: int

    def to_dict(self):
        return {
            'chunk_id': self.chunk_id,
            'index': self.index,
            'text': self.text,
            'start_char': self.start_char,
            'end_char': self.end_char,
            'total_chunks': self.total_chunks,
        }


class MessageChunker:
    """Divides text into independently processable semantic chunks with source spans."""

    def __init__(self, target_chars: int = 800, max_chars: int = 1400, overlap_chars: int = 100):
        self.target_chars = target_chars
        self.max_chars = max_chars
        self.overlap_chars = overlap_chars

    def chunk_message(self, text: str, message_id: str = None) -> List[TextChunk]:
        """Split a message into bounded chunks with precise source spans."""
        if not text or not isinstance(text, str):
            return []

        clean = text.strip()
        if not clean:
            return []

        msg_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]
        base_id = f"msg_{message_id or msg_hash}"

        # If text is within comfortable single-chunk size, return directly
        if len(text) <= self.target_chars:
            return [TextChunk(
                chunk_id=f"{base_id}_c0",
                index=0,
                text=text,
                start_char=0,
                end_char=len(text),
                total_chunks=1
            )]

        # Find logical split points
        paragraphs = self._split_semantic_units(text)
        chunks_spans: List[Tuple[int, int]] = []
        
        current_start = 0
        current_end = 0

        for unit_start, unit_end in paragraphs:
            unit_len = unit_end - unit_start
            
            # If adding unit exceeds max_chars and we already have content
            if current_end > current_start and (unit_end - current_start) > self.max_chars:
                chunks_spans.append((current_start, current_end))
                # Next chunk starts with overlap if possible
                overlap_start = max(current_start, current_end - self.overlap_chars)
                # Find nearest word break for overlap
                space_idx = text.find(' ', overlap_start, current_end)
                if space_idx != -1 and space_idx + 1 < current_end:
                    current_start = space_idx + 1
                else:
                    current_start = current_end
                current_end = unit_end
            else:
                current_end = unit_end

        if current_end > current_start:
            chunks_spans.append((current_start, current_end))

        # Build TextChunk instances
        total = len(chunks_spans)
        chunks: List[TextChunk] = []
        for i, (s, e) in enumerate(chunks_spans):
            chunk_text = text[s:e].strip()
            chunks.append(TextChunk(
                chunk_id=f"{base_id}_c{i}",
                index=i,
                text=chunk_text,
                start_char=s,
                end_char=e,
                total_chunks=total
            ))

        return chunks

    def _split_semantic_units(self, text: str) -> List[Tuple[int, int]]:
        """Identify boundaries by paragraphs, list items, or sentence breaks."""
        units: List[Tuple[int, int]] = []
        # Pattern for major break: double newlines or numbered/bulleted lists
        pattern = re.compile(r'(?:\r?\n\s*\r?\n|\r?\n(?=\s*(?:[-*•]|\d+[.)]))|[.!?]\s+(?=[A-Z]))')
        
        last_pos = 0
        for match in pattern.finditer(text):
            end_pos = match.end()
            if end_pos - last_pos >= 60:  # avoid micro-units
                units.append((last_pos, end_pos))
                last_pos = end_pos

        if last_pos < len(text):
            units.append((last_pos, len(text)))

        return units

