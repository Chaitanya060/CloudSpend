"""AWS Lambda handler — event-driven ETL (weight-adder layer).

Deployment pattern (matches the JD's "event-driven, auto-scaling" line):

    Raw billing CSV uploaded to S3  ->  S3 ObjectCreated event  ->  this Lambda
    ->  runs the same clean/aggregate logic  ->  writes to RDS (MySQL).

This is a reference implementation showing the wiring. It reuses the exact
transform logic from src/etl.py so local and cloud paths stay in sync. To run
it for real you'd package src/ with the function and set the MYSQL_* env vars
(pointing at your RDS instance) plus CLOUDSPEND_DB=mysql.
"""
from __future__ import annotations

import io
import os
import urllib.parse

import boto3  # provided by the Lambda runtime
import pandas as pd

# When packaged with the project, these imports resolve against src/.
from src import etl, db

s3 = boto3.client("s3")


def lambda_handler(event, context):
    # 1. Parse the S3 event
    record = event["Records"][0]
    bucket = record["s3"]["bucket"]["name"]
    key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
    print(f"Triggered by s3://{bucket}/{key}")

    # 2. Download the object into memory
    obj = s3.get_object(Bucket=bucket, Key=key)
    raw = pd.read_csv(io.BytesIO(obj["Body"].read()))

    # 3. Transform with the SAME logic used locally
    daily = etl.transform(raw)

    # 4. Load into RDS (CLOUDSPEND_DB=mysql + MYSQL_* env vars point at RDS)
    etl.load(daily)

    return {
        "statusCode": 200,
        "body": f"Processed {len(raw)} rows -> {len(daily)} daily aggregates "
                f"from s3://{bucket}/{key}",
    }
