"""
chunking.py
The single source of truth for the notebook's chunking algorithm.

Both the Data Service (which reports chunk counts) and any other component that
needs to reason about chunk boundaries import from here, so the two can never
drift apart.
"""

CHUNK_SIZE = 300
OVERLAP = 50


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = OVERLAP) -> list[str]:
    """Sliding-window chunker matching the notebook implementation."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += (chunk_size - overlap)
    return chunks
