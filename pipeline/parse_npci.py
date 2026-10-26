"""Parse NPCI "Top 50 Member Performance" responses (saved unchanged in data/raw/npci) into one tidy table.

Months not yet downloaded from NPCI are filled from Time Series of India's copy of the same NPCI data
(data/raw/tsoi, kept out of git), which has volume, BD % and TD % only. The `source` column marks each row.
Output: data/processed/bank_month.csv and data/processed/upi_pulse.duckdb, one row per (side, month, bank).
Usage: python pipeline/parse_npci.py
"""
import json
import re
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "npci"
TSOI = ROOT / "data" / "raw" / "tsoi"
OUT = ROOT / "data" / "processed"
TSOI_SIDES = {"UPI Remitter": "remitter", "UPI Beneficiary": "beneficiary"}
MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
NUMERIC = {
    "total_volume_in_mn": "volume_mn", "approved_percent": "approved_pct", "bd_percent": "bd_pct", "td_percent": "td_pct",
    "total_debit_reversal_count_in_mn": "debit_reversal_count_mn", "debit_reversal_success_percent": "debit_reversal_success_pct",
    "udir_auto_update_sr_percent": "udir_auto_update_sr_pct", "udir_refund_sr_percent": "udir_refund_sr_pct",
}
PUBLIC_SECTOR = {  # the 12 public sector banks, by bank_key
    "statebankofindia", "punjabnationalbank", "bankofbaroda", "canarabank", "unionbankofindia", "bankofindia",
    "indianbank", "centralbankofindia", "indianoverseasbank", "ucobank", "bankofmaharashtra", "punjabandsindbank",
}
FOREIGN = ("citi", "hsbc", "standardchartered", "dbs", "deutsche")
# Same bank under a different name, checked to never appear twice in one month. Pairs that do share a month
# (AU Small Finance Bank and its 'Erstwhile Fincare' handle; HDFC Bank and its credit-card handle) stay separate.
ALIASES = {
    "andhrapradeshgrameenavikasbankimps": "andhrapradeshgrameenavikasbank",
    "barodaupbank": "barodaupgraminbank",
    "barodaupbankerstwhilebarodauttarpradeshgraminbank": "barodaupgraminbank",
    "barodauttarpradeshgraminbank": "barodaupgraminbank",
    "dbsbank": "dbsbankindia",
    "equitasbank": "equitassmallfinancebank",
    "finopaymentsbankfip": "finopaymentsbank",
    "idfcbank": "idfcfirstbank",
    "indiapostpaymentbank": "indiapostpaymentsbank",
    "jammukashmirbank": "jammuandkashmirbank",
    "karnatakagraminbankerstwhilepragathikrishnagraminbank": "karnatakagraminbank",
    "punjabsindbank": "punjabandsindbank",
    "rbl": "rblbank",
    "saraswatbank": "saraswatcooperativebank",
    "standardchartered": "standardcharteredbank",
    "triotechsolutionsprivateppi": "triotechsolutionsprivate",
    "triotechsolutions": "triotechsolutionsprivate",  # Time Series of India's spelling
}
# Errors in NPCI's published data, fixed here so the raw files stay as downloaded: (side, month, column) -> divisor.
# Aug 2022: every bank's debit reversal success % lost its decimal point ('9123.00%' for 91.23%).
SOURCE_FIXES = {("remitter", "2022-08-01", "debit_reversal_success_pct"): 100}


def bank_key(name: str) -> str:
    """One key per bank across spellings: 'HDFC BANK LTD.' and 'HDFC Bank Ltd' both give 'hdfcbank'."""
    key = re.sub(r"[^a-z]", "", re.sub(r"\b(the|ltd|limited)\b", "", name.lower()))
    return ALIASES.get(key, key)


def display_name(name: str) -> str:
    """Clean a spelling for display: 'The South Indian Bank Limited' -> 'South Indian Bank', 'Bank Of India' -> 'Bank of India'."""
    name = re.sub(r"^\s*the\s+", "", name.strip(), flags=re.I)
    words = re.sub(r"\s+(ltd\.?|limited)\s*$", "", name, flags=re.I).split()
    return " ".join(w.lower() if i and w.lower() in ("of", "and") else w[:1].upper() + w[1:] for i, w in enumerate(words))


def bank_type(key: str) -> str:
    if "bank" not in key:  # e.g. One Mobikwik Systems, Tri O Tech Solutions
        return "non-bank member"
    if "paymentsbank" in key:
        return "payments bank"
    if "smallfinance" in key:
        return "small finance bank"
    if any(w in key for w in ("grameen", "gramin", "grameena")):
        return "regional rural bank"
    if any(w in key for w in ("cooperative", "sahakari")):
        return "co-operative bank"
    if key in PUBLIC_SECTOR:
        return "public sector bank"
    if key.startswith(FOREIGN):
        return "foreign bank"
    return "private bank"


def number(value) -> float | None:
    """'90.34%' -> 90.34, '1,291.88' -> 1291.88, None or '' -> None."""
    if value is None or str(value).strip() in ("", "-"):
        return None
    return float(str(value).replace("%", "").replace(",", "").strip())


def raw_responses():
    """Yield (side, year, month, response) from single API responses and from batch files of several months."""
    for path in sorted(RAW.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for item in doc.get("items", [{"body": doc}]):
            rows = item["body"]["data"]["results"]
            if rows:
                yield rows[0]["type_name"], int(rows[0]["year"]), rows[0]["month"], rows


def tsoi_rows() -> pd.DataFrame:
    """All UPI rows from the newest Time Series of India file, in this table's columns (other measures left empty)."""
    files = sorted(TSOI.glob("bank-performance_*.json"))
    if not files:
        return pd.DataFrame(columns=["side", "month", "bank_raw", "bank_key", "volume_mn", "bd_pct", "td_pct", "source"])
    t = pd.DataFrame(json.loads(files[-1].read_text(encoding="utf-8"))["rows"])
    t = t[t.system.isin(TSOI_SIDES)]
    df = pd.DataFrame({"side": t.system.map(TSOI_SIDES), "month": t.date, "bank_raw": t.bank.str.strip(),
                       "bank_key": t.bank.map(bank_key), "volume_mn": (t.volume_cr * 10).round(1),
                       "bd_pct": t.bd_pct, "td_pct": t.td_pct, "source": "tsoi"})
    dupes = df[df.duplicated(["side", "month", "bank_key"], keep=False)]
    if len(dupes):
        raise ValueError(f"two tsoi names share a bank key in one month:\n{dupes}")
    return df


def build() -> pd.DataFrame:
    records = {}
    for side, year, month, rows in raw_responses():
        for r in rows:
            name = r.get("upi_remitter_banks") or r.get("upi_beneficiary_banks")
            rec = {"side": side, "month": f"{year}-{MONTHS[month]:02d}-01", "npci_rank": int(r["sr_no"]), "bank_raw": name.strip(),
                   "bank_key": bank_key(name), "npci_row_id": r["id"], "npci_updated_at": r["updated_at"], "source": "npci"}
            rec.update({new: number(r.get(old)) for old, new in NUMERIC.items()})
            records[(side, rec["month"], rec["bank_key"])] = rec  # a later file for the same month replaces an earlier one
    npci = pd.DataFrame(records.values())
    # NPCI's own file wins: Time Series of India fills only the (side, month) pairs NPCI has not given us.
    tsoi = tsoi_rows()
    have = set(zip(npci.side, npci.month))
    tsoi = tsoi[[pair not in have for pair in zip(tsoi.side, tsoi.month)]]
    df = pd.concat([npci, tsoi], ignore_index=True).sort_values(["side", "month", "npci_rank", "volume_mn"],
                                                                ascending=[True, True, True, False], ignore_index=True)
    df["npci_rank"] = df.npci_rank.astype("Int64")
    for (side, month, col), divisor in SOURCE_FIXES.items():
        rows = (df.side == side) & (df.month == month)
        if df.loc[rows, col].max() > 100:  # skip if NPCI has since corrected the file
            df.loc[rows, col] = (df.loc[rows, col] / divisor).round(2)
    # NPCI's Sr. No. is its listing order and sometimes lags the month's volumes, so rank by volume separately.
    df["volume_rank"] = df.groupby(["side", "month"]).volume_mn.rank(ascending=False, method="min").astype(int)
    # Display name: the most used spelling that is not all capitals, cleaned of 'The' and 'Ltd' (the most recent wins a tie).
    # Not simply the latest: NPCI labels IDFC FIRST Bank 'IDFC Bank Ltd.' in some recent months.
    names = df.assign(name=df.bank_raw.map(display_name), caps=df.bank_raw.str.isupper())
    names = (names.groupby(["bank_key", "caps", "name"]).month.agg(["count", "max"]).reset_index()
                  .sort_values(["caps", "count", "max"], ascending=[True, False, False])
                  .drop_duplicates("bank_key").set_index("bank_key").name)
    df.insert(df.columns.get_loc("bank_key") + 1, "bank", df.bank_key.map(names))
    df.insert(df.columns.get_loc("bank") + 1, "bank_type", df.bank_key.map(bank_type))
    return df


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    df = build()
    df.to_csv(OUT / "bank_month.csv", index=False)
    with duckdb.connect(str(OUT / "upi_pulse.duckdb")) as con:
        con.execute("CREATE OR REPLACE TABLE bank_month AS SELECT * FROM df")
    cover = df.groupby("side").month.agg(["min", "max", "nunique"])
    print(f"{len(df):,} rows, {df.bank_key.nunique()} banks\n{cover}")


if __name__ == "__main__":
    main()
