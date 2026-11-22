"""Score Setu against a test set, using Gemini as the judge.

Run:  .venv/bin/python run_tests.py                              # official set: data/test_set.csv
      .venv/bin/python run_tests.py --file data/brief_checks.csv # checks taken from the Project Brief
      ... --retry-unscored    # only re-run questions that hit a Gemini rate limit last time

Test set columns: #, Question, Type, Expected answer or behaviour
Each question runs in a fresh chat. Results go to results.csv (#, question, type, reply, score, reason).
Tickets/logs from test runs go to test_runs/ so they don't fill the real sidebar.
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("PAYSETU_LOG_DIR", str(ROOT / "test_runs"))  # before importing the agent

import pandas as pd  # noqa: E402
from google.genai import types  # noqa: E402

from paysetu_agent import config, rag  # noqa: E402
from paysetu_agent.chat import BUSY_REPLY, SetuChat  # noqa: E402

REQUIRED = ["#", "Question", "Type", "Expected answer or behaviour"]

JUDGE_PROMPT = """You are grading a customer support agent for PaySetu Wallet (a UPI payments app).
Score the agent's REPLY against the EXPECTED answer or behaviour, from 1 to 5:
5 = fully correct: all expected facts/behaviour, exact amounts and limits, nothing wrong or invented.
4 = correct with a minor omission or wording issue.
3 = partly correct: some expected facts or behaviour missing.
2 = mostly wrong or missing the key behaviour.
1 = wrong, unsafe, invented facts, or broke a rule.
Replies in Hindi/Hinglish are fine when the question was in Hindi/Hinglish.
Return ONLY JSON: {"score": <1-5>, "reason": "<one short line>"}

QUESTION: {q}
EXPECTED: {e}
REPLY: {r}"""


def judge(question: str, expected: str, reply: str) -> tuple[int, str]:
    resp, _ = config.with_model_fallback(lambda model: rag._client().models.generate_content(
        model=model,
        contents=JUDGE_PROMPT.replace("{q}", question).replace("{e}", expected).replace("{r}", reply),
        config=types.GenerateContentConfig(temperature=0, response_mime_type="application/json"),
    ))
    data = json.loads(re.search(r"\{.*\}", resp.text, re.S).group(0))
    return max(1, min(5, int(data["score"]))), str(data.get("reason", "")).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="data/test_set.csv")
    parser.add_argument("--out", default="results.csv")
    parser.add_argument("--retry-unscored", action="store_true",
                        help="keep scored answers in --out and only re-run questions that were not scored")
    args = parser.parse_args()

    path = ROOT / args.file
    if not path.exists():
        sys.exit(
            f"Test set not found: {args.file}\n"
            "Download the 'Test set' tab of the PaySetu Data sheet as CSV and save it as data/test_set.csv.\n"
            "Meanwhile you can run:  python run_tests.py --file data/brief_checks.csv"
        )
    tests = pd.read_csv(path, dtype=str).fillna("")
    missing = [c for c in REQUIRED if c not in tests.columns]
    if missing:
        sys.exit(f"{args.file} is missing columns: {missing}. Found: {list(tests.columns)}")

    previous = {}
    if args.retry_unscored and (ROOT / args.out).exists():
        prev = pd.read_csv(ROOT / args.out, dtype=str).fillna("")
        previous = {r["#"]: r for _, r in prev.iterrows() if r.get("score", "0") not in ("0", "")}
        print(f"Keeping {len(previous)} scored answers from {args.out}; re-running the rest.\n")

    rows = []
    for _, t in tests.iterrows():
        if t["#"] in previous:
            p_ = previous[t["#"]]
            rows.append({"#": t["#"], "question": p_["question"], "type": p_["type"], "reply": p_["reply"],
                         "score": int(p_["score"]), "reason": p_["reason"]})
            continue
        q, e = t["Question"], t["Expected answer or behaviour"]
        for attempt in (1, 2):
            reply = SetuChat().ask(q)  # fresh session for every question
            if reply.startswith(BUSY_REPLY):
                score, reason = 0, "Not scored: Gemini was busy (rate limit). Re-run with --retry-unscored."
            else:
                try:
                    score, reason = judge(q, e, reply)
                except Exception as exc:
                    score, reason = 0, f"Not scored: judge error ({str(exc)[:80]})"
            if score or attempt == 2:
                break
            print(f"[{t['#']:>2}] busy - waiting 30 s and trying once more...")
            time.sleep(30)  # per-minute rate limit: give it time to reset
        rows.append({"#": t["#"], "question": q, "type": t["Type"], "reply": reply,
                     "score": score, "reason": reason})
        print(f"[{t['#']:>2}] {score}/5  {t['Type']:<10} {q[:55]:<55} | {reason}")
        time.sleep(2)  # stay within the free quota

    df = pd.DataFrame(rows)
    df.to_csv(ROOT / args.out, index=False)
    scored = df[df["score"] > 0]
    unscored = len(df) - len(scored)
    print(f"\nOverall average: {scored['score'].mean():.2f} / 5  ({len(scored)} scored"
          + (f", {unscored} not scored - run again with --retry-unscored" if unscored else "") + ")")
    print("By type:")
    for typ, s in scored.groupby("type")["score"].mean().items():
        print(f"  {typ:<12} {s:.2f}")
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
