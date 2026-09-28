# CloudSpend — Cloud Billing ETL + Cost Insights

CloudSpend is a miniature **cloud-cost (FinOps) analytics platform**. It ingests
real multi-cloud billing data, cleans and models it into a data-warehouse
**star schema**, and surfaces actionable cost insights — **anomaly detection**
(catch runaway spend) and a **30-day forecast** — through an interactive
**Streamlit dashboard**.

It is a compact, end-to-end demonstration of a real data-engineering workflow:
**raw billing data → ETL → dimensional model → analytics → dashboard**, with an
optional **event-driven AWS layer** (S3 → Lambda → RDS).

**Stack:** Python · Pandas · NumPy · scikit-learn · SQLAlchemy · SQLite / MySQL ·
Streamlit · Plotly · (optional) AWS S3 + Lambda + RDS.

---

## Table of contents

1. [What it does](#what-it-does)
2. [The data (real, not fake)](#the-data-real-not-fake)
3. [Architecture & data flow](#architecture--data-flow)
4. [The star schema (data model)](#the-star-schema-data-model)
5. [How each stage works](#how-each-stage-works)
6. [Quickstart](#quickstart)
7. [Project layout](#project-layout)
8. [Switching to MySQL](#switching-to-mysql)
9. [The AWS event-driven layer](#the-aws-event-driven-layer)
10. [Design decisions & trade-offs](#design-decisions--trade-offs)
11. [Data credit](#data-credit)

---

## What it does

| Stage | What happens |
|-------|--------------|
| **1. Ingest** | Reads a real cloud billing export (FOCUS 1.0 CSV) — or a synthetic CUR-style CSV in fallback mode. |
| **2. Transform (clean)** | Parses timestamps, handles nulls and credits/refunds (negative costs), and resolves each service to a single cloud **provider** and **service category**. |
| **3. Model (load)** | Aggregates to a **daily grain** and loads a dimensional **star schema**: one fact table + three dimensions. |
| **4. Analyze** | **Anomaly detection** (per-service rolling mean + 2σ, with a materiality floor) and a **30-day linear forecast**. |
| **5. Visualize** | A **Streamlit dashboard**: KPIs, top cost drivers, spend by provider / account / category, daily trend, an anomaly table with per-service spike charts, and the forecast. |

---

## The data (real, not fake)

By default CloudSpend runs on **real, multi-cloud billing data**: the FinOps
Foundation's official **FOCUS 1.0 sample dataset**
(`datasets/focus_sample.csv` — 10,000 rows, **AWS + Microsoft Azure + Oracle**,
September 2024).

**Why this matters:** [FOCUS](https://focus.finops.org/) (FinOps Open Cost &
Usage Specification) is the **open billing standard that AWS, Azure, and GCP all
now export their bills to**. So this pipeline consumes the *exact same schema a
real FinOps team works with* — real service names (Amazon EC2, Azure SQL
Database, RDS…), real regions, tags, commitment discounts, and **credits/refunds
as negative costs**.

> **Note on magnitude:** the amounts are small (≈ $151 total) because it is the
> Foundation's published *sample*. The values are real-format; the pipeline
> handles production volume identically — only the row count and totals scale up.

A self-contained **synthetic generator** is also included
(`CLOUDSPEND_SOURCE=synthetic`) that fabricates a messy AWS CUR-style CSV with
**deliberately planted cost spikes** — handy for demonstrating the ETL's
cleaning and the anomaly detector on known anomalies.

---

## Architecture & data flow

```
                        ┌──────────────────────────────────────────────┐
                        │              CloudSpend pipeline               │
                        └──────────────────────────────────────────────┘

  datasets/focus_sample.csv                    (real FOCUS 1.0 billing export)
            │
            ▼
   ┌─────────────────┐   extract      ┌──────────────────────────────────────┐
   │   src/etl.py    │ ─────────────▶ │  clean: parse dates, keep credits,   │
   │                 │   transform    │  resolve provider + category         │
   │                 │ ─────────────▶ │  aggregate to DAILY grain            │
   │                 │   load         └──────────────────────────────────────┘
   └─────────────────┘                              │
            │                                        ▼
            ▼                          ┌──────────────────────────────────────┐
   ┌─────────────────┐                 │      Star schema (SQLite / MySQL)     │
   │   src/db.py     │  ─────────────▶ │  fact_cost + dim_date / account /     │
   │ (SQLAlchemy)    │                 │  service                              │
   └─────────────────┘                 └──────────────────────────────────────┘
                                                     │
                          ┌──────────────────────────┼──────────────────────────┐
                          ▼                          ▼                          ▼
                 ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
                 │ analytics/      │       │ analytics/      │       │  src/queries.py │
                 │ anomaly.py      │       │ forecast.py     │       │ (fact ⋈ dims)   │
                 │ rolling mean+2σ │       │ 30-day linear   │       └─────────────────┘
                 └─────────────────┘       └─────────────────┘                │
                          └──────────────────────────┴──────────────────────────┘
                                                     ▼
                                         ┌─────────────────────────┐
                                         │   dashboard/app.py       │
                                         │   (Streamlit + Plotly)   │
                                         └─────────────────────────┘
```

**Optional cloud path:** a billing CSV lands in **S3** → an **S3 event** triggers
a **Lambda** that runs the *same* `etl.transform` / `etl.load` → writes to
**RDS (MySQL)**. See [The AWS event-driven layer](#the-aws-event-driven-layer).

---

## The star schema (data model)

CloudSpend models the data as a classic **star schema** — the standard
dimensional model for analytics warehouses. One central **fact** table holds the
measurements (cost), surrounded by **dimension** tables that describe each fact.

```
                      ┌──────────────────────────┐
                      │        dim_date          │
                      │  date_id (PK)            │
                      │  full_date, year, month, │
                      │  day, weekday            │
                      └──────────────────────────┘
                                  ▲
                                  │ date_id
   ┌──────────────────────┐      │      ┌──────────────────────────────┐
   │     dim_account      │      │      │        dim_service           │
   │  account_id (PK)     │◀──┐  │  ┌──▶│  service_id (PK)             │
   │  account_name        │   │  │  │   │  service_name                │
   └──────────────────────┘   │  │  │   │  service_category (Compute…) │
                              account│service│ provider (AWS/Azure/…)   │
                               _id  │  _id  └──────────────────────────┘
                                │   │   │
                          ┌─────┴───┴───┴─────┐
                          │     fact_cost     │
                          │  id (PK)          │
                          │  date_id   (FK)   │
                          │  account_id(FK)   │
                          │  service_id(FK)   │
                          │  cost  (measure)  │
                          └───────────────────┘
```

- **`fact_cost`** — one row per (day × account × service), with the summed
  `cost`. This is the grain of the warehouse.
- **`dim_date`** — calendar attributes for time-based slicing (month, weekday…).
- **`dim_account`** — the billing accounts.
- **`dim_service`** — the cloud service, enriched with its **provider**
  (AWS / Microsoft / Oracle) and **service category** (Compute, Storage,
  Databases…), both taken from the FOCUS data.

Analytical queries (`src/queries.py`) join the fact to the dimensions to answer
questions like "spend by provider", "top services", or "daily total".

---

## How each stage works

### 1. Extract — `src/etl.py :: extract()`
Reads the configured source. With `CLOUDSPEND_SOURCE=focus` (default) it loads
`datasets/focus_sample.csv`; with `synthetic` it (re)generates and reads the
fake CUR-style CSV.

### 2. Transform — `src/etl.py :: transform()`
For the FOCUS data it:
- maps FOCUS columns → canonical names (`ChargePeriodStart→date`,
  `BilledCost→cost`, `ServiceName→service`, …),
- parses timestamps and normalizes them to a calendar **day**,
- keeps **negative costs** (credits/refunds) as real net cost,
- fills missing account names, and
- resolves each service to **one** provider and category (the mode), then
- **aggregates to daily grain**: `sum(cost)` per (day, account, service).

### 3. Load — `src/etl.py :: load()`
Builds the three dimension tables and the fact table with surrogate keys, then
writes them through **one SQLAlchemy engine** — so the identical code targets
SQLite or MySQL. The schema is fully rebuilt each run (idempotent reload).

### 4. Anomaly detection — `src/analytics/anomaly.py`
For each service, over a **7-day trailing window** (excluding the current day so
a spike can't inflate its own baseline), compute the rolling **mean** and
**standard deviation**. A day is flagged when:

```
cost > mean + 2·σ      AND      cost ≥ materiality_floor ($0.10)
```

The **materiality floor** is a real FinOps practice: it prevents a near-zero
baseline from turning a trivial sub-cent blip into a "+160,000%" false alarm, so
only meaningful spikes surface.

### 5. Forecast — `src/analytics/forecast.py`
Fits an ordinary-least-squares **linear regression** (`scikit-learn`) to the
daily total cost and projects **30 days** forward, returning the trend
(USD/day), the projected 30-day total, and the model fit (R²).

### 6. Dashboard — `dashboard/app.py`
A Streamlit app that reads the modelled data via `src/queries.py` and renders it
with Plotly. On a **fresh deploy** it **self-builds the database** on first load
(`src/bootstrap.py`), so it works on Streamlit Cloud with zero manual steps.

---

## Quickstart

```bash
# 1. install dependencies
pip install -r requirements.txt

# 2. run the whole pipeline (ETL into the star schema + analytics summary)
python run_pipeline.py

# 3. launch the dashboard
python -m streamlit run dashboard/app.py
```

Runs on **SQLite by default** — no database server to install or configure.

### Run stages individually

```bash
python -m src.etl                  # run the ETL / load
python -m src.analytics.anomaly    # print detected anomalies
python -m src.analytics.forecast   # print the forecast summary
```

Switch to the synthetic source:

```bash
CLOUDSPEND_SOURCE=synthetic python run_pipeline.py
```

---

## Project layout

```
CloudSpend/
├── config.py                  # data source + DB backend + analytics knobs
├── run_pipeline.py            # orchestrator: ETL → analytics summary
├── requirements.txt
├── datasets/
│   └── focus_sample.csv       # REAL FOCUS 1.0 billing data (AWS/Azure/Oracle)
├── src/
│   ├── etl.py                 # extract / transform / load (FOCUS + synthetic)
│   ├── db.py                  # SQLAlchemy engine + star-schema definition
│   ├── queries.py             # read-side helpers (fact ⋈ dimensions)
│   ├── bootstrap.py           # self-builds the DB on a fresh deploy
│   ├── generate_data.py       # synthetic CUR-style generator (fallback)
│   └── analytics/
│       ├── anomaly.py         # 7-day rolling mean + 2σ + materiality floor
│       └── forecast.py        # 30-day linear projection
├── dashboard/
│   └── app.py                 # Streamlit dashboard
└── aws_lambda/
    └── handler.py             # S3 → Lambda → RDS reference handler
```

---

## Switching to MySQL

Everything goes through a single SQLAlchemy engine, so MySQL is a config flip —
no code changes:

```bash
# create the database once
mysql -u root -p -e "CREATE DATABASE cloudspend;"

# point CloudSpend at it (bash / macOS / Linux)
export CLOUDSPEND_DB=mysql
export MYSQL_USER=root MYSQL_PASSWORD=yourpw MYSQL_HOST=localhost MYSQL_DB=cloudspend
python run_pipeline.py
```

```powershell
# Windows PowerShell
$env:CLOUDSPEND_DB="mysql"; $env:MYSQL_PASSWORD="yourpw"
python run_pipeline.py
```

`fact_cost` and the three dimensions are created in MySQL and loaded exactly the
same way.

---

## The AWS event-driven layer

`aws_lambda/handler.py` is a reference implementation of the production,
**event-driven** pattern (matching a "serverless, auto-scaling" architecture):

```
Raw billing CSV uploaded to S3
        │  (S3 ObjectCreated event)
        ▼
   AWS Lambda  ──runs the SAME src/etl.py transform/load──▶  RDS (MySQL)
```

It reuses the exact `etl.transform` / `etl.load` functions, so the local and
cloud paths stay identical. To deploy: package `src/` with the handler, set
`CLOUDSPEND_DB=mysql` + the `MYSQL_*` env vars pointing at your RDS instance, and
wire an S3 `ObjectCreated` trigger to the function.

---

## Design decisions & trade-offs

- **Real FOCUS data over fake data** — using the open multi-cloud billing
  standard makes the project ingest the same schema real FinOps teams use, and
  demonstrates cross-cloud normalization.
- **SQLite default, MySQL by config** — zero-setup local runs, while a single
  env var promotes it to a real MySQL/RDS server; the code path is identical.
- **Star schema over a flat table** — the dimensional model is what signals data
  engineering (conformed dimensions, surrogate keys, a defined grain) rather
  than ad-hoc scripting.
- **Materiality floor on anomalies** — mirrors real FinOps alerting to suppress
  noise from immaterial spend.
- **Self-bootstrapping dashboard** — the app rebuilds its database on a fresh
  deploy, so it is fully reproducible from a clean clone or on Streamlit Cloud.

---

## Data credit

Real sample data from the FinOps Foundation's
[FOCUS-Sample-Data](https://github.com/FinOps-Open-Cost-and-Usage-Spec/FOCUS-Sample-Data)
repository (FOCUS 1.0), redistributed here for demonstration.
