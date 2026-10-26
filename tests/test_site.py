"""The site's data file holds every bank-month and a calculator whose bank shares add up to 100%."""
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
