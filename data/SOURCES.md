# Data sources

All figures come from the National Payments Corporation of India (NPCI): UPI Ecosystem Statistics, "Top 50 Member
Performance" (remitter and beneficiary banks, monthly): https://www.npci.org.in/product/ecosystem-statistics/upi.
The data belongs to NPCI.

Every month on both sides comes from NPCI's API responses, saved unchanged in `data/raw/npci/`, with all columns, including deemed approved % on the beneficiary side.

Corrections to NPCI's own data. The pipeline makes these; the raw files stay as downloaded.

- Aug 2022, remitter: every bank's debit reversal success % was published without its decimal point ("9123.00%" for 91.23%). The pipeline divides that month by 100.
- Jan 2025, beneficiary: every percentage was published as a two-decimal fraction ("0.00%" for 0.38%), so the detail is lost. The pipeline blanks that month's percentages and keeps its volumes. [Time Series of India](https://timeseriesofindia.com)'s copy of the month carries the same rounded values, so it cannot fill the gap.
- Sep 2024, beneficiary: Tamilnad Mercantile Bank's approved % was published as 124.22%. It is left blank.
- Beneficiary, mostly Jan 2022 to Jun 2023: NPCI reported deemed approvals outside approved %, while later months include them. Where a row adds up to 100 only with deemed approvals, they are added into approved %, so it means the same thing every month.
- Mar and Jun 2026, remitter: NPCI lists Slice Small Finance Bank twice under the same name. Both rows are kept; the second is named "Slice Small Finance Bank (second NPCI entry)".

Left as published: Sep 2025 remitter lists Sr. No. 30 twice and no 39, and six beneficiary rows add up to between 97.56 and 100.48 (Citibank and Karnataka Vikas Grameena Bank Dec 2022, Yes Bank Mar and Apr 2023, RBL Bank Apr 2023, Canara Bank Nov 2024).

