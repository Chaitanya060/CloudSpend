"""30-day spend forecast via linear regression on the daily total.

Fits a simple linear trend (ordinary least squares) to historical daily total
cost and projects FORECAST_DAYS into the future. Deliberately simple -- it
checks the "cost forecasting" box and is easy to explain in an interview.

Run:  python -m src.analytics.forecast
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

import config
from src import queries


def forecast(horizon: int = config.FORECAST_DAYS):
    hist = queries.daily_total().sort_values("date").reset_index(drop=True)
    hist["t"] = np.arange(len(hist))

    X = hist[["t"]].values
    y = hist["cost"].values
    model = LinearRegression().fit(X, y)

    future_t = np.arange(len(hist), len(hist) + horizon).reshape(-1, 1)
    future_pred = model.predict(future_t)
    future_pred = np.clip(future_pred, 0, None)  # cost can't be negative

    last_date = hist["date"].max()
    future_dates = pd.date_range(
        last_date + pd.Timedelta(days=1), periods=horizon, freq="D")

    future = pd.DataFrame({
        "date": future_dates,
        "cost": future_pred,
        "kind": "forecast",
    })
    hist_out = hist[["date", "cost"]].copy()
    hist_out["kind"] = "actual"

    combined = pd.concat([hist_out, future], ignore_index=True)

    summary = {
        "daily_trend_usd": round(float(model.coef_[0]), 2),
        "next_30d_total": round(float(future_pred.sum()), 2),
        "last_actual_day": round(float(y[-1]), 2),
        "projected_day_30": round(float(future_pred[-1]), 2),
        "r2": round(float(model.score(X, y)), 3),
    }
    return combined, summary


def main() -> None:
    combined, summary = forecast()
    print("Forecast summary:")
    for k, v in summary.items():
        print(f"  {k:18s}: {v}")
    print(f"\nProjected next {config.FORECAST_DAYS}-day spend: "
          f"${summary['next_30d_total']:,.2f}")


if __name__ == "__main__":
    main()
