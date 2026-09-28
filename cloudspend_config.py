"""Central configuration for CloudSpend.

Database backend is chosen here. By default we use SQLite so the whole
pipeline runs with zero setup. Flip DB_BACKEND to "mysql" (and fill in the
MySQL_* values, or set the matching env vars) to load into a real MySQL
server instead -- the rest of the code is unchanged because everything goes
through a single SQLAlchemy engine.
"""
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DATASETS_DIR = BASE_DIR / "datasets"            # versioned source data (real)

SQLITE_PATH = DATA_DIR / "cloudspend.db"

# ---------------------------------------------------------------------------
# Data source:  "focus" (real FinOps FOCUS 1.0 dataset)  or  "synthetic"
# ---------------------------------------------------------------------------
# "focus"     -> real cloud billing data from the FinOps Foundation's official
#                FOCUS 1.0 sample (AWS / Microsoft / Oracle), committed under
#                datasets/. This is the default.
# "synthetic" -> the self-generated fake CUR-style CSV (kept as a fallback /
#                for demonstrating the generator).
DATA_SOURCE = os.getenv("CLOUDSPEND_SOURCE", "focus").lower()

FOCUS_CSV = DATASETS_DIR / "focus_sample.csv"   # real dataset (source of truth)
RAW_CSV = DATA_DIR / "raw_billing.csv"          # synthetic CUR-style export

# ---------------------------------------------------------------------------
# Database backend:  "sqlite"  (default, no setup)  or  "mysql"
# ---------------------------------------------------------------------------
DB_BACKEND = os.getenv("CLOUDSPEND_DB", "sqlite").lower()

# MySQL settings (only used when DB_BACKEND == "mysql")
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "root")
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")
MYSQL_DB = os.getenv("MYSQL_DB", "cloudspend")


def get_engine_url() -> str:
    """Return the SQLAlchemy URL for the configured backend."""
    if DB_BACKEND == "mysql":
        return (
            f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
            f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}"
        )
    # default: sqlite
    return f"sqlite:///{SQLITE_PATH}"


# ---------------------------------------------------------------------------
# Synthetic data generation knobs
# ---------------------------------------------------------------------------
SEED = 42
N_DAYS = 120                     # ~4 months of history
ACCOUNTS = ["1001-prod", "1002-staging", "1003-data", "1004-sandbox"]
SERVICES = ["EC2", "S3", "RDS", "Lambda", "CloudFront", "DynamoDB"]
REGIONS = ["us-east-1", "us-west-2", "eu-west-1", "ap-south-1"]

# Anomaly detection
ANOMALY_WINDOW = 7               # rolling window in days
ANOMALY_SIGMA = 2.0              # flag if cost > mean + SIGMA * std
ANOMALY_MIN_COST = 0.10          # materiality floor: ignore trivial spend so a
                                 # near-zero baseline can't explode the % change
                                 # (a standard FinOps practice to cut alert noise)

# Forecast
FORECAST_DAYS = 30               # projection horizon
