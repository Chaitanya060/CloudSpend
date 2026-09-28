"""SQLAlchemy engine + star-schema definition for CloudSpend.

Schema (classic star):

    fact_cost(date_id, account_id, service_id, cost)
        |__ dim_date(date_id, full_date, year, month, day, weekday)
        |__ dim_account(account_id, account_name)
        |__ dim_service(service_id, service_name)

Works identically on SQLite (default) and MySQL -- the backend is selected in
config.py and everything here goes through one engine.
"""
from __future__ import annotations

from sqlalchemy import (
    Column, Date, Float, ForeignKey, Integer, String, Table, MetaData,
    create_engine,
)
from sqlalchemy.engine import Engine

import config

metadata = MetaData()

dim_date = Table(
    "dim_date", metadata,
    Column("date_id", Integer, primary_key=True),      # YYYYMMDD surrogate key
    Column("full_date", Date, nullable=False),
    Column("year", Integer, nullable=False),
    Column("month", Integer, nullable=False),
    Column("day", Integer, nullable=False),
    Column("weekday", String(10), nullable=False),
)

dim_account = Table(
    "dim_account", metadata,
    Column("account_id", String(128), primary_key=True),
    Column("account_name", String(128), nullable=False),
)

dim_service = Table(
    "dim_service", metadata,
    Column("service_id", Integer, primary_key=True, autoincrement=True),
    Column("service_name", String(128), nullable=False, unique=True),
    Column("service_category", String(64)),   # e.g. Compute, Storage (FOCUS)
    Column("provider", String(32)),            # AWS / Microsoft / Oracle
)

fact_cost = Table(
    "fact_cost", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("date_id", Integer, ForeignKey("dim_date.date_id"), nullable=False),
    Column("account_id", String(128), ForeignKey("dim_account.account_id"), nullable=False),
    Column("service_id", Integer, ForeignKey("dim_service.service_id"), nullable=False),
    Column("cost", Float, nullable=False),
)


def get_engine() -> Engine:
    return create_engine(config.get_engine_url(), future=True)


def reset_schema(engine: Engine) -> None:
    """Drop and recreate all tables (idempotent full reload)."""
    metadata.drop_all(engine)
    metadata.create_all(engine)


if __name__ == "__main__":
    eng = get_engine()
    reset_schema(eng)
    print(f"Schema created on: {config.get_engine_url()}")
