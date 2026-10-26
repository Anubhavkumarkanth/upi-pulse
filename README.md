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
- **This month in plain English:** a short summary written by an AI model, with every number checked against the data before it is published.
- **Ask the data:** type a question in your own words. An AI model turns it into a database query, code runs it, and the answer comes straight from the data, with the query shown.
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
- **AI monthly summary (`pipeline/insights.py`):**
  - **Facts first:** code works out the latest month's figures (this month against last month and a year ago, the highest failure rates, banks that crossed the 1% line, unusual months), already formatted as they should be written.
  - **The model writes, code checks:** Google Gemini's free tier writes 3 or 4 sentences from those facts. Free models are often busy, so it tries `gemini-3.8-flash`, then `gemini-3.6-flash`, then `gemini-3.1-flash-lite`, and the site names the model that wrote the summary. Claude works too, with `--provider claude`.
  - **Number check:** every number in the summary must appear among the figures. Quantity words such as "doubled" or "half", links, lists and text over 120 words are also refused. A refused summary is never written, and the site hides the panel when there is no summary for the latest month.
  - **Bad input:** bank names come from outside data, so they never count as allowed numbers. A test hides an instruction inside a bank name and checks that a model which obeys it cannot get anything published.
  - **On every push:** the tests re-check the published summary against the data.
- **Ask the data (`pipeline/ask.py`, `api/main.py`):**
  - **The model writes only the query:** Gemini's free tier (the same models as the summary) turns the question into one SQL query. Claude works too, with `ASK_PROVIDER=claude`. Every number and name in the answer comes from running that query, never from the model.
  - **Code checks the query:** DuckDB parses it, and it must be a single SELECT that reads only the `bank_month` table. File readers, system tables, lists of typed-in values and second statements are refused.
  - **The database is locked anyway:** it lives in memory and holds only the rows the site shows. It cannot read files or reach the network, its settings cannot be changed back, and a query returns at most 200 rows and is stopped after 5 seconds.
  - **The answer is checked too:** every piece of text in it must be a bank name, bank type or month from the data, so the model cannot slip its own words into an answer.
  - **Questions are untrusted:** anyone can type anything. The tests hand the code a model that obeys "ignore your rules" and check that nothing it writes gets through.
  - **Limits:** 8 questions a minute and 50 a day for each visitor, and 300 a day for everyone, so the free model quota (or a paid key's bill) stays small.
  - **Accuracy:** 30 test questions with answers worked out from the data (`pipeline/ask_questions.json`), checked again by the tests on every push. `python -m pipeline.ask_eval` puts them to the model. An answer counts as right when it has the same rows as the known answer, with the same names, months and numbers (to within 0.1%). A run where the model gives no reply to some questions is not published, because it would measure Gemini's free quota, not accuracy. **Latest score:** not measured yet. In the first run, on 27 October 2026, the free models answered 15 of the 30 questions and got all 15 right; the other 15 got no reply because the free quota had run out.
  - **Where it runs:** a small FastAPI service on Render's free plan (`render.yaml`) holds the API key. The free plan sleeps after 15 quiet minutes, so the first question can take up to a minute. The page says so, and nothing else on it depends on the service.

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
python -m pipeline.insights                     # AI summary; asks for a free Gemini key if none is set
python -m pipeline.ask "Which bank had the most technical declines in Oct 2025?"
python -m pipeline.ask_eval                     # scores the model on the 30 test questions
uvicorn api.main:app --port 8000                # the question service; needs GEMINI_API_KEY in the environment
```

Without the Time Series of India file, the pipeline builds only NPCI's own months, and the checks that need that file skip. On GitHub Actions, the tests run on every push.

## Limits

- **Monthly totals only:** these are monthly totals per bank, not single payments. The shop calculator is an estimate from averages.
- **The 1% line:** it comes from press reports of RBI's request to NPCI. It is not a published rule.
- **Missing columns:** for the months filled from the copy, approval rates, debit reversals and UDIR figures are not available yet. They will come from NPCI's own files.

- **AI summary:** it restates the month's figures and does not explain causes. On Gemini's free tier, what is sent may be used to improve Google's products. Only NPCI's public figures are sent.
- **Ask the data:** the model can misread a question, and the score above shows how often. The query is always shown, so an answer can be checked. Only the table's layout, the bank names and the question are sent to the model, and on Gemini's free tier they may be used to improve Google's products.

## Planned next

- **UPI failure tests for Orderdesk:** UPI failure scenarios for my [Orderdesk](https://github.com/Anubhavkumarkanth/orderdesk-qa-suite) QA project.
