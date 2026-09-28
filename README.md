# CloudSpend — Cloud Billing ETL + Cost Insights

A miniature cloud-cost (FinOps) platform: it **ingests raw cloud billing data,
cleans and models it into a star schema, and surfaces cost insights** with
anomaly detection and a 30-day spend forecast — served through a Streamlit
dashboard.

Built on the exact stack the pipeline targets: **Python · Pandas · NumPy ·
scikit-learn · SQLAlchemy · MySQL/SQLite · (optional) AWS S3 + Lambda**.

---

## What it does

| Layer | What happens |
|-------|--------------|
| **Generate** | Synthesizes an AWS Cost-and-Usage-Report-style CSV (`date, account_id, service, region, usage_type, cost, tags`) with *deliberately messy* data (nulls, mixed date formats, inconsistent service names) and **planted cost spikes**. |
| **ETL** | Cleans (null repair, date parsing, service-name normalization), aggregates to daily grain, and loads a **star schema**: `fact_cost` + `dim_date`, `dim_account`, `dim_service`. |
| **Anomaly detection** | Per service, a 7-day trailing rolling mean + std; flags any day above `mean + 2σ`. |
| **Forecast** | 30-day spend projection via linear regression (`scikit-learn`). |
| **Dashboard** | Streamlit UI: KPIs, top cost drivers, month-over-month, anomaly table + per-service chart, forecast chart. |

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
├── config.py                  # backend + generation/analytics knobs
├── run_pipeline.py            # orchestrator: generate -> etl -> summary
├── src/
│   ├── generate_data.py       # synthetic CUR-style CSV with planted spikes
│   ├── db.py                  # SQLAlchemy engine + star schema
│   ├── etl.py                 # extract / transform / load
│   ├── queries.py             # read-side helpers (fact ⋈ dims)
│   └── analytics/
│       ├── anomaly.py         # 7-day rolling mean + 2σ
│       └── forecast.py        # 30-day linear projection
├── dashboard/app.py           # Streamlit dashboard
└── aws_lambda/handler.py      # S3 -> Lambda -> RDS reference handler
```

## Run pieces individually

```bash
python -m src.generate_data        # just (re)generate the raw CSV
python -m src.etl                  # just run the ETL/load
python -m src.analytics.anomaly    # print detected anomalies
python -m src.analytics.forecast   # print forecast summary
```
