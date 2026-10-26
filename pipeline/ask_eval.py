"""Accuracy of "ask the data": 30 questions with answers known from the data, put to the model and scored.

Each question in pipeline/ask_questions.json has a reference query and the answer that query gives. The model's answer
is right when its result has the same number of rows as the reference answer, and every value of each reference row
appears in a row of its result. Extra columns are fine. Numbers match to within 0.1% (or 0.005), and a month may be
written in any common form ('2025-10-01', 'Oct 2025'). A refused or failed query counts as wrong.
Writes docs/ask_eval.json, which the site and the README quote, but only once every question has a reply: a missing
reply (busy or out of quota) says nothing about accuracy. An unfinished run is kept in data/processed/ (not published),
and a second run on the same day asks only the questions that got no reply, so each question still has exactly one answer.
Usage: python -m pipeline.ask_eval [--provider gemini|claude]
       python -m pipeline.ask_eval --update-answers   (re-runs the reference queries after a data change; no model)
"""
import json
import math
import sys
import time
from datetime import date, datetime
from pathlib import Path

from pipeline.ask import DATA, PROVIDERS, Asker, Refused
from pipeline.insights import load_key

QUESTIONS = Path(__file__).with_name("ask_questions.json")
OUT = DATA.with_name("ask_eval.json")
PARTIAL = DATA.parents[1] / "data" / "processed" / "ask_eval_partial.json"  # unfinished run, kept local
PAUSE = 10  # seconds between questions, to stay under the free tier's per-minute limit
RETRIES = 2  # extra rounds for questions no model answered


def norm(v):
    """A value in a form that compares across query styles: numbers as floats, months as 'YYYY-MM-01', text lowercased."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m", "%b %Y", "%B %Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return s.lower()


def same(got, want) -> bool:
    got, want = norm(got), norm(want)
    if isinstance(got, float) and isinstance(want, float):
        return math.isclose(got, want, rel_tol=1e-3, abs_tol=0.005)
    return got == want


def matches(got_rows: list, want_rows: list) -> bool:
    """Same number of rows, and each reference row's values all found in its own row of the result (in any order)."""
    if len(got_rows) != len(want_rows):
        return False
    unused = list(got_rows)
    for want in want_rows:
        hit = next((g for g in unused if all(any(same(v, w) for v in g) for w in want)), None)
        if hit is None:
            return False
        unused.remove(hit)
    return True


def evaluate(asker: Asker, questions: list, write_sql, pause: float = 0) -> dict:
    results = []
    for i, q in enumerate(questions):
        try:
            got = asker.ask(q["question"], write_sql)
            results.append({"question": q["question"], "right": matches(got["rows"], q["answer"]), "sql": got["sql"],
                            "expected": q["answer"], "got": got["rows"][:10], "model": got["model"]})
        except Refused as e:  # the model's query was refused or did not run: a wrong answer
            results.append({"question": q["question"], "right": False, "expected": q["answer"], "error": str(e)})
        except Exception as e:  # no model answered (busy or out of quota): not wrong, but the run is incomplete
            results.append({"question": q["question"], "right": False, "no_reply": True, "expected": q["answer"],
                            "error": f"{type(e).__name__}: {e}"})
        if pause and i < len(questions) - 1:
            time.sleep(pause)
    return summary(results)


def summary(results: list) -> dict:
    models = sorted({r["model"] for r in results if "model" in r})
    return {"score": sum(r["right"] for r in results), "total": len(results), "no_reply": sum("no_reply" in r for r in results),
            "models": models, "date": date.today().isoformat(), "results": results}


def main() -> None:
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    asker = Asker(json.loads(DATA.read_text(encoding="utf-8")))
    if "--update-answers" in sys.argv:
        for q in questions:
            q["answer"] = [[round(v, 4) if isinstance(v, float) else v for v in row] for row in asker.run(q["sql"])["rows"]]
        lines = ",\n".join(" " + json.dumps(q, ensure_ascii=False) for q in questions)  # one question per line
        QUESTIONS.write_text(f"[\n{lines}\n]\n", encoding="utf-8")
        print(f"answers written for {len(questions)} questions")
        return
    provider = sys.argv[sys.argv.index("--provider") + 1] if "--provider" in sys.argv else "gemini"
    load_key(provider)
    previous = json.loads(PARTIAL.read_text(encoding="utf-8")) if PARTIAL.exists() else None
    # An unfinished run from today with the same questions and answers: ask only the questions that got no reply.
    resume = bool(previous) and previous["date"] == date.today().isoformat() and \
        [(r["question"], r["expected"]) for r in previous["results"]] == [(q["question"], q["answer"]) for q in questions]
    report = previous if resume else evaluate(asker, questions, PROVIDERS[provider], pause=PAUSE)
    for attempt in range(RETRIES + resume):  # busy free models often answer a minute later, so ask again
        missing = [i for i, r in enumerate(report["results"]) if "no_reply" in r]
        if not missing:
            break
        if attempt or not resume:
            time.sleep(60)
        again = evaluate(asker, [questions[i] for i in missing], PROVIDERS[provider], pause=PAUSE)["results"]
        report = summary([dict(zip(missing, again)).get(i, r) for i, r in enumerate(report["results"])])
    for r in report["results"]:
        label = "right " if r["right"] else "NO REPLY " if r.get("no_reply") else "WRONG "
        print(label + r["question"] + ("" if r["right"] else f"\n      {r.get('error') or r['sql']}"))
    if report["no_reply"]:
        answered = report["total"] - report["no_reply"]
        PARTIAL.parent.mkdir(parents=True, exist_ok=True)
        PARTIAL.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\n{report['score']} of the {answered} answered questions were right, but {report['no_reply']} got no reply "
              f"from any model (busy or out of quota). That is not a full score, so docs/ask_eval.json was not written. "
              f"Run this again later today and it asks only those {report['no_reply']}.")
        return
    OUT.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    PARTIAL.unlink(missing_ok=True)
    print(f"\n{report['score']} of {report['total']} right ({', '.join(report['models'])}); written to docs/ask_eval.json")


if __name__ == "__main__":
    main()
