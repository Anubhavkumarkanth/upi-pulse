# UPI Pulse

Live site: **https://anubhavkumarkanth.github.io/upi-pulse/**

How often UPI payments fail at India's 50 busiest banks, month by month, from January 2022 to September 2026.
The data is NPCI's own monthly "Top 50 Member Performance" tables.

A failed UPI payment is one of two kinds. A technical decline means the bank's or the network's systems failed, and the
customer did nothing wrong. A business decline is a normal "no", like a wrong PIN, a low balance or a daily limit.

RBI has reportedly asked NPCI to keep technical declines under 1% at each bank. This site tracks who meets that line.

## What the data shows

For paying banks (the customer's bank, which sends the money):

- Technical declines fell every year: about 1.45% of payments in 2022, then 1.01%, 0.59%, 0.40%, and 0.26% so far in 2026. In September 2026 that is about 1 payment in 385.
- 45 of the top 50 banks were under the 1% line in September 2026, against 24 in January 2022.
- Business declines doubled, from 5.2% of payments in 2023 to 10.1% so far in 2026, and the rise was gradual.
- Between 2024 and the last 12 months, business declines rose 3.39 points. SBI accounts for 0.70 of those points, and Airtel Payments Bank's own rate went from 10% to 23%.
- October and November, the festive months, had fewer technical declines than the rest of the year, in every year.

## What's on the site

- The latest month's headline numbers.
- A short summary of the month, written by an AI model. Code checks every number in it against the data before it is published.
- A question box. You type a question in your own words, an AI model turns it into a database query, and code runs the query and shows the answer next to it.
- Trend charts of technical and business declines, with the 1% line.
- Each bank's share of the rise in business declines.
- A sortable scoreboard of every top-50 bank, with a 12-month mini-chart.
- A chart that compares up to three banks.
- Unusual months: banks whose technical declines jumped far above their own usual level.
- A shop calculator. You enter how many UPI payments you take, your customers' banks and your own bank, and it estimates how many payments fail each month and what they are worth.

Every chart has a table view, and the site works on phones and in dark mode.

## How it works

```
NPCI API responses ──► pipeline/parse_npci.py ──► one table: bank × month (DuckDB + CSV)
                                │
                     tests/ (data checks run first)
                                │
                       pipeline/analysis.py ──► pipeline/build_site.py ──► docs/ (GitHub Pages)
```

### Parsing (`pipeline/parse_npci.py`)

NPCI names the same bank differently over time ("Baroda UP Gramin Bank", "Baroda U.P. Bank"). Even after ignoring
capitals and "Ltd", its files use 78 names for 62 banks, and the parser gives each bank one name. Two pairs that look
alike stay separate, because both names appear in the same month. Each bank is labelled public sector, private,
payments bank, small finance bank, regional rural bank, co-operative, foreign, or non-bank.

### Data checks (`tests/test_data_quality.py`)

These run before the site is built, so a bad or changed NPCI file never reaches it:

- Percentages stay between 0 and 100.
- Approved, business and technical add up to 100%.
- Each month has one row per bank, and each NPCI month has exactly 50 banks.
- No month is missing.
- Spot checks match NPCI's published values.

The checks found a real error in NPCI's data. In August 2022, NPCI published every bank's debit reversal success rate
without the decimal point ("9123.00%" for 91.23%). The pipeline corrects that month and keeps the raw file unchanged.

### Unusual-month alerts (`pipeline/analysis.py`)

A month is flagged when a bank's technical decline rate is at least 1 point above its own usual level (the median of its
previous 12 months) and at least 5 robust standard deviations above it, so normal ups and downs don't count. About 3% of
bank-months are flagged. On simulated stable banks the false-alarm rate is 1.15%, and the tests confirm that two known
spikes in NPCI's data are caught. This part is plain statistics, with no AI model.

Rates across banks are weighted by each bank's number of payments, so they show what a typical payer experiences.

### AI monthly summary (`pipeline/insights.py`)

Code first works out the latest month's figures: this month against last month and a year ago, the highest failure
rates, banks that crossed the 1% line, and unusual months, each formatted the way it should be written. Google Gemini's
free tier then writes 3 or 4 sentences from those figures. Free models are often busy, so it tries `gemini-3.8-flash`,
then `gemini-3.6-flash`, then `gemini-3.1-flash-lite`, and the site names the model that wrote the summary. Claude works
too, with `--provider claude`.

Every number in the summary must appear among the figures. Quantity words such as "doubled" or "half", links, lists and
text over 120 words are refused too. A refused summary is never written, and the site hides the panel when there is no
summary for the latest month. Bank names come from outside data, so they never count as allowed numbers: a test hides an
instruction inside a bank name and checks that a model which obeys it cannot get anything published. On every push, the
tests check the published summary against the data again.

### Ask the data (`pipeline/ask.py`, `api/main.py`)

Gemini's free tier (the same models as the summary) turns a visitor's question into one SQL query. Claude works too,
with `ASK_PROVIDER=claude`. The model writes only the query; the numbers and names in the answer come from running it.

- DuckDB parses the query, and it must be a single SELECT that reads only the `bank_month` table. File readers, system tables, lists of typed-in values and second statements are refused.
- The database lives in memory and holds only the rows the site shows. It cannot read files or reach the network, and its settings are locked. A query returns at most 200 rows and is stopped after 5 seconds.
- Every piece of text in an answer must be a bank name, bank type or month from the data, so the model cannot slip its own words into an answer.
- Anyone can type anything, so the tests hand the code a model that obeys "ignore your rules" and check that nothing it writes gets through.
- Each visitor can ask 8 questions a minute and 50 a day, and everyone together 300 a day. That keeps the free model quota (or a paid key's bill) small.

Accuracy is measured on 30 test questions whose answers were worked out from the data (`pipeline/ask_questions.json`),
and the tests check those answers again on every push. `python -m pipeline.ask_eval` puts the questions to the model. An
answer counts as right when it has the same rows as the known answer, with the same names, months and numbers (to within
0.1%). The known answer holds only what the question asks for, so an answer may add columns. A score is published only
once every question has a reply, since a missing reply says nothing about accuracy. When the free model is busy, the next
run that day asks only the questions it missed.

Latest score: 30 of 30 right (gemini-3.1-flash-lite, 27 October 2026). Each question's result, with the query the model
wrote, is in `docs/ask_eval.json`. The question box tries `gemini-3.8-flash` first; this run used
`gemini-3.1-flash-lite` because the other two free models were out of quota that day.

The service is a small FastAPI app on Render's free plan (`render.yaml`), and it holds the API key. The free plan sleeps
after 15 quiet minutes, so the first question can take up to a minute. The page says so, and nothing else on it depends
on the service.

## Data sources

All figures come from the National Payments Corporation of India (NPCI): UPI Ecosystem Statistics, Top 50 Member
Performance ([npci.org.in](https://www.npci.org.in/product/ecosystem-statistics/upi)). The data belongs to NPCI.

- Paying banks, Jan 2022 to Oct 2024 and Sep 2026: NPCI's own API responses, saved unchanged in `data/raw/npci/`.
- Paying banks, Nov 2024 to Aug 2026, and all receiving-bank months: [Time Series of India](https://timeseriesofindia.com)'s copy of the same NPCI data, used while NPCI's site was down in October 2026. Wherever both copies exist, every bank's technical and business decline rates match exactly. The copy has volumes and decline rates only, and it is not stored in this repository.

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

Without the Time Series of India file, the pipeline builds only NPCI's own months, and the checks that need that file
skip. On GitHub Actions, the tests run on every push.

## Limits

- These are monthly totals per bank, so the shop calculator is an estimate from averages.
- The 1% line comes from press reports of RBI's request to NPCI. It is not a published rule.
- For the months filled from the copy, approval rates, debit reversals and UDIR figures are not available yet. They will come from NPCI's own files.
- The AI summary restates the month's figures and does not explain causes. On Gemini's free tier, what is sent may be used to improve Google's products. Only NPCI's public figures are sent.
- The question box's model can misread a question, and the score above shows how often. The query is always shown, so an answer can be checked. Only the table's layout, the bank names and the question are sent to the model, and on Gemini's free tier they may be used to improve Google's products.

## Used by

The UPI payment failure lab in my [Orderdesk QA project](https://github.com/Anubhavkumarkanth/orderdesk-qa-suite) fails
pretend payments at the decline rates measured here: 9.62% business and 0.29% technical declines at paying banks over the
last 12 months.
