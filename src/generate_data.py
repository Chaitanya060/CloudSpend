"""Generate synthetic AWS Cost-and-Usage-Report (CUR) style billing data.

Produces a messy CSV on purpose (nulls, inconsistent service-name casing,
mixed date formats) so the ETL step has real cleaning to do. It also plants
deliberate cost spikes so the anomaly detector has something to find.

Run:  python -m src.generate_data
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

import config


# Baseline daily cost per service (USD) -- realistic-ish relative scale
SERVICE_BASELINE = {
    "EC2": 120.0,
    "S3": 25.0,
    "RDS": 80.0,
    "Lambda": 8.0,
    "CloudFront": 15.0,
    "DynamoDB": 18.0,
}

USAGE_TYPES = {
    "EC2": ["BoxUsage:t3.medium", "BoxUsage:m5.large", "EBS:VolumeUsage"],
    "S3": ["TimedStorage-ByteHrs", "Requests-Tier1", "DataTransfer-Out"],
    "RDS": ["InstanceUsage:db.t3", "StorageUsage", "IOUsage"],
    "Lambda": ["Lambda-GB-Second", "Request"],
    "CloudFront": ["DataTransfer-Out", "Requests-HTTPS"],
    "DynamoDB": ["ReadCapacityUnit-Hrs", "WriteCapacityUnit-Hrs"],
}

# Messy variants used at random so ETL has to normalize them
NAME_VARIANTS = {
    "EC2": ["EC2", "ec2", "Amazon EC2", "AmazonEC2"],
    "S3": ["S3", "s3", "Amazon S3", "AmazonS3"],
    "RDS": ["RDS", "rds", "Amazon RDS"],
    "Lambda": ["Lambda", "lambda", "AWS Lambda"],
    "CloudFront": ["CloudFront", "cloudfront", "Amazon CloudFront"],
    "DynamoDB": ["DynamoDB", "dynamodb", "Amazon DynamoDB"],
}

TAG_POOL = [
    "env=prod", "env=staging", "env=dev",
    "team=platform", "team=data", "team=web",
    "",  # some rows have no tags
]


def _daily_cost(service: str, day_idx: int, rng: random.Random) -> float:
    """Baseline + weekly seasonality + gentle upward trend + noise."""
    base = SERVICE_BASELINE[service]
    # slow growth (~15% over the window)
    trend = 1.0 + 0.0015 * day_idx
    # weekly seasonality: cheaper on weekends
    weekday = day_idx % 7
    season = 0.8 if weekday in (5, 6) else 1.0
    noise = rng.uniform(0.85, 1.15)
    return base * trend * season * noise


def _planted_spikes(n_days: int) -> dict[tuple[int, str], float]:
    """Map (day_index, service) -> multiplier for deliberate anomalies."""
    return {
        (n_days - 40, "EC2"): 3.2,     # runaway EC2 fleet
        (n_days - 25, "S3"): 4.0,      # accidental data-transfer blowout
        (n_days - 12, "RDS"): 2.8,     # oversized DB instance left on
        (n_days - 5, "Lambda"): 5.0,   # infinite-loop deploy
    }


def generate(n_days: int = config.N_DAYS) -> pd.DataFrame:
    rng = random.Random(config.SEED)
    np.random.seed(config.SEED)

    start = datetime.today().date() - timedelta(days=n_days - 1)
    spikes = _planted_spikes(n_days)
    rows: list[dict] = []

    for day_idx in range(n_days):
        date = start + timedelta(days=day_idx)
        for account in config.ACCOUNTS:
            # sandbox account has lighter, patchier usage
            acct_factor = 0.3 if "sandbox" in account else 1.0
            for service in config.SERVICES:
                # not every service is used by every account every day
                if rng.random() < 0.1:
                    continue
                cost = _daily_cost(service, day_idx, rng) * acct_factor
                mult = spikes.get((day_idx, service))
                if mult and account == config.ACCOUNTS[0]:  # spikes hit prod
                    cost *= mult

                region = rng.choice(config.REGIONS)
                usage_type = rng.choice(USAGE_TYPES[service])
                service_label = rng.choice(NAME_VARIANTS[service])

                # mixed date formats to force parsing in ETL
                if rng.random() < 0.5:
                    date_str = date.strftime("%Y-%m-%d")
                else:
                    date_str = date.strftime("%m/%d/%Y")

                # inject some nulls (~3% of cost values)
                cost_val = round(cost, 4)
                if rng.random() < 0.03:
                    cost_val = None

                rows.append({
                    "date": date_str,
                    "account_id": account,
                    "service": service_label,
                    "region": region,
                    "usage_type": usage_type,
                    "cost": cost_val,
                    "tags": rng.choice(TAG_POOL),
                })

    df = pd.DataFrame(rows)
    # shuffle so it doesn't look pre-sorted
    df = df.sample(frac=1.0, random_state=config.SEED).reset_index(drop=True)
    return df


def main() -> None:
    df = generate()
    df.to_csv(config.RAW_CSV, index=False)
    print(f"Wrote {len(df):,} rows -> {config.RAW_CSV}")
    print(f"Date span: {config.N_DAYS} days, "
          f"{df['account_id'].nunique()} accounts, "
          f"{df['service'].nunique()} raw service labels")
    print(f"Null costs injected: {df['cost'].isna().sum()}")


if __name__ == "__main__":
    main()
