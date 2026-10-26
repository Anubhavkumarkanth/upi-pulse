"""Build the static site: docs/data.json from the bank_month table, and docs/index.html from site/page.html.

docs/ is what GitHub Pages serves. site/page.html holds the page body only (the Artifact preview publishes it as is),
so this script wraps it in a full HTML document for Pages.
Usage: python pipeline/build_site.py
"""
import json
from datetime import date
from pathlib import Path

from pipeline import analysis as A
from pipeline.parse_npci import build

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def r2(x):
    return None if x != x else round(float(x), 2)  # x != x is NaN


def site_data(df) -> dict:
    months = sorted(df.month.unique())
    banks = df.sort_values("month").drop_duplicates("bank_key", keep="last")[["bank_key", "bank", "bank_type"]]
    bank_idx = {k: i for i, k in enumerate(banks.bank_key)}
    month_idx = {m: i for i, m in enumerate(months)}
    last12 = months[-12:]

    summary = A.monthly_summary(df)
    remitter = df[df.side == "remitter"]
    before = [m for m in months if m.startswith("2024")]
    drivers = A.bd_drivers(remitter, before, last12)
    bd_change = A.weighted(remitter[remitter.month.isin(last12)], "bd_pct") - A.weighted(remitter[remitter.month.isin(before)], "bd_pct")

    calculator = {}
    for side, g in df.groupby("side"):
        p = A.period_by_bank(g, last12).sort_values("volume_mn", ascending=False)
        calculator[side] = [{"b": bank_idx[r.bank_key], "share": r2(r.share * 100), "td": r2(r.td_pct), "bd": r2(r.bd_pct)}
                            for r in p.itertuples()]

    return {
        "meta": {"built": date.today().isoformat(), "months": months, "td_target": A.TD_TARGET,
                 "last12": [last12[0], last12[-1]], "drivers_before": "2024",
                 "alert_rule": {"z": A.ALERT_Z, "min_rise": A.ALERT_MIN_RISE, "min_history": A.ALERT_MIN_HISTORY},
                 "sources": {side: {s: sorted(g[g.source == s].month.unique().tolist()) for s in ("npci", "tsoi")}
                             for side, g in df.groupby("side")}},
        "banks": [{"k": r.bank_key, "n": r.bank, "t": r.bank_type} for r in banks.itertuples()],
        # rows[side] = [month index, bank index, volume (million), TD %, BD %]
        "rows": {side: [[month_idx[r.month], bank_idx[r.bank_key], r2(r.volume_mn), r2(r.td_pct), r2(r.bd_pct)]
                        for r in g.itertuples()] for side, g in df.groupby("side")},
        "summary": {side: [{"m": month_idx[r.month], "src": r.source, "banks": r.banks, "under": r.under_target,
                            "td": r2(r.td_pct), "bd": r2(r.bd_pct), "vol": r2(r.volume_mn), "top5": r2(r.top5_share)}
                           for r in g.itertuples()] for side, g in summary.groupby("side")},
        "drivers": {"change": r2(bd_change), "rows": [
            {"b": bank_idx[r.bank_key], "c": r2(r.contribution), "bd0": r2(r.bd_pct_before), "bd1": r2(r.bd_pct_after),
             "s0": r2(r.share_before * 100), "s1": r2(r.share_after * 100)} for r in drivers.itertuples()]},
        "festive": [{"side": r.side, "year": r.year, "festive": r2(r.festive_td), "other": r2(r.other_td)}
                    for r in A.festive_vs_rest(summary).itertuples()],
        "alerts": [{"side": r.side, "m": month_idx[r.month], "b": bank_idx[r.bank_key], "td": r2(r.td_pct),
                    "usual": r2(r.usual_td_pct), "z": r2(r.z), "vol": r2(r.volume_mn)} for r in A.alerts(df).itertuples()],
        "calculator": calculator,
    }


def main() -> None:
    DOCS.mkdir(exist_ok=True)
    data = site_data(build())
    (DOCS / "data.json").write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    page = (ROOT / "site" / "page.html").read_text(encoding="utf-8")
    (DOCS / "index.html").write_text('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                                     '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                                     f"</head>\n<body>\n{page}\n</body>\n</html>\n", encoding="utf-8")
    print(f"docs/data.json: {(DOCS / 'data.json').stat().st_size / 1024:.0f} KB, {len(data['alerts'])} alerts")


if __name__ == "__main__":
    main()
