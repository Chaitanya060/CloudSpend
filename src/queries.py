"""Read-side helpers: pull modelled data back out of the star schema as tidy
DataFrames the analytics modules and dashboard can consume.
"""
from __future__ import annotations

import pandas as pd

from src import db


def _joined() -> pd.DataFrame:
    """Fact joined to all dimensions -> one flat analytics-ready frame."""
    sql = """
        SELECT d.full_date        AS date,
               a.account_id       AS account_id,
               a.account_name     AS account_name,
               s.service_name     AS service,
               s.service_category AS category,
               s.provider         AS provider,
               f.cost             AS cost
        FROM fact_cost f
        JOIN dim_date    d ON f.date_id    = d.date_id
        JOIN dim_account a ON f.account_id = a.account_id
        JOIN dim_service s ON f.service_id = s.service_id
    """
    engine = db.get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)
    df["date"] = pd.to_datetime(df["date"])
    return df


def daily_by_service() -> pd.DataFrame:
    """Total daily cost per service (summed across accounts)."""
    df = _joined()
    return (df.groupby(["date", "service"], as_index=False)["cost"].sum()
              .sort_values("date"))


def daily_total() -> pd.DataFrame:
    """Total daily cost across everything."""
    df = _joined()
    return (df.groupby("date", as_index=False)["cost"].sum()
              .sort_values("date"))


def top_services() -> pd.DataFrame:
    df = _joined()
    return (df.groupby("service", as_index=False)["cost"].sum()
              .sort_values("cost", ascending=False))


def top_accounts() -> pd.DataFrame:
    df = _joined()
    # disambiguate accounts that share a name across clouds (e.g. two
    # "SunBird" accounts on AWS + Microsoft) and keep the label a string so
    # numeric-looking account names don't become a numeric axis.
    df["account"] = (df["account_name"].astype(str)
                     + " (" + df["provider"].astype(str) + ")")
    return (df.groupby("account", as_index=False)["cost"].sum()
              .sort_values("cost", ascending=False))


def by_provider() -> pd.DataFrame:
    df = _joined()
    return (df.groupby("provider", as_index=False)["cost"].sum()
              .sort_values("cost", ascending=False))


def by_category() -> pd.DataFrame:
    df = _joined()
    return (df.groupby("category", as_index=False)["cost"].sum()
              .sort_values("cost", ascending=False))


def month_over_month() -> pd.DataFrame:
    df = _joined()
    df["month"] = df["date"].dt.to_period("M").astype(str)
    return (df.groupby("month", as_index=False)["cost"].sum()
              .sort_values("month"))


def flat() -> pd.DataFrame:
    return _joined()
