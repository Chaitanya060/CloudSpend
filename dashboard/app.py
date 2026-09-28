"""CloudSpend dashboard -- Streamlit.

Surfaces cloud cost insights: KPIs, top cost drivers, month-over-month trend,
detected anomalies, and a 30-day spend forecast.

Run:  streamlit run dashboard/app.py
(Run `python run_pipeline.py` first so the database is populated.)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# make project root importable when launched via `streamlit run`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config                              # noqa: E402
from src import queries                    # noqa: E402
from src.analytics import anomaly, forecast  # noqa: E402

st.set_page_config(page_title="CloudSpend", page_icon="💸", layout="wide")


@st.cache_data(ttl=60)
def load_all():
    return {
        "flat": queries.flat(),
        "daily_total": queries.daily_total(),
        "daily_by_service": queries.daily_by_service(),
        "top_services": queries.top_services(),
        "top_accounts": queries.top_accounts(),
        "mom": queries.month_over_month(),
        "anomalies": anomaly.anomalies_only(),
    }


st.title("💸 CloudSpend — Cloud Cost Insights")
st.caption(f"Cloud billing ETL + anomaly detection + forecast · backend: `{config.DB_BACKEND}`")

try:
    data = load_all()
except Exception as e:  # noqa: BLE001
    st.error(f"Could not read the database. Run `python run_pipeline.py` first.\n\n{e}")
    st.stop()

flat = data["flat"]
if flat.empty:
    st.warning("No data found. Run `python run_pipeline.py` to populate the database.")
    st.stop()

# ---------------------------------------------------------------- KPIs
total_spend = flat["cost"].sum()
mom = data["mom"]
n_anom = len(data["anomalies"])
_, fc_summary = forecast.forecast()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total spend (all time)", f"${total_spend:,.0f}")
if len(mom) >= 2:
    delta = (mom["cost"].iloc[-1] - mom["cost"].iloc[-2]) / mom["cost"].iloc[-2] * 100
    c2.metric(f"Latest month ({mom['month'].iloc[-1]})",
              f"${mom['cost'].iloc[-1]:,.0f}", f"{delta:+.1f}% MoM")
else:
    c2.metric("Latest month", f"${mom['cost'].iloc[-1]:,.0f}")
c3.metric("Anomalies detected", n_anom)
c4.metric("Forecast next 30d", f"${fc_summary['next_30d_total']:,.0f}",
          f"{fc_summary['daily_trend_usd']:+.2f} USD/day")

st.divider()

# ---------------------------------------------------------------- Top drivers
left, right = st.columns(2)
with left:
    st.subheader("Top cost drivers — by service")
    ts = data["top_services"]
    fig = px.bar(ts, x="cost", y="service", orientation="h",
                 labels={"cost": "Total cost (USD)", "service": ""})
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=340,
                      margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("Spend by account")
    ta = data["top_accounts"]
    fig = px.pie(ta, values="cost", names="account_name", hole=0.45)
    fig.update_layout(height=340, margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------- MoM trend
st.subheader("Month-over-month spend")
fig = px.bar(mom, x="month", y="cost", labels={"cost": "USD", "month": ""})
fig.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0))
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---------------------------------------------------------------- Anomalies
st.subheader("🚨 Detected cost anomalies")
st.caption(f"Daily cost above mean + {config.ANOMALY_SIGMA}σ over a "
           f"{config.ANOMALY_WINDOW}-day rolling window, per service.")
anom = data["anomalies"]
if anom.empty:
    st.success("No anomalies detected in the current data.")
else:
    show = anom.copy()
    show["date"] = show["date"].dt.date
    show = show.rename(columns={
        "cost": "cost ($)", "baseline": "baseline ($)",
        "threshold": "threshold ($)", "pct_over": "% over baseline"})
    st.dataframe(
        show.style.format({
            "cost ($)": "{:,.2f}", "baseline ($)": "{:,.2f}",
            "threshold ($)": "{:,.2f}", "% over baseline": "{:+.0f}%"}),
        use_container_width=True, hide_index=True)

    # per-service line with anomaly markers
    svc = st.selectbox("Inspect a service", sorted(anom["service"].unique()))
    dbs = data["daily_by_service"]
    line = dbs[dbs["service"] == svc]
    marks = anom[anom["service"] == svc]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=line["date"], y=line["cost"],
                             mode="lines", name="daily cost"))
    fig.add_trace(go.Scatter(x=marks["date"], y=marks["cost"], mode="markers",
                             name="anomaly", marker=dict(color="red", size=11,
                                                         symbol="x")))
    fig.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0),
                      yaxis_title="USD")
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---------------------------------------------------------------- Forecast
st.subheader("📈 30-day spend forecast")
combined, summary = forecast.forecast()
fig = go.Figure()
actual = combined[combined["kind"] == "actual"]
fut = combined[combined["kind"] == "forecast"]
fig.add_trace(go.Scatter(x=actual["date"], y=actual["cost"],
                         mode="lines", name="actual"))
fig.add_trace(go.Scatter(x=fut["date"], y=fut["cost"], mode="lines",
                         name="forecast", line=dict(dash="dash")))
fig.update_layout(height=340, margin=dict(l=0, r=0, t=10, b=0), yaxis_title="USD")
st.plotly_chart(fig, use_container_width=True)

fc1, fc2, fc3 = st.columns(3)
fc1.metric("Projected 30-day spend", f"${summary['next_30d_total']:,.0f}")
fc2.metric("Daily trend", f"{summary['daily_trend_usd']:+.2f} USD/day")
fc3.metric("Model fit (R²)", summary["r2"])
