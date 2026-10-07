"""Build the RAG index from the knowledge/ folder.

Usage (from the repo root):
    backend/.venv/Scripts/python scripts/ingest_knowledge.py            # build index
    backend/.venv/Scripts/python scripts/ingest_knowledge.py --query "What is an ERA?"   # build + test search
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.rag.ingest import build_index  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--query", action="append", default=[], help="run a test search after building")
    args = parser.parse_args()

    settings = get_settings()
    configure_logging("INFO")
    store = build_index(settings)
    print(f"\nIndexed {store.manifest['n_documents']} documents into {store.manifest['n_chunks']} chunks "
          f"({store.manifest['embedding_model']}, dim={store.manifest['dimension']}) -> {settings.index_dir}")

    if args.query:
        from app.rag.retriever import HybridRetriever

        retriever = HybridRetriever(settings)
        retriever.load()
        for q in args.query:
            print(f"\nQ: {q}")
            for r in retriever.retrieve(q):
                print(f"  {r.score:.3f}  (dense {r.dense_score:.3f}, bm25 {r.lexical_score:.2f})  "
                      f"{r.chunk.document} :: {r.chunk.section}")


if __name__ == "__main__":
    main()
