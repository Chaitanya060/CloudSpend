"""Self-bootstrap the database.

On a fresh deploy (Streamlit Cloud, a clean clone, a new container) the SQLite
file and its tables do not exist, because `data/` is gitignored. Since all the
billing data is synthetic and produced by code, we can rebuild the whole
database on demand: generate the raw CSV, then run the ETL into the star
schema. This makes the app fully self-contained.
"""
from __future__ import annotations

from sqlalchemy import inspect as sa_inspect, text

from src import db, generate_data, etl


def database_ready() -> bool:
    """True if fact_cost exists and has rows."""
    engine = db.get_engine()
    insp = sa_inspect(engine)
    if "fact_cost" not in insp.get_table_names():
        return False
    with engine.connect() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM fact_cost")).scalar()
    return bool(n and n > 0)


def ensure_database(force: bool = False) -> bool:
    """Build the database if it's missing/empty. Returns True if it (re)built."""
    if not force and database_ready():
        return False
    generate_data.main()
    etl.run()
    return True


if __name__ == "__main__":
    built = ensure_database()
    print("Rebuilt database." if built else "Database already present.")
