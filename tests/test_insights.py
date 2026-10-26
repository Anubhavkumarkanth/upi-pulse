"""Checks on the AI monthly summary: the facts it is given, and the check that rejects any number not in them."""
import json
from pathlib import Path

import pytest

from pipeline.insights import facts, ungrounded, write_insight

DOCS = Path(__file__).resolve().parents[1] / "docs"


@pytest.fixture(scope="module")
def data():
    return json.loads((DOCS / "data.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def sheet(data):
    return facts(data)


def test_facts_match_the_site_figures(data, sheet):
    last = len(data["meta"]["months"]) - 1
    now = next(r for r in data["summary"]["remitter"] if r["m"] == last)
    assert sheet["paying_banks"]["technical_decline_rate"] == f"{now['td']:.2f}%"
    assert sheet["paying_banks"]["banks_under_target"] == f"{now['under']} of {now['banks']}"


def test_grounded_text_passes(sheet):
    p = sheet["paying_banks"]
    text = (f"In {sheet['month']}, {p['technical_decline_rate']} of payments at paying banks failed for a technical "
            f"reason, about {p['one_in_payments_fails_technically']}, against {p['year_ago_technical_decline_rate']} "
            f"in {sheet['year_ago_month']}. {p['banks_under_target']} banks stayed under the {sheet['target']} line, "
            f"across {p['payments']} payments.")
    assert ungrounded(text, sheet) == []


@pytest.mark.parametrize("text, flagged", [
    ("Technical declines fell to 0.19% this month.", ["0.19"]),
    ("Business declines reached 12.4% of payments.", ["12.4"]),
    ("About 27,000 million payments went through.", ["27,000"]),
    ("Business declines have nearly doubled since last year.", ["doubled"]),
    ("Three banks crossed the line.", ["three"]),
])
def test_invented_numbers_are_rejected(sheet, text, flagged):
    assert ungrounded(text, sheet) == flagged


def test_summary_written_only_when_it_passes(data, sheet, tmp_path):
    out = tmp_path / "insight.json"
    good = f"In {sheet['month']}, {sheet['paying_banks']['technical_decline_rate']} of payments failed technically."
    insight = write_insight(data, ask=lambda f: (good, "stand-in"), out=out)
    assert json.loads(out.read_text(encoding="utf-8"))["text"] == good and insight["model"] == "stand-in"

    out.unlink()
    with pytest.raises(ValueError, match="rejected"):
        write_insight(data, ask=lambda f: ("Failures fell to 0.01%.", "stand-in"), out=out)
    assert not out.exists()


@pytest.mark.skipif(not (DOCS / "insight.json").exists(), reason="no published summary yet")
def test_published_summary_is_current_and_grounded(data):
    # Guards the site: the summary on the page is for the latest month and every number in it is in the data.
    insight = json.loads((DOCS / "insight.json").read_text(encoding="utf-8"))
    assert insight["month"] == data["meta"]["months"][-1]
    assert ungrounded(insight["text"], facts(data)) == []
