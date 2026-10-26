"""Monthly plain-English summary, written by Claude from the computed figures, with a check on every number.

Reads docs/data.json (what the site shows), computes the latest month's facts, asks Claude for a short summary,
and refuses the summary if it contains any number that is not in those facts. Writes docs/insight.json.
Usage: python -m pipeline.insights     (needs ANTHROPIC_API_KEY, or an `ant auth login` profile)
"""
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
MODEL = "claude-opus-5-5"
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
# Quantities written as words would slip past the digit check, so the summary may not use them.
# ("million" and "billion" are allowed: they follow a digit, which is checked, as in the facts' "26.3 billion".)
NUMBER_WORDS = re.compile(r"\b(two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|dozen|hundred|thousand|"
                          r"half|double[ds]?|twice|triple[ds]?|tripled|quadrupled)\b", re.I)

SYSTEM = """You write the monthly summary for UPI Pulse, a site that tracks how often UPI payments fail at India's
50 busiest banks, using NPCI's published data. Readers are shop owners, students and recruiters, not payment experts.

Write 3 or 4 short sentences of plain English: what happened this month, how it compares with last month and a year
ago, and one bank-level detail worth knowing. A technical decline means the bank's or the network's systems failed;
a business decline is a normal "no", such as a wrong PIN or a low balance. "Paying banks" send the money and
"receiving banks" receive it.

Rules:
- Use only the figures in FACTS, copied exactly as written there, including their % signs. Write every number in
  digits. Do not round, add, subtract or compare numbers yourself, and do not write words for quantities such as
  "half", "double" or "twice".
- Do not guess at causes; the data does not say why rates changed.
- No headings, lists, markdown or emoji. Return only the summary."""


def month_name(month: str) -> str:
    year, m, _ = month.split("-")
    return f"{MONTHS[int(m) - 1]} {year}"


def pct(x) -> str:
    return f"{x:.2f}%"


def facts(data: dict) -> dict:
    """The latest month's figures, already formatted the way the summary must write them."""
    months, banks = data["meta"]["months"], data["banks"]
    last = len(months) - 1
    out = {"month": month_name(months[last]), "previous_month": month_name(months[last - 1]),
           "year_ago_month": month_name(months[last - 12]), "target": "1%"}
    for side, label in (("remitter", "paying_banks"), ("beneficiary", "receiving_banks")):
        by_month = {r["m"]: r for r in data["summary"][side]}
        now, prev, year_ago = by_month[last], by_month[last - 1], by_month[last - 12]
        out[label] = {
            "technical_decline_rate": pct(now["td"]), "previous_month_technical_decline_rate": pct(prev["td"]),
            "year_ago_technical_decline_rate": pct(year_ago["td"]), "business_decline_rate": pct(now["bd"]),
            "year_ago_business_decline_rate": pct(year_ago["bd"]),
            "banks_under_target": f"{now['under']} of {now['banks']}", "year_ago_banks_under_target": str(year_ago["under"]),
            "payments": f"{now['vol'] / 1000:.1f} billion", "one_in_payments_fails_technically": f"1 in {round(100 / now['td'])}",
        }
    rows = {(r[0], r[1]): r for r in data["rows"]["remitter"]}
    current = sorted((r for (m, _), r in rows.items() if m == last), key=lambda r: -r[3])
    out["paying_banks"]["highest_technical_decline_banks"] = [
        {"bank": banks[r[1]]["n"], "technical_decline_rate": pct(r[3])} for r in current[:3]]
    crossed = [r for r in current if (last - 1, r[1]) in rows and (r[3] >= 1) != (rows[(last - 1, r[1])][3] >= 1)]
    out["paying_banks"]["banks_that_crossed_the_target_this_month"] = [
        {"bank": banks[r[1]]["n"], "direction": "rose above the 1% line" if r[3] >= 1 else "fell below the 1% line",
         "now": pct(r[3]), "previous_month": pct(rows[(last - 1, r[1])][3])} for r in crossed]
    out["unusual_months_this_month"] = [
        {"side": "paying" if a["side"] == "remitter" else "receiving", "bank": banks[a["b"]]["n"],
         "technical_decline_rate": pct(a["td"]), "usual_rate": pct(a["usual"])} for a in data["alerts"] if a["m"] == last]
    return out


def ungrounded(text: str, fact_sheet: dict) -> list:
    """Numbers (or quantity words) in the text that the facts do not contain. An empty list means the text passes."""
    allowed = {float(n.replace(",", "")) for n in NUMBER.findall(json.dumps(fact_sheet))}
    bad = [n for n in NUMBER.findall(text) if float(n.replace(",", "")) not in allowed]
    return bad + [w.lower() for w in NUMBER_WORDS.findall(text)]


def ask_claude(fact_sheet: dict) -> tuple[str, str]:
    """Returns (summary text, model that wrote it)."""
    import anthropic  # only needed for a real run; the tests pass their own `ask`

    response = anthropic.Anthropic().beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM,
        output_config={"effort": "low"},  # a short summary of given figures needs little reasoning
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",  # if the model declines, the API retries on a fallback model in the same call
        messages=[{"role": "user", "content": "FACTS:\n" + json.dumps(fact_sheet, indent=1)}],
    )
    if response.stop_reason != "end_turn":
        raise RuntimeError(f"no summary: stop reason {response.stop_reason} (request {response._request_id})")
    text = " ".join(b.text for b in response.content if b.type == "text").strip()
    return text, response.model


def write_insight(data: dict, ask=ask_claude, out: Path = DOCS / "insight.json") -> dict:
    """Ask for a summary, check every number against the facts, and write it only if it passes."""
    fact_sheet = facts(data)
    text, model = ask(fact_sheet)
    bad = ungrounded(text, fact_sheet)
    if bad or not text:
        raise ValueError(f"summary rejected, not written: numbers or quantity words not in the data: {bad}\n{text}")
    insight = {"month": data["meta"]["months"][-1], "text": text, "model": model, "generated": date.today().isoformat()}
    out.write_text(json.dumps(insight, indent=1, ensure_ascii=False), encoding="utf-8")
    return insight


def main() -> None:
    insight = write_insight(json.loads((DOCS / "data.json").read_text(encoding="utf-8")))
    print(f"docs/insight.json written by {insight['model']} for {month_name(insight['month'])}:\n{insight['text']}")


if __name__ == "__main__":
    main()
