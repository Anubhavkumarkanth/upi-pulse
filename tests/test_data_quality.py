"""Checks on the tidy bank_month table, so a bad or changed NPCI file never reaches the site."""
import pandas as pd
import pytest

from pipeline.parse_npci import ALIASES, PUBLIC_SECTOR, TSOI, bank_key, bank_type, build, display_name, number, tsoi_rows

# The Time Series of India copy stays on the author's machine (data/raw/tsoi is not in git), so checks of it skip elsewhere.
needs_tsoi = pytest.mark.skipif(not any(TSOI.glob("bank-performance_*.json")),
                                reason="Time Series of India copy not present (kept local, not in git)")
PCT =["approved_pct", "bd_pct", "td_pct", "debit_reversal_success_pct", "udir_auto_update_sr_pct", "udir_refund_sr_pct", "deemed_approved_pct"]


@pytest.fixture(scope="module")
def df():
    return build()


def test_percentages_between_0_and_100(df):
    for col in PCT:
        values = df[col].dropna()
        assert values.between(0, 100).all(), f"{col} out of range:\n{df.loc[values[~values.between(0, 100)].index]}"


def test_approved_bd_td_add_up_to_100(df):
    npci = df[df.source == "npci"]  # the Time Series of India copy has no approved %
    # Known exceptions: beneficiary rows NPCI publishes as not adding up to 100 with or without deemed approvals (97.56 to 100.48).
    odd = {("2022-12-01", "citibank"), ("2022-12-01", "karnatakavikasgrameenabank"), ("2023-03-01", "yesbank"),
           ("2023-04-01", "yesbank"), ("2023-04-01", "rblbank"), ("2024-11-01", "canarabank")}
    npci = npci[~((npci.side == "beneficiary") & pd.Series(list(zip(npci.month, npci.bank_key)), index=npci.index).isin(odd))]
    total = npci.approved_pct + npci.bd_pct + npci.td_pct
    off = total.notna() & ((total - 100).abs() > 0.05)
    assert not off.any(), npci.loc[off, ["month", "bank", "approved_pct", "bd_pct", "td_pct"]]


def test_one_row_per_bank_per_month(df):
    assert not df.duplicated(["side", "month", "bank_key"]).any()


def test_one_source_per_month(df):
    assert (df.groupby(["side", "month"]).source.nunique() == 1).all()


def test_fifty_banks_ranked_1_to_50_each_npci_month(df):
    # Also catches two spellings merged by ALIASES in the same month, since one would overwrite the other.
    for (side, month), g in df[df.source == "npci"].groupby(["side", "month"]):
        if (side, month) == ("remitter", "2025-09-01"):  # NPCI's own file lists Sr. No. 30 twice and no 39
            assert len(g) == 50 and sorted(g.npci_rank) == sorted([*range(1, 39), 30, *range(40, 51)])
            continue
        assert sorted(g.npci_rank) == list(range(1, 51)), f"{side} {month}: {len(g)} rows"


def test_49_or_50_banks_each_filled_month(df):
    # Time Series of India sometimes merges two handles of one bank into a single row.
    for (side, month), g in df[df.source == "tsoi"].groupby(["side", "month"]):
        assert 49 <= len(g) <= 50, f"{side} {month}: {len(g)} rows"


def test_volumes_positive(df):
    assert df.volume_mn.notna().all() and (df.volume_mn > 0).all()


def test_volume_rank_follows_volume(df):
    for _, g in df.groupby(["side", "month"]):
        assert g.sort_values("volume_rank").volume_mn.is_monotonic_decreasing


def test_display_names_unique_across_banks(df):
    names = df.drop_duplicates("bank_key").bank
    assert not names.duplicated().any(), f"same name, different keys: {sorted(names[names.duplicated()])}"


def test_all_public_sector_banks_found(df):
    assert PUBLIC_SECTOR <= set(df.bank_key), f"missing: {PUBLIC_SECTOR - set(df.bank_key)}"


def test_alias_targets_are_real_banks(df):
    assert set(ALIASES.values()) <= set(df.bank_key)


@pytest.mark.parametrize("side, month, bank, volume, td", [
    ("remitter", "2026-09-01", "statebankofindia", 6734.080234, 0.38),
    ("remitter", "2022-01-01", "statebankofindia", 1291.88, 1.21),
])
def test_spot_check_against_npci_source(df, side, month, bank, volume, td):
    row = df[(df.side == side) & (df.month == month) & (df.bank_key == bank)].iloc[0]
    assert row.volume_mn == pytest.approx(volume) and row.td_pct == pytest.approx(td)


def test_aug_2022_debit_reversal_fix(df):
    # NPCI published '9123.00%'; SOURCE_FIXES divides that month by 100.
    sbi = df[(df.side == "remitter") & (df.month == "2022-08-01") & (df.bank_key == "statebankofindia")].iloc[0]
    assert sbi.debit_reversal_success_pct == pytest.approx(91.23)


@needs_tsoi
def test_tsoi_copy_matches_npci():
    # Two copies of the same NPCI data must agree wherever both have a bank-month.
    npci = build().query("source == 'npci'")
    both = npci.merge(tsoi_rows(), on=["side", "month", "bank_key"], suffixes=("", "_tsoi"))
    assert len(both) >= 0.99 * len(npci)
    off = both[(both.bd_pct.round(2) != both.bd_pct_tsoi) | (both.td_pct.round(2) != both.td_pct_tsoi)
               | ((both.volume_mn - both.volume_mn_tsoi).abs() > 0.1)]
    # Known differences: Time Series of India merges AU Small Finance Bank's two handles in Jul 2024, and has
    # Yes Bank's Oct 2022 beneficiary volume as 1227.7 million where NPCI's file says 1219.77.
    assert set(zip(off.side, off.month, off.bank_key)) == {("remitter", "2024-07-01", "ausmallfinancebank"),
                                                           ("beneficiary", "2022-10-01", "yesbank")}, off


@needs_tsoi
@pytest.mark.parametrize("bank, volume, bd, td", [
    ("ausmallfinancebank", 44.585, 0.62, 0.11),
    ("airtelpaymentsbank", 590.913, 3.9, 0.04),
])
def test_beneficiary_spot_check_against_dataful_preview(df, bank, volume, bd, td):
    # Values from Dataful's free preview of NPCI's Sep 2026 beneficiary table, a third copy.
    row = df[(df.side == "beneficiary") & (df.month == "2026-09-01") & (df.bank_key == bank)].iloc[0]
    assert row.volume_mn == pytest.approx(volume, abs=0.06) and row.bd_pct == pytest.approx(bd) and row.td_pct == pytest.approx(td)


@needs_tsoi
def test_no_missing_months(df):
    for side in ("remitter", "beneficiary"):
        months = pd.to_datetime(df[df.side == side].month)
        assert len(months), f"no {side} data"
        expected = pd.date_range(months.min(), months.max(), freq="MS")
        assert set(expected) <= set(months), f"{side} missing {sorted(set(expected) - set(months))[:5]}..."


@pytest.mark.parametrize("raw, key", [
    ("HDFC BANK LTD.", "hdfcbank"),
    ("The Jammu & Kashmir Bank Limited", "jammuandkashmirbank"),
    ("Punjab & Sind Bank", "punjabandsindbank"),
    ("IDFC Bank Ltd.", "idfcfirstbank"),
    ("AU Small Finance Bank (Erstwhile Fincare)", "ausmallfinancebankerstwhilefincare"),  # shares months with AU, kept apart
])
def test_bank_key(raw, key):
    assert bank_key(raw) == key


@pytest.mark.parametrize("raw, name", [
    ("The South Indian Bank Limited", "South Indian Bank"),
    ("Bank Of India", "Bank of India"),
    ("Telangana Grameena bank", "Telangana Grameena Bank"),
    ("Punjab And Sind Bank", "Punjab and Sind Bank"),
])
def test_display_name(raw, name):
    assert display_name(raw) == name


@pytest.mark.parametrize("key, kind", [
    ("statebankofindia", "public sector bank"), ("hdfcbank", "private bank"), ("airtelpaymentsbank", "payments bank"),
    ("ausmallfinancebank", "small finance bank"), ("barodaupgraminbank", "regional rural bank"),
    ("saraswatcooperativebank", "co-operative bank"), ("citibank", "foreign bank"), ("onemobikwiksystems", "non-bank member"),
])
def test_bank_type(key, kind):
    assert bank_type(key) == kind


@pytest.mark.parametrize("raw, value", [("90.34%", 90.34), ("1,291.88", 1291.88), (None, None), ("-", None), ("", None)])
def test_number(raw, value):
    assert number(raw) == value
