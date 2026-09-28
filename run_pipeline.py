"""End-to-end pipeline runner: generate -> ETL -> analytics summary.

Run:  python run_pipeline.py
Then: streamlit run dashboard/app.py
"""
from __future__ import annotations

import config
from src import generate_data, etl
from src.analytics import anomaly, forecast


def main() -> None:
    print("=" * 60)
    print(f"CloudSpend pipeline  |  backend={config.DB_BACKEND}")
    print("=" * 60)

    print("\n[1/4] Generating synthetic billing data...")
    generate_data.main()

    print("\n[2/4] Running ETL into star schema...")
    etl.run()

    print("\n[3/4] Anomaly detection...")
    hits = anomaly.anomalies_only()
    print(f"  -> {len(hits)} anomalous service-days flagged")
    if not hits.empty:
        for _, r in hits.head(10).iterrows():
            print(f"     {r['date'].date()}  {r['service']:<11} "
                  f"${r['cost']:>10,.2f}  (+{r['pct_over']:.0f}% vs baseline)")

    print("\n[4/4] 30-day forecast...")
    _, summary = forecast.forecast()
    print(f"  -> projected next {config.FORECAST_DAYS}d spend: "
          f"${summary['next_30d_total']:,.2f} "
          f"(trend {summary['daily_trend_usd']:+.2f} USD/day, "
          f"R2={summary['r2']})")

    print("\nDone. Launch the dashboard with:")
    print("  streamlit run dashboard/app.py")


if __name__ == "__main__":
    main()
