"""Ask the running backend one or more questions and print answer + pipeline metadata.

Usage: python scripts/ask.py "What is an ERA?" ["another question" ...] [--no-rag] [--url http://127.0.0.1:8000]
Uses only the standard library so it runs with any Python.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request


def ask(url: str, question: str, use_rag: bool) -> dict:
    body = json.dumps({"message": question, "options": {"use_rag": use_rag}}).encode()
    req = urllib.request.Request(f"{url}/api/chat", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read())


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("questions", nargs="+")
    p.add_argument("--no-rag", action="store_true")
    p.add_argument("--url", default="http://127.0.0.1:8000")
    args = p.parse_args()

    for q in args.questions:
        t0 = time.time()
        r = ask(args.url, q, not args.no_rag)
        v = r["validation"]
        print("=" * 100)
        print(f"Q: {q}")
        print(f"intent={r['intent']['intent']} ({r['intent']['confidence']}) terms={r['intent']['terms']} "
              f"grounded={r['grounded']} | validation passed={v['passed']} regenerated={v['regenerated']} "
              f"| {r['usage']['prompt_tokens']}+{r['usage']['completion_tokens']} tok | {time.time() - t0:.1f}s")
        for i in v["issues"]:
            print(f"  [{i['severity']}] {i['code']}: {i['message']}")
        print("-" * 100)
        print(r["answer"])
        if r["sources"]:
            print("Sources:")
            for s in r["sources"]:
                print(f"  [{s['ref']}] {s['title']} - {s['section']} ({s['document']}, score {s['score']})")


if __name__ == "__main__":
    main()
