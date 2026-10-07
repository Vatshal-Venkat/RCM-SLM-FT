"""Section-aware chunking.

Sections (headings) are the primary unit: a definition section becomes one chunk so the model
sees the complete authoritative definition. Long sections are packed paragraph-by-paragraph up to
`max_chars`, with a small overlap carried into the next chunk.
"""

from __future__ import annotations

import hashlib
import re

from app.rag.base import Chunk
from app.rag.loaders import Document

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _split_long(paragraph: str, max_chars: int) -> list[str]:
    if len(paragraph) <= max_chars:
        return [paragraph]
    out, cur = [], ""
    for s in _SENTENCE_SPLIT.split(paragraph):
        if cur and len(cur) + len(s) + 1 > max_chars:
            out.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        out.append(cur)
    return out


def _paragraphs(text: str) -> list[str]:
    # Keep list blocks together with their lead-in line; split on blank lines.
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def chunk_document(doc: Document, max_chars: int = 1000, overlap_chars: int = 150) -> list[Chunk]:
    chunks: list[Chunk] = []
    for sec_idx, sec in enumerate(doc.sections):
        pieces: list[str] = []
        for para in _paragraphs(sec.text):
            pieces.extend(_split_long(para, max_chars))

        packed: list[str] = []
        cur = ""
        for piece in pieces:
            if cur and len(cur) + len(piece) + 2 > max_chars:
                packed.append(cur)
                tail = cur[-overlap_chars:]
                # Start the overlap on a word boundary.
                cur = (tail[tail.find(" ") + 1:] if " " in tail else tail) + "\n\n" + piece if overlap_chars else piece
            else:
                cur = f"{cur}\n\n{piece}" if cur else piece
        if cur:
            packed.append(cur)

        for part_idx, text in enumerate(packed):
            digest = hashlib.sha1(f"{doc.path.name}|{sec_idx}|{part_idx}|{text}".encode()).hexdigest()[:12]
            chunks.append(Chunk(
                chunk_id=f"{doc.path.stem}-{sec_idx:03d}-{part_idx:02d}-{digest}",
                document=doc.path.name,
                title=doc.title,
                section=sec.heading,
                text=text,
                metadata={
                    "category": doc.metadata.get("category"),
                    "source_basis": doc.metadata.get("source_basis"),
                    "page": sec.page,
                    "part": part_idx,
                },
            ))
    return chunks


def embedding_text(chunk: Chunk) -> str:
    """Text that is embedded / lexically indexed: heading context + body (contextual chunk header)."""
    header = f"{chunk.title} - {chunk.section}" if chunk.section else chunk.title
    return f"{header}\n{chunk.text}"
