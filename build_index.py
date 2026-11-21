"""Rebuild the help-docs search index (index/) from data/paysetu_help.txt.

Run:  .venv/bin/python build_index.py            # rebuild
      .venv/bin/python build_index.py --show     # rebuild and print every chunk title
      .venv/bin/python build_index.py --ask "What is the daily UPI limit?"   # show top 3 chunks
"""
import argparse
import sys

from paysetu_agent import rag


def main():
    parser = argparse.ArgumentParser(description="Build the PaySetu help docs index.")
    parser.add_argument("--show", action="store_true", help="print all chunk titles")
    parser.add_argument("--ask", help="print the top 3 chunks for a question (no rebuild)")
    args = parser.parse_args()

    try:
        if args.ask:
            for i, r in enumerate(rag.search(args.ask), 1):
                print(f"\n#{i}  score={r['score']}  ({r['source']})\n{r['text']}")
            return
        n = rag.build_index()
    except Exception as exc:
        if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
            sys.exit("Gemini free quota is busy (429). Wait a minute and run build_index.py again.")
        sys.exit(f"Index build failed: {exc}")

    print(f"Index built in index/ with {n} chunks.")
    if args.show:
        for c in rag.load_chunks():
            print(f"  [{c['kind']:6}] {c['source']}")


if __name__ == "__main__":
    main()
