"""ETL: read a cloud billing export, clean it, aggregate to daily grain, and
load it into the MySQL/SQLite star schema.

Two sources are supported (chosen in config.DATA_SOURCE):

  * "focus"      -- REAL data: the FinOps Foundation's official FOCUS 1.0
                    sample (datasets/focus_sample.csv). This is the default.
  * "synthetic"  -- the self-generated fake CUR-style CSV (fallback/demo).

Both paths clean the data and land the same star schema:
    fact_cost + dim_date + dim_account + dim_service

Run:  python -m src.etl
"""
from __future__ import annotations

import pandas as pd

import config
from src import db


# ---------------------------------------------------------------------------
# EXTRACT
# ---------------------------------------------------------------------------
def extract() -> pd.DataFrame:
    if config.DATA_SOURCE == "focus":
        df = pd.read_csv(config.FOCUS_CSV)
        print(f"[extract] {len(df):,} rows from REAL FOCUS dataset "
              f"({config.FOCUS_CSV.name})")
    else:
        # synthetic: generate the raw CSV on demand if missing
        if not config.RAW_CSV.exists():
            from src import generate_data
            generate_data.main()
        df = pd.read_csv(config.RAW_CSV)
        print(f"[extract] {len(df):,} rows from synthetic CSV")
    return df


# ---------------------------------------------------------------------------
# TRANSFORM
# ---------------------------------------------------------------------------
def _transform_focus(df: pd.DataFrame) -> pd.DataFrame:
    """Map the FOCUS 1.0 schema onto our canonical daily-grain frame."""
    n0 = len(df)

    df = df.rename(columns={
        "ChargePeriodStart": "date",
        "BillingAccountId": "account_id",
        "BillingAccountName": "account_name",
        "ServiceName": "service",
        "ServiceCategory": "category",
        "ProviderName": "provider",
        "BilledCost": "cost",
    })

    # dates: FOCUS timestamps -> normalize to day
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["full_date"] = df["date"].dt.normalize()

    # costs: BilledCost can be negative (credits/refunds) -- keep as real net cost
    df["cost"] = pd.to_numeric(df["cost"], errors="coerce").fillna(0.0)

    # accounts: fill missing names with the id
    df["account_id"] = df["account_id"].astype(str)
    df["account_name"] = df["account_name"].fillna(df["account_id"]).astype(str)

    # each service maps to one provider/category -> resolve to the mode so the
    # dimension stays consistent (3 services carry >1 category in raw data)
    cat_map = df.groupby("service")["category"].agg(
        lambda s: s.mode().iat[0] if not s.mode().empty else "Other").to_dict()
    prov_map = df.groupby("service")["provider"].agg(
        lambda s: s.mode().iat[0] if not s.mode().empty else "Unknown").to_dict()
    df["category"] = df["service"].map(cat_map)
    df["provider"] = df["service"].map(prov_map)

    daily = (
        df.groupby(["full_date", "account_id", "account_name",
                    "service", "provider", "category"], as_index=False)["cost"]
        .sum()
    )
    print(f"[transform] {n0:,} rows -> {len(daily):,} daily aggregates "
          f"| {daily['provider'].nunique()} providers, "
          f"{daily['service'].nunique()} services, "
          f"{daily['account_id'].nunique()} accounts")
    return daily


def _canonical_service(raw: str) -> str:
    s = str(raw).strip().lower().replace("amazon", "").replace("aws", "").strip()
    mapping = {"ec2": "EC2", "s3": "S3", "rds": "RDS", "lambda": "Lambda",
               "cloudfront": "CloudFront", "dynamodb": "DynamoDB"}
    return mapping.get(s, str(raw).strip())


def _transform_synthetic(df: pd.DataFrame) -> pd.DataFrame:
    """Clean the self-generated CUR-style CSV."""
    n0 = len(df)
    df["date"] = pd.to_datetime(df["date"], format="mixed", errors="coerce")
    df = df.dropna(subset=["date"])
    df["cost"] = pd.to_numeric(df["cost"], errors="coerce")
    df = df[df["cost"].fillna(0) >= 0]
    df["cost"] = df["cost"].fillna(0.0)
    df["service"] = df["service"].map(_canonical_service)
    df["account_name"] = df["account_id"].str.split("-").str[-1].str.title()
    df["provider"] = "AWS"
    df["category"] = "Other"
    df["full_date"] = df["date"].dt.normalize()

    daily = (
        df.groupby(["full_date", "account_id", "account_name",
                    "service", "provider", "category"], as_index=False)["cost"]
        .sum()
    )
    print(f"[transform] {n0:,} rows -> {len(daily):,} daily aggregates")
    return daily


def transform(df: pd.DataFrame) -> pd.DataFrame:
    if config.DATA_SOURCE == "focus":
        return _transform_focus(df)
    return _transform_synthetic(df)


# ---------------------------------------------------------------------------
# LOAD
# ---------------------------------------------------------------------------
def _build_dimensions(daily: pd.DataFrame):
    dates = pd.DataFrame({"full_date": sorted(daily["full_date"].unique())})
    dates["full_date"] = pd.to_datetime(dates["full_date"])
    dates["date_id"] = dates["full_date"].dt.strftime("%Y%m%d").astype(int)
    dates["year"] = dates["full_date"].dt.year
    dates["month"] = dates["full_date"].dt.month
    dates["day"] = dates["full_date"].dt.day
    dates["weekday"] = dates["full_date"].dt.day_name()

    accounts = (daily[["account_id", "account_name"]]
                .drop_duplicates().reset_index(drop=True))

    services = (daily[["service", "provider", "category"]]
                .drop_duplicates("service")
                .sort_values("service")
                .reset_index(drop=True)
                .rename(columns={"service": "service_name",
                                 "category": "service_category"}))
    services["service_id"] = range(1, len(services) + 1)

    return dates, accounts, services


def load(daily: pd.DataFrame) -> None:
    engine = db.get_engine()
    db.reset_schema(engine)

    dates, accounts, services = _build_dimensions(daily)

    fact = daily.merge(services, left_on="service",
                       right_on="service_name", how="left")
    fact["date_id"] = pd.to_datetime(
        fact["full_date"]).dt.strftime("%Y%m%d").astype(int)
    fact = fact[["date_id", "account_id", "service_id", "cost"]]

    with engine.begin() as conn:
        dates.to_sql("dim_date", conn, if_exists="append", index=False)
        accounts.to_sql("dim_account", conn, if_exists="append", index=False)
        services[["service_id", "service_name", "service_category", "provider"]]\
            .to_sql("dim_service", conn, if_exists="append", index=False)
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
