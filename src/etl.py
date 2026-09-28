"""ETL: read the raw CUR-style CSV, clean it, aggregate to daily grain, and
load it into the MySQL/SQLite star schema.

Extract  -> read raw_billing.csv
Transform-> parse mixed dates, drop/repair nulls, normalize service names,
            aggregate to (date, account, service) daily cost
Load     -> populate dim_date / dim_account / dim_service / fact_cost

Run:  python -m src.etl
"""
from __future__ import annotations

import pandas as pd

import config
from src import db


# Map every messy raw label to a canonical service name
def _canonical_service(raw: str) -> str:
    s = str(raw).strip().lower().replace("amazon", "").replace("aws", "").strip()
    mapping = {
        "ec2": "EC2",
        "s3": "S3",
        "rds": "RDS",
        "lambda": "Lambda",
        "cloudfront": "CloudFront",
        "dynamodb": "DynamoDB",
    }
    return mapping.get(s, raw.strip())


def extract() -> pd.DataFrame:
    df = pd.read_csv(config.RAW_CSV)
    print(f"[extract] {len(df):,} raw rows")
    return df


def transform(df: pd.DataFrame) -> pd.DataFrame:
    n0 = len(df)

    # --- parse mixed date formats -> real datetime ---
    df["date"] = pd.to_datetime(df["date"], format="mixed", errors="coerce")
    df = df.dropna(subset=["date"])

    # --- handle null / bad costs ---
    df["cost"] = pd.to_numeric(df["cost"], errors="coerce")
    # drop negatives (data errors); fill nulls with 0 (no charge recorded)
    df = df[df["cost"].fillna(0) >= 0]
    n_null = df["cost"].isna().sum()
    df["cost"] = df["cost"].fillna(0.0)

    # --- normalize service names ---
    df["service"] = df["service"].map(_canonical_service)

    # --- account display name ---
    df["account_name"] = df["account_id"].str.split("-").str[-1].str.title()

    # --- aggregate to daily grain: (date, account, service) ---
    df["full_date"] = df["date"].dt.normalize()
    daily = (
        df.groupby(["full_date", "account_id", "account_name", "service"],
                   as_index=False)["cost"]
        .sum()
    )
    daily["full_date"] = pd.to_datetime(daily["full_date"])

    print(f"[transform] {n0:,} rows -> {len(daily):,} daily aggregates "
          f"(nulls repaired: {n_null})")
    return daily


def _build_dimensions(daily: pd.DataFrame):
    # dim_date
    dates = pd.DataFrame({"full_date": sorted(daily["full_date"].unique())})
    dates["full_date"] = pd.to_datetime(dates["full_date"])
    dates["date_id"] = dates["full_date"].dt.strftime("%Y%m%d").astype(int)
    dates["year"] = dates["full_date"].dt.year
    dates["month"] = dates["full_date"].dt.month
    dates["day"] = dates["full_date"].dt.day
    dates["weekday"] = dates["full_date"].dt.day_name()

    # dim_account
    accounts = (
        daily[["account_id", "account_name"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )

    # dim_service
    services = pd.DataFrame(
        {"service_name": sorted(daily["service"].unique())}
    )
    services["service_id"] = range(1, len(services) + 1)

    return dates, accounts, services


def load(daily: pd.DataFrame) -> None:
    engine = db.get_engine()
    db.reset_schema(engine)

    dates, accounts, services = _build_dimensions(daily)

    # build fact table with surrogate keys (attach service_id via dim_service)
    fact = daily.merge(services, left_on="service", right_on="service_name", how="left")
    fact["date_id"] = pd.to_datetime(fact["full_date"]).dt.strftime("%Y%m%d").astype(int)
    fact = fact[["date_id", "account_id", "service_id", "cost"]]

    with engine.begin() as conn:
        dates.to_sql("dim_date", conn, if_exists="append", index=False)
        accounts.to_sql("dim_account", conn, if_exists="append", index=False)
        services[["service_id", "service_name"]].to_sql(
            "dim_service", conn, if_exists="append", index=False)
        fact.to_sql("fact_cost", conn, if_exists="append", index=False)

    print(f"[load] dim_date={len(dates)}, dim_account={len(accounts)}, "
          f"dim_service={len(services)}, fact_cost={len(fact)} "
          f"-> {config.get_engine_url()}")


def run() -> None:
    df = extract()
    daily = transform(df)
    load(daily)
    print("[etl] done.")


if __name__ == "__main__":
    run()
