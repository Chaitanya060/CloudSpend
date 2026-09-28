"""Compare spend across cloud providers (AWS vs Azure vs Oracle).

This is the multi-cloud comparison at the heart of FinOps: because every cloud
exports its bill in the same FOCUS format, the rows all share a `provider`
column, so comparing them is just a group-by. This script prints:

  1. a per-provider summary (total spend, share %, #services, #accounts, top service)
  2. a provider x service-category breakdown (where each cloud spends its money)

It reads the already-modelled data from the star schema, so run the pipeline
first (or this script will build the database for you).

Run:  python compare_clouds.py
"""
from __future__ import annotations

import pandas as pd

from src import queries, bootstrap


def _fmt_money(x: float) -> str:
    return f"${x:,.2f}"


def provider_summary(df: pd.DataFrame) -> pd.DataFrame:
    total = df["cost"].sum()
    rows = []
    for provider, g in df.groupby("provider"):
        spend = g["cost"].sum()
        top_service = (g.groupby("service")["cost"].sum()
                        .sort_values(ascending=False).index[0])
        rows.append({
            "Provider": provider,
            "Total spend": _fmt_money(spend),
            "Share %": f"{spend / total * 100:5.1f}%",
            "Services": g["service"].nunique(),
            "Accounts": g["account_id"].nunique(),
            "Top service": top_service,
        })
    out = pd.DataFrame(rows)
    # sort by raw spend (recompute to sort, since Total spend is a string)
    order = (df.groupby("provider")["cost"].sum()
               .sort_values(ascending=False).index.tolist())
    out["__o"] = out["Provider"].map({p: i for i, p in enumerate(order)})
    return out.sort_values("__o").drop(columns="__o").reset_index(drop=True)


def provider_category_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Rows = service category, columns = provider, values = spend."""
    pivot = (df.pivot_table(index="category", columns="provider",
                            values="cost", aggfunc="sum", fill_value=0.0)
               .round(2))
    pivot["Total"] = pivot.sum(axis=1).round(2)
    pivot = pivot.sort_values("Total", ascending=False)
    return pivot


def main() -> None:
    # make sure the database is built (reads the FOCUS data if needed)
    bootstrap.ensure_database()
    df = queries.flat()

    if df.empty:
        print("No data found. Run `python run_pipeline.py` first.")
        return

    total = df["cost"].sum()
    n_days = df["date"].dt.date.nunique()

    print("=" * 68)
    print("  MULTI-CLOUD SPEND COMPARISON  (FOCUS billing data)")
    print("=" * 68)
    print(f"  Period: {n_days} days   |   Total across all clouds: "
          f"{_fmt_money(total)}")
    print()

    print("-- 1. Per-provider summary " + "-" * 40)
    print(provider_summary(df).to_string(index=False))
    print()

    print("-- 2. Spend by service category, per provider " + "-" * 21)
    with pd.option_context("display.float_format", lambda v: f"{v:,.2f}"):
        print(provider_category_matrix(df).to_string())
    print()

    # cheapest vs most expensive cloud, one-line takeaway
    by_prov = df.groupby("provider")["cost"].sum().sort_values(ascending=False)
    top, bottom = by_prov.index[0], by_prov.index[-1]
    print("-" * 68)
    print(f"  Takeaway: {top} is the largest cost driver "
          f"({_fmt_money(by_prov.iloc[0])}), "
          f"{bottom} the smallest ({_fmt_money(by_prov.iloc[-1])}).")
    print("=" * 68)


if __name__ == "__main__":
    main()
