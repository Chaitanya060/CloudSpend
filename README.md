# CloudSpend — Cloud Billing ETL + Cost Insights

A miniature cloud-cost (FinOps) platform: it **ingests real cloud billing data,
cleans and models it into a star schema, and surfaces cost insights** with
anomaly detection and a 30-day spend forecast — served through a Streamlit
dashboard.

Built on the exact stack the pipeline targets: **Python · Pandas · NumPy ·
scikit-learn · SQLAlchemy · MySQL/SQLite · (optional) AWS S3 + Lambda**.

## Data source

By default CloudSpend runs on **real, multi-cloud billing data**: the FinOps
Foundation's official **FOCUS 1.0 sample dataset** (`datasets/focus_sample.csv`,
10,000 rows spanning **AWS, Microsoft Azure, and Oracle** for September 2024).
[FOCUS](https://focus.finops.org/) (FinOps Open Cost & Usage Specification) is
the open billing standard that AWS, Azure, and GCP all now export to — so this
pipeline ingests the *same schema a real FinOps team works with*, including real
service names, regions, tags, and credits/refunds (negative costs).

A self-contained **synthetic** generator is also included as a fallback / demo
(`CLOUDSPEND_SOURCE=synthetic`) — useful for showing the ETL on deliberately
messy data with planted anomalies.

---

## What it does

| Layer | What happens |
|-------|--------------|
| **Ingest** | Reads the real FOCUS 1.0 billing export (or a synthetic CUR-style CSV in fallback mode). |
| **ETL** | Cleans (date parsing, null/credit handling, provider & category resolution), aggregates to daily grain, and loads a **star schema**: `fact_cost` + `dim_date`, `dim_account`, `dim_service` (service carries `provider` + `category`). |
| **Anomaly detection** | Per service, a 7-day trailing rolling mean + std; flags any day above `mean + 2σ`, with a **materiality floor** so trivial (sub-cent) spend can't create false alarms. |
| **Forecast** | 30-day spend projection via linear regression (`scikit-learn`). |
| **Dashboard** | Streamlit UI: KPIs, top cost drivers, **spend by cloud provider**, by account, by category, daily trend, anomaly table + per-service chart, forecast chart. |

---

## Quickstart

```bash
# 1. install
pip install -r requirements.txt

# 2. run the whole pipeline (generate -> ETL -> analytics summary)
python run_pipeline.py

# 3. launch the dashboard
python -m streamlit run dashboard/app.py
```

That's it — it runs on **SQLite by default**, so no database setup is required.

---

## Star schema

```
fact_cost(date_id, account_id, service_id, cost)
   ├── dim_date(date_id, full_date, year, month, day, weekday)
   ├── dim_account(account_id, account_name)
   └── dim_service(service_id, service_name)
```

## Switching to MySQL

Everything goes through one SQLAlchemy engine, so MySQL is a config flip:

```bash
# create the database once
mysql -u root -p -e "CREATE DATABASE cloudspend;"

# point CloudSpend at it
export CLOUDSPEND_DB=mysql
export MYSQL_USER=root MYSQL_PASSWORD=yourpw MYSQL_HOST=localhost MYSQL_DB=cloudspend
# (Windows PowerShell: $env:CLOUDSPEND_DB="mysql"  etc.)

python run_pipeline.py
```

No code changes — `fact_cost` and the three dimensions are created in MySQL and
loaded exactly the same way.

---

## Event-driven layer (AWS S3 → Lambda → RDS)

`aws_lambda/handler.py` is a reference implementation of the production pattern:

```
Raw billing CSV uploaded to S3  ->  S3 ObjectCreated event  ->  Lambda
   ->  runs the same src/etl.py transform  ->  writes to RDS (MySQL)
```

It reuses the exact `etl.transform` / `etl.load` functions, so the local and
cloud paths stay identical. To deploy: package `src/` with the handler, set
`CLOUDSPEND_DB=mysql` + the `MYSQL_*` env vars pointing at your RDS instance,
and wire an S3 `ObjectCreated` trigger to the function.

---

## Project layout

```
CloudSpend/
├── config.py                  # data source + backend + analytics knobs
├── run_pipeline.py            # orchestrator: etl -> analytics summary
├── datasets/
│   └── focus_sample.csv       # REAL FOCUS 1.0 billing data (AWS/Azure/Oracle)
├── src/
│   ├── etl.py                 # extract / transform / load (FOCUS + synthetic)
│   ├── db.py                  # SQLAlchemy engine + star schema
│   ├── queries.py             # read-side helpers (fact ⋈ dims)
│   ├── bootstrap.py           # self-builds the DB on a fresh deploy
│   ├── generate_data.py       # synthetic CUR-style generator (fallback)
│   └── analytics/
│       ├── anomaly.py         # 7-day rolling mean + 2σ + materiality floor
│       └── forecast.py        # 30-day linear projection
├── dashboard/app.py           # Streamlit dashboard
└── aws_lambda/handler.py      # S3 -> Lambda -> RDS reference handler
```

## Run pieces individually

```bash
python -m src.etl                  # run the ETL/load
python -m src.analytics.anomaly    # print detected anomalies
python -m src.analytics.forecast   # print forecast summary
```

Switch data source: `CLOUDSPEND_SOURCE=synthetic python run_pipeline.py`

## Data credit

Real sample data from the FinOps Foundation's
[FOCUS-Sample-Data](https://github.com/FinOps-Open-Cost-and-Usage-Spec/FOCUS-Sample-Data)
repository (FOCUS 1.0), redistributed here for demonstration.
