"""Checks on the analysis: weighted rates, the business-decline breakdown and the unusual-month alerts."""
import numpy as np
import pandas as pd
import pytest

from pipeline import analysis as A
from pipeline.parse_npci import build


@pytest.fixture(scope="module")
def df():
    return build()


def frame(rows):
    cols = ["side", "month", "bank_key", "td_pct", "volume_mn"]
    return pd.DataFrame(rows, columns=cols).assign(bank=lambda d: d.bank_key, bank_type="private bank", bd_pct=5.0,
                                                   source="npci")


def test_monthly_summary_weights_by_volume():
    rows = [("remitter", "2026-01-01", f"b{i}", 0.5, 10.0) for i in range(5)] + [("remitter", "2026-01-01", "big", 2.0, 50.0)]
    s = A.monthly_summary(frame(rows)).iloc[0]
    assert s.td_pct == pytest.approx((5 * 0.5 * 10 + 2.0 * 50) / 100)
    assert s.under_target == 5 and s.volume_mn == 100
    assert s.top5_share == pytest.approx(90.0)  # the big bank plus four of the 10s


def test_bd_drivers_parts_add_up_to_total_change(df):
    r = df[df.side == "remitter"]
    months = sorted(r.month.unique())
    before, after = [m for m in months if m.startswith("2024")], months[-12:]
    total = A.weighted(r[r.month.isin(after)], "bd_pct") - A.weighted(r[r.month.isin(before)], "bd_pct")
    assert A.bd_drivers(r, before, after).contribution.sum() == pytest.approx(total)


def test_robust_z():
    history = pd.Series([0.2, 0.3, 0.2, 0.25, 0.3, 0.2])
    assert A.robust_z(history, 3.0) > 10
    assert A.robust_z(pd.Series([0.4] * 8), 0.45) == pytest.approx(0.5)  # spread floored at 0.1, so no blow-up


def series(values, side="remitter", key="testbank"):
    months = pd.date_range("2024-01-01", periods=len(values), freq="MS").strftime("%Y-%m-%d")
    return frame([(side, m, key, v, 100.0) for m, v in zip(months, values)])


def test_alert_flags_the_spike_month_only():
    values = [0.3, 0.35, 0.3, 0.4, 0.3, 0.35, 0.3, 0.4, 3.2, 0.35, 0.3, 0.3]
    found = A.alerts(series(values))
    assert found.month.tolist() == ["2024-09-01"]


def test_alert_needs_six_months_of_history():
    assert A.alerts(series([0.3, 0.3, 0.3, 5.0, 0.3])).empty


def test_no_alert_for_small_rise_even_if_unusual():
    # 0.05 -> 0.8 is far outside a flat history but stays under the 1-point minimum rise
    assert A.alerts(series([0.05] * 8 + [0.8])).empty


def test_false_alarm_rate_on_stable_banks():
    # 500 stable banks over 3 years, swinging like a typical real bank (robust sd about 0.37 points) with
    # heavy-tailed noise. None of them really changes, so every alert here is a false alarm. Measured: 1.15%,
    # against 2.9% of real bank-months alerting.
    rng = np.random.default_rng(7)
    frames = [series(np.clip(0.8 + 0.37 * rng.standard_t(3, 36), 0, None), key=f"b{i}") for i in range(500)]
    rate = len(A.alerts(pd.concat(frames))) / (500 * 30)  # 30 judged months each (the first 6 build history)
    assert rate < 0.02, f"false-alarm rate {rate:.2%}"


@pytest.mark.parametrize("month, bank", [
    ("2023-04-01", "punjabandsindbank"),  # NPCI: TD 14.97% against a usual 0.88%
    ("2022-07-01", "centralbankofindia"),  # NPCI: TD 11.73% against a usual 2.46%
])
def test_known_spikes_from_npci_data_are_flagged(df, month, bank):
    found = A.alerts(df[(df.side == "remitter") & (df.bank_key == bank)])
    assert month in set(found.month)
