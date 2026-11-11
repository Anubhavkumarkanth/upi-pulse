"""The site's data file holds every bank-month and a calculator whose bank shares add up to 100%, and the page shows
text from the data and from the AI model as plain text."""
import json
from pathlib import Path

import pytest

from pipeline.build_site import html_document, site_data
from pipeline.parse_npci import build


def test_site_data_is_complete():
    df = build()
    d = site_data(df)
    assert sum(len(v) for v in d["rows"].values()) == len(df)
    assert len(d["meta"]["months"]) == df.month.nunique()
    for side, banks in d["calculator"].items():
        assert sum(b["share"] for b in banks) == pytest.approx(100, abs=0.1), side
    assert sum(r["c"] for r in d["drivers"]["rows"]) == pytest.approx(d["drivers"]["change"], abs=0.05)


def test_a_month_without_percentages_shows_no_rate():
    # Jan 2025, receiving banks: NPCI's percentages are unusable, so the month must read as "no figure", never as 0%.
    d = site_data(build())
    jan = d["meta"]["months"].index("2025-01-01")
    month = next(r for r in d["summary"]["beneficiary"] if r["m"] == jan)
    assert month["td"] is None and month["bd"] is None and month["under"] is None and month["vol"] > 0
    assert all(td is None and bd is None for m, _, _, td, bd in d["rows"]["beneficiary"] if m == jan)


def test_published_site_is_built_from_the_current_data_and_page():
    # docs/ is built by hand with `python -m pipeline.build_site`; this fails when that step was forgotten.
    root = Path(__file__).resolve().parents[1]
    published = json.loads((root / "docs" / "data.json").read_text(encoding="utf-8"))
    fresh = json.loads(json.dumps(site_data(build())))
    for d in (published, fresh):
        del d["meta"]["built"]  # the build date
    assert published == fresh, "docs/data.json is stale: run python -m pipeline.build_site"
    page = (root / "site" / "page.html").read_text(encoding="utf-8")
    assert (root / "docs" / "index.html").read_text(encoding="utf-8") == html_document(page), "docs/index.html is stale"


def test_title_and_description_are_in_the_head():
    # Link previews read <head> only, so the page's title and description must be there, with matching og: tags.
    page = (Path(__file__).resolve().parents[1] / "site" / "page.html").read_text(encoding="utf-8")
    head, body = html_document(page).split("</head>")
    assert "<title>UPI Pulse</title>" in head and '<meta name="description"' in head
    assert '<meta property="og:title" content="UPI Pulse">' in head and '<meta property="og:description" content="How reliably' in head
    assert "<title>" not in body and body.count("<style>") == 1


def test_page_never_turns_text_into_html():
    # The AI summary, the question box's answers and the bank names are shown with textContent, so markup or a script
    # hidden in any of them is shown as text, never run.
    page = (Path(__file__).resolve().parents[1] / "site" / "page.html").read_text(encoding="utf-8")
    for risky in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert risky not in page, risky
