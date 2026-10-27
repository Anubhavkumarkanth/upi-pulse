"""The site's data file holds every bank-month and a calculator whose bank shares add up to 100%, and the page shows
text from the data and from the AI model as plain text."""
from pathlib import Path

import pytest

from pipeline.build_site import site_data
from pipeline.parse_npci import build


def test_site_data_is_complete():
    df = build()
    d = site_data(df)
    assert sum(len(v) for v in d["rows"].values()) == len(df)
    assert len(d["meta"]["months"]) == df.month.nunique()
    for side, banks in d["calculator"].items():
        assert sum(b["share"] for b in banks) == pytest.approx(100, abs=0.1), side
    assert sum(r["c"] for r in d["drivers"]["rows"]) == pytest.approx(d["drivers"]["change"], abs=0.05)


def test_page_never_turns_text_into_html():
    # The AI summary, the question box's answers and the bank names are shown with textContent, so markup or a script
    # hidden in any of them is shown as text, never run.
    page = (Path(__file__).resolve().parents[1] / "site" / "page.html").read_text(encoding="utf-8")
    for risky in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert risky not in page, risky
