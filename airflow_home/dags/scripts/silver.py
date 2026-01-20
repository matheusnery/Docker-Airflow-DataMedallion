"""Silver script: normalize bronze JSON into a partitioned parquet dataset.

Provides `run(bronze_path) -> str` which returns the dataset root for the run.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

import pandas as pd


def run(bronze_path: str) -> str:
    """Read raw JSON from bronze_path and write partitioned parquet dataset by state.

    Returns the dataset root folder.
    """
    with open(bronze_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    df = pd.DataFrame(data)

    # Ensure columns exist
    for col in ["id", "name", "brewery_type", "city", "state", "website_url"]:
        if col not in df.columns:
            df[col] = None

    # Normalize state: uppercase, strip, fill empty as 'UNKNOWN'
    df["state"] = df["state"].fillna("").astype(str).str.strip().str.upper()
    df.loc[df["state"] == "", "state"] = "UNKNOWN"

    # Select final columns and order
    df = df[["id", "name", "brewery_type", "city", "state", "website_url"]]

    out_dir = "/opt/airflow/data/silver"
    os.makedirs(out_dir, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    dataset_root = os.path.join(out_dir, f"run_{timestamp}")
    os.makedirs(dataset_root, exist_ok=True)

    # write partitioned parquet by state
    df.to_parquet(dataset_root, engine="pyarrow", partition_cols=["state"], index=False)

    # data-quality metrics
    try:
        from scripts.logging import log_event

        row_count = len(df)
        null_counts = df.isnull().sum().to_dict()
        distinct_states = int(df["state"].nunique()) if "state" in df.columns else 0
        cols = df.columns.tolist()
        metrics = {
            "row_count": row_count,
            "distinct_states": distinct_states,
            "null_counts": null_counts,
            "columns": cols,
            "silver_path": dataset_root,
        }
        log_event(stage="silver", metrics=metrics)
    except Exception:
        pass

    return dataset_root
    
