"""Anomaly detection on daily cost.

Method: per service, compute a trailing rolling mean and standard deviation
over ANOMALY_WINDOW days. Flag any day whose cost exceeds
    mean + ANOMALY_SIGMA * std
i.e. an unusually expensive day relative to that service's recent baseline.

Run:  python -m src.analytics.anomaly
"""
from __future__ import annotations

import pandas as pd

import config
from src import queries


def detect(window: int = config.ANOMALY_WINDOW,
           sigma: float = config.ANOMALY_SIGMA) -> pd.DataFrame:
    df = queries.daily_by_service().copy()
    out = []

    for service, grp in df.groupby("service"):
        grp = grp.sort_values("date").reset_index(drop=True)
        # trailing window, exclude the current day (shift) so a spike doesn't
        # inflate its own baseline
        roll = grp["cost"].shift(1).rolling(window, min_periods=3)
        grp["baseline"] = roll.mean()
        grp["std"] = roll.std()
        grp["threshold"] = grp["baseline"] + sigma * grp["std"]
        grp["is_anomaly"] = grp["cost"] > grp["threshold"]
        grp["pct_over"] = (
            (grp["cost"] - grp["baseline"]) / grp["baseline"] * 100
        ).round(1)
        out.append(grp)

    result = pd.concat(out, ignore_index=True)
    return result


def anomalies_only(**kwargs) -> pd.DataFrame:
    r = detect(**kwargs)
    cols = ["date", "service", "cost", "baseline", "threshold", "pct_over"]
    return (r[r["is_anomaly"]][cols]
            .sort_values("date", ascending=False)
            .reset_index(drop=True))


def main() -> None:
    hits = anomalies_only()
    if hits.empty:
        print("No anomalies detected.")
        return
    print(f"Detected {len(hits)} anomalous service-days "
          f"(cost > mean + {config.ANOMALY_SIGMA}sigma over "
          f"{config.ANOMALY_WINDOW}d):\n")
    with pd.option_context("display.float_format", "{:,.2f}".format):
        print(hits.to_string(index=False))


if __name__ == "__main__":
    main()
