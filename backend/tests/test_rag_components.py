from pathlib import Path

from app.ai.llm_provider import ChatMessage
from app.ai.local_llm import render_qwen3_chatml, strip_reasoning
from app.core.config import REPO_ROOT
from app.rag.chunker import chunk_document
from app.rag.ingest import discover_documents
from app.rag.lexical import BM25Index, tokenize
from app.rag.loaders import load_document
from app.rag.retriever import normalize_query


def test_markdown_loader_uses_frontmatter_and_headings():
    doc = load_document(REPO_ROOT / "knowledge" / "era_eob.md")
    assert doc.title == "ERA and EOB - Remittance Documents"
    assert doc.metadata["category"] == "remittance"
    headings = [s.heading for s in doc.sections]
    assert "What is an ERA (Electronic Remittance Advice)?" in headings


def test_definition_sections_are_single_chunks():
    doc = load_document(REPO_ROOT / "knowledge" / "era_eob.md")
    chunks = chunk_document(doc, max_chars=1000)
    era = [c for c in chunks if c.section == "What is an ERA (Electronic Remittance Advice)?"]
    assert len(era) == 1
    assert "835" in era[0].text


def test_long_sections_are_split_with_bounded_size(tmp_path: Path):
    p = tmp_path / "long.md"
    p.write_text("# T\n\n## S\n\n" + "\n\n".join(f"Paragraph {i} " + "word " * 60 for i in range(10)), encoding="utf-8")
    chunks = chunk_document(load_document(p), max_chars=500, overlap_chars=80)
    assert len(chunks) > 1
    assert all(len(c.text) <= 500 + 80 + 2 for c in chunks)


def test_discover_excludes_yaml_and_readme():
    names = {p.name for p in discover_documents(REPO_ROOT / "knowledge")}
    assert "validated_terms.yaml" not in names
    assert "era_eob.md" in names


def test_bm25_prefers_exact_acronym():
    idx = BM25Index(["The ERA is an 835 remittance", "Revenue cycle overview and stages", "EOB statement"])
    s = idx.scores("what is an ERA")
    assert s.index(max(s)) == 0


def test_tokenize_folds_plurals_and_hyphens():
    assert "denial" in tokenize("Denials")
    assert {"first", "pass"} <= set(tokenize("first-pass"))


def test_normalize_query_strips_domain_context():
    assert normalize_query("What is an ERA in Revenue Cycle Management?") == "What is an ERA"
    assert normalize_query("What is Revenue Cycle Management?") == "What is Revenue Cycle Management"


def test_chatml_render_disables_thinking():
    prompt = render_qwen3_chatml([ChatMessage("system", "sys"), ChatMessage("user", "hi")], enable_thinking=False)
    assert prompt.endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n")
    assert "<|im_start|>system\nsys<|im_end|>" in prompt


def test_strip_reasoning():
    assert strip_reasoning("<think>\nhmm\n</think>\n\nAnswer") == "Answer"
    assert strip_reasoning("Plain answer") == "Plain answer"
