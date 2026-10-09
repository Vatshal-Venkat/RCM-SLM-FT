"""Turn retrieval results into the reference context given to the SLM.

Prompt-processing cost on CPU grows with context length, and a 1.7B model gets distracted by
marginal passages, so context is filtered by relevance, de-duplicated and capped by size.

For critical terms detected in the question (ERA, EOB, Days in AR, ...), an extra retrieval is
run with the term's canonical name so its knowledge-base definition is always in context: this
is exactly where the small model is least reliable. That definition always comes from a reference
document, never from the supporting curated Q&A (knowledge/curated_qa.md).
"""

from __future__ import annotations

from app.ai.validators import load_term_rules
from app.rag.base import KnowledgeRetriever, RetrievedChunk

# Chunks scoring below this (cross-encoder probability) are not shown to the model.
MIN_CHUNK_SCORE = 0.05
# Keep chunks whose score is at least this fraction of the best chunk's score.
RELATIVE_SCORE_FLOOR = 0.1
MAX_CONTEXT_CHARS = 3600
# Knowledge-document categories that support answers but are not the authority for a definition.
SUPPORTING_CATEGORIES = {"curated_qa"}
# The curated Q&A holds several phrasings of the same answer; one is enough, the rest of the
# context goes to reference documents.
MAX_SUPPORTING_CHUNKS = 1


def _is_supporting(r: RetrievedChunk) -> bool:
    return r.chunk.metadata.get("category") in SUPPORTING_CATEGORIES


def select_context(
    results: list[RetrievedChunk],
    k: int,
    max_chars: int = MAX_CONTEXT_CHARS,
    min_score: float = MIN_CHUNK_SCORE,
    max_supporting: int = MAX_SUPPORTING_CHUNKS,
) -> list[RetrievedChunk]:
    """Filter an already-ordered result list down to the context shown to the model."""
    if not results:
        return []
    best = max(r.score for r in results)
    chosen: list[RetrievedChunk] = []
    seen: set[tuple[str, str | None]] = set()
    used = supporting = 0
    for r in results:
        if len(chosen) >= k:
            break
        if r.score < min_score or r.score < best * RELATIVE_SCORE_FLOOR:
            continue
        key = (r.chunk.document, r.chunk.section)
        # Two parts of the same section usually overlap; keep only the best-scoring one.
        if key in seen:
            continue
        if _is_supporting(r) and supporting >= max_supporting:
            continue
        if used + len(r.chunk.text) > max_chars and chosen:
            continue
        chosen.append(r)
        seen.add(key)
        used += len(r.chunk.text)
        supporting += _is_supporting(r)
    return chosen


def retrieve_context(
    retriever: KnowledgeRetriever | None, query: str, k: int = 4, terms: list[str] | None = None
) -> list[RetrievedChunk]:
    if retriever is None or not retriever.is_ready():
        return []
    # Over-fetch (reranking cost is fixed by rag_candidates) so slots freed by the filters in
    # select_context are refilled from the next-best results.
    general = retriever.retrieve(query, k=2 * k)

    # Definition chunks for critical terms go first: they are the authority for those terms.
    rules = load_term_rules()
    definitions: list[RetrievedChunk] = []
    for term in terms or []:
        rule = rules.get(term)
        if rule is None:
            continue
        hits = retriever.retrieve(f"What is {rule.name}? Definition", k=3)
        top = next((h for h in hits if not _is_supporting(h)), None)
        if top and top.score >= MIN_CHUNK_SCORE and all(d.chunk.chunk_id != top.chunk.chunk_id for d in definitions):
            definitions.append(top)

    def_ids = {d.chunk.chunk_id for d in definitions}
    ordered = definitions + [g for g in general if g.chunk.chunk_id not in def_ids]
    return select_context(ordered, k=max(k, len(definitions)))
