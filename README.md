# UPI Pulse

**Live site: https://anubhavkumarkanth.github.io/upi-pulse/**

How often UPI payments fail at India's 50 busiest banks, month by month, from January 2022 to September 2026.
The data is NPCI's own monthly "Top 50 Member Performance" tables.

When a UPI payment fails, there are two kinds of failure:

- **Technical decline:** the bank's or the network's systems failed. The customer did nothing wrong.
- **Business decline:** a normal "no", like a wrong PIN, a low balance or a daily limit.

RBI has reportedly asked NPCI to keep technical declines under 1% at each bank. This site tracks who meets that line.

## What the data shows

These figures are for paying banks (the customer's bank that sends the money):

- **Technical declines fell every year:** about 1.45% of payments in 2022, then 1.01%, 0.59%, 0.40%, and 0.26% so far in 2026. In September 2026 that is about 1 payment in 385.
- **Most banks now meet the 1% line:** 45 of the top 50 in September 2026, against 24 in January 2022.
- **Business declines doubled:** from 5.2% of payments in 2023 to 10.1% so far in 2026. The rise is gradual, not a one-off jump.
- **Who drove that rise:** business declines rose 3.39 points between 2024 and the last 12 months. SBI accounts for 0.70 of those points. Airtel Payments Bank's own rate went from 10% to 23%.
- **Festive months are not worse:** October and November had fewer technical declines than the rest of the year, in every year.

## What's on the site

- **Latest month:** the headline numbers.
- **Trends:** technical and business declines over time, with the 1% line.
- **Who drove the rise:** each bank's share of the rise in business declines.
- **Bank scoreboard:** every top-50 bank, sortable, with a 12-month mini-chart.
- **Compare banks:** up to three banks on one chart.
- **Unusual months:** banks whose technical declines jumped far above their own usual level.
- **Shop calculator:** you enter how many UPI payments you take, your customers' banks and your own bank. It estimates how many payments fail each month and what they are worth.

Every chart has a table view. The site works on phones and in dark mode.

## How it works

```
NPCI API responses ──► pipeline/parse_npci.py ──► one table: bank × month (DuckDB + CSV)
                                │
                     tests/ (data checks run first)
                                │
                       pipeline/analysis.py ──► pipeline/build_site.py ──► docs/ (GitHub Pages)
```

- **Parsing (`pipeline/parse_npci.py`):**
  - **One name per bank:** NPCI names the same bank differently over time ("Baroda UP Gramin Bank", "Baroda U.P. Bank"). Even after ignoring capitals and "Ltd", its files use 78 names for 62 banks. Two pairs that look alike stay separate, because both names appear in the same month.
  - **Bank types:** each bank is labelled public sector, private, payments bank, small finance bank, regional rural bank, co-operative, foreign, or non-bank.
- **Data checks (`tests/test_data_quality.py`):** these run before the site is built, so a bad or changed NPCI file never reaches it.
  - Percentages stay between 0 and 100.
  - Approved, business and technical add up to 100%.
  - Each month has one row per bank, and each NPCI month has exactly 50 banks.
  - No month is missing.
  - Spot checks match NPCI's published values.
  - The checks found a real error in NPCI's data: in August 2022, NPCI published every bank's debit reversal success rate without the decimal point ("9123.00%" for 91.23%). The pipeline corrects that month and keeps the raw file unchanged.
- **Unusual-month alerts (`pipeline/analysis.py`):**
  - **The rule:** a month is flagged when a bank's technical decline rate is at least 1 point above its own usual level (the median of its previous 12 months). It must also be at least 5 robust standard deviations above that level, so normal ups and downs don't count.
  - **How often:** about 3% of bank-months are flagged.
  - **Checked against noise:** on simulated stable banks, the false-alarm rate is 1.15%.
  - **Checked against history:** the tests confirm that two known spikes in NPCI's data are caught.
  - **No AI involved:** this is plain statistics.
- **Rates across banks** are weighted by each bank's number of payments, so they show what a typical payer experiences.

## Data sources

**All figures come from the National Payments Corporation of India (NPCI):** UPI Ecosystem Statistics, Top 50 Member Performance ([npci.org.in](https://www.npci.org.in/product/ecosystem-statistics/upi)). The data belongs to NPCI.

- **Paying banks, Jan 2022 to Oct 2024 and Sep 2026:** NPCI's own API responses, saved unchanged in `data/raw/npci/`.
- **Paying banks Nov 2024 to Aug 2026, and all receiving-bank months:** these come from [Time Series of India](https://timeseriesofindia.com)'s copy of the same NPCI data, used while NPCI's site was down in October 2026.
  - **How it was checked:** wherever both copies exist, every bank's technical and business decline rates match exactly.
  - **What it lacks:** the copy has volumes and decline rates only.
  - **Where it lives:** it is not stored in this repository.

The `source` column of each row says which copy it came from. See [data/SOURCES.md](data/SOURCES.md) for details.

## Run it yourself

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # on macOS/Linux: .venv/bin/pip
python pipeline/parse_npci.py                   # builds data/processed/
pytest -q                                       # data, analysis and site checks
python -m pipeline.build_site                   # rebuilds docs/
```

Without the Time Series of India file, the pipeline builds only NPCI's own months, and the checks that need that file skip. On GitHub Actions, the tests run on every push.

## Limits

- **Monthly totals only:** these are monthly totals per bank, not single payments. The shop calculator is an estimate from averages.
- **The 1% line:** it comes from press reports of RBI's request to NPCI. It is not a published rule.
- **Missing columns:** for the months filled from the copy, approval rates, debit reversals and UDIR figures are not available yet. They will come from NPCI's own files.

## Planned next

- **AI monthly summary:** a short written summary each month, with an automatic check that every number in it matches the data.
- **Plain-English questions:** ask the data in your own words, with a test set of known answers.
- **UPI failure tests for Orderdesk:** UPI failure scenarios for my [Orderdesk](https://github.com/Anubhavkumarkanth/orderdesk-qa-suite) QA project.
