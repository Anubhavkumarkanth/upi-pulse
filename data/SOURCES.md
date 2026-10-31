# Data sources

All figures come from the National Payments Corporation of India (NPCI): UPI Ecosystem Statistics, "Top 50 Member
Performance" (remitter and beneficiary banks, monthly): https://www.npci.org.in/product/ecosystem-statistics/upi.
The data belongs to NPCI.

How each month got here (the `source` column of `bank_month` says which):

| `source` | Months | What it holds |
|---|---|---|
| `npci` | Remitter: every month. Beneficiary: every month except Jan 2025 | NPCI's API responses, saved unchanged in `data/raw/npci/`. All columns, including deemed approved % on the beneficiary side. |
| `tsoi` | Beneficiary: Jan 2025 | [Time Series of India](https://timeseriesofindia.com)'s processed copy of the same NPCI data, used because NPCI's own file for that month lost its decimal detail. Volume (to 0.1 million), BD % and TD % only. Kept local in `data/raw/tsoi/`, not in this repository. |

Checks on the `tsoi` copy (`tests/test_data_quality.py`):

- On all 113 months where both copies exist, every bank's BD % and TD % match NPCI's file exactly, and volumes agree to 0.1 million.
- The only differences are remitter Jul 2024, where Time Series of India merges AU Small Finance Bank's two entries into one row, and Yes Bank's beneficiary volume for Oct 2022 (1,219.77 million in NPCI's file, 1,227.7 million in the copy).

Corrections to NPCI's own data. The pipeline makes these; the raw files stay as downloaded.

- Aug 2022, remitter: every bank's debit reversal success % was published without its decimal point ("9123.00%" for 91.23%). The pipeline divides that month by 100.
- Jan 2025, beneficiary: every percentage was published as a two-decimal fraction, so the detail is lost. NPCI's file is kept but not used, and the `tsoi` copy fills that month.
- Sep 2024, beneficiary: Tamilnad Mercantile Bank's approved % was published as 124.22%. It is left blank.
- Beneficiary, mostly Jan 2022 to Jun 2023: NPCI reported deemed approvals outside approved %, while later months include them. Where a row adds up to 100 only with deemed approvals, they are added into approved %, so it means the same thing every month.
- Mar and Jun 2026, remitter: NPCI lists Slice Small Finance Bank twice under the same name. Both rows are kept; the second is named "Slice Small Finance Bank (second NPCI entry)".

Left as published: Sep 2025 remitter lists Sr. No. 30 twice and no 39, and six beneficiary rows add up to between 97.56 and 100.48 (Citibank and Karnataka Vikas Grameena Bank Dec 2022, Yes Bank Mar and Apr 2023, RBL Bank Apr 2023, Canara Bank Nov 2024).

