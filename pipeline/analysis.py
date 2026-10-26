"""Analysis on the bank_month table: monthly summary, what drove the change in business declines, and unusual-month alerts.

All rates are volume-weighted across banks, so a bank with more payments counts for more (what a typical payer sees).
"""
import pandas as pd

TD_TARGET = 1.0  # RBI's reported ask to NPCI: technical declines under 1% (press reports, not a published rule)
# Bank TD rates are spiky, so an alert needs both: far outside the bank's normal swings (robust z-score, in robust
# standard deviations above its own past year) and a material rise, at least 1 point, enough to cross the target.
# Chosen on 26 Oct 2026 data: about 3% of bank-months alert (3.5 and 0.5 points flagged 5%, too many to be unusual).
ALERT_Z = 5.0
ALERT_MIN_RISE = 1.0
ALERT_MIN_HISTORY = 6  # months of the bank's own history needed in the past 12 before judging a month


def weighted(df: pd.DataFrame, col: str) -> float:
    return (df[col] * df.volume_mn).sum() / df.volume_mn.sum()


def monthly_summary(df: pd.DataFrame) -> pd.DataFrame:
    """One row per side and month: weighted TD and BD, banks under the 1% TD target, volume and the top 5 banks' share."""
    rows = []
    for (side, month), g in df.groupby(["side", "month"]):
        rows.append({"side": side, "month": month, "source": g.source.iloc[0], "banks": len(g),
                     "under_target": int((g.td_pct < TD_TARGET).sum()), "td_pct": weighted(g, "td_pct"),
                     "bd_pct": weighted(g, "bd_pct"), "volume_mn": g.volume_mn.sum(),
                     "top5_share": g.nlargest(5, "volume_mn").volume_mn.sum() / g.volume_mn.sum() * 100})
    return pd.DataFrame(rows)


def period_by_bank(df: pd.DataFrame, months) -> pd.DataFrame:
    """Per bank over a set of months: total volume, share of all volume, and volume-weighted TD and BD."""
    g = df[df.month.isin(months)].assign(td_x=lambda d: d.td_pct * d.volume_mn, bd_x=lambda d: d.bd_pct * d.volume_mn)
    g = g.groupby(["bank_key", "bank", "bank_type"], as_index=False)[["volume_mn", "td_x", "bd_x"]].sum()
    return g.assign(share=g.volume_mn / g.volume_mn.sum(), td_pct=g.td_x / g.volume_mn,
                    bd_pct=g.bd_x / g.volume_mn).drop(columns=["td_x", "bd_x"])


def bd_drivers(df: pd.DataFrame, before, after) -> pd.DataFrame:
    """Each bank's part in the change of the weighted BD rate between two periods; the parts add up to the total change.

    A bank's part is (its share x its BD) after minus the same before, so it captures both a bank declining more
    and a high-decline bank growing its share. Banks in only one period count with 0 in the other.
    """
    b, a = period_by_bank(df, before), period_by_bank(df, after)
    m = b.merge(a, on=["bank_key"], how="outer", suffixes=("_before", "_after"))
    m["bank"] = m.bank_after.fillna(m.bank_before)
    m["bank_type"] = m.bank_type_after.fillna(m.bank_type_before)
    for p in ("before", "after"):
        m[f"part_{p}"] = (m[f"share_{p}"] * m[f"bd_pct_{p}"]).fillna(0)
    m["contribution"] = m.part_after - m.part_before
    cols = ["bank_key", "bank", "bank_type", "share_before", "share_after", "bd_pct_before", "bd_pct_after", "contribution"]
    return m[cols].sort_values("contribution", ascending=False, ignore_index=True)


def festive_vs_rest(summary: pd.DataFrame) -> pd.DataFrame:
    """Weighted TD in October and November (Diwali season) against the other months of the same year, per side."""
    s = summary.assign(year=summary.month.str[:4], festive=summary.month.str[5:7].isin(["10", "11"]))
    s = s[s.groupby(["side", "year"]).festive.transform("any")]  # only years that have festive months
    out = s.groupby(["side", "year", "festive"]).td_pct.mean().unstack()
    return out.rename(columns={True: "festive_td", False: "other_td"}).reset_index()


def robust_z(history: pd.Series, value: float) -> float:
    """How far value sits above the history's median, in robust standard deviations (1.4826 x MAD).

    The spread is floored at 0.1 percentage points, so a bank whose rate never moves cannot alert on a tiny change.
    """
    median = history.median()
    spread = max(1.4826 * (history - median).abs().median(), 0.1)
    return (value - median) / spread


def alerts(df: pd.DataFrame) -> pd.DataFrame:
    """Bank-months whose TD jumped well above that bank's own previous 12 months (no LLM, just statistics)."""
    found = []
    for (side, key), g in df.groupby(["side", "bank_key"]):
        g = g.assign(when=pd.to_datetime(g.month)).sort_values("when")
        for _, row in g.iterrows():
            past = g[(g.when < row.when) & (g.when >= row.when - pd.DateOffset(months=12))].td_pct
            if len(past) < ALERT_MIN_HISTORY:
                continue
            z = robust_z(past, row.td_pct)
            if z >= ALERT_Z and row.td_pct - past.median() >= ALERT_MIN_RISE:
                found.append({"side": side, "month": row.month, "bank_key": key, "bank": row.bank, "bank_type": row.bank_type,
                              "td_pct": row.td_pct, "usual_td_pct": past.median(), "z": z, "volume_mn": row.volume_mn})
    cols = ["side", "month", "bank_key", "bank", "bank_type", "td_pct", "usual_td_pct", "z", "volume_mn"]
    return pd.DataFrame(found, columns=cols).sort_values(["month", "z"], ascending=[False, False], ignore_index=True)
