from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

import pandas as pd
import pyarrow as pa


def _sanitize_for_delta(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    numeric_cols = df.select_dtypes(include=["number", "bool"]).columns.tolist()
    for col in df.columns:
        if col in numeric_cols:
            continue
        series = df[col]
        if pd.api.types.is_categorical_dtype(series.dtype):
            series = series.astype(str)
        if pd.api.types.is_object_dtype(series.dtype):
            if series.apply(lambda x: isinstance(x, (dict, list))).any():
                series = series.apply(lambda x: json.dumps(x, ensure_ascii=False) if x is not None else None)
            else:
                series = series.apply(lambda x: None if pd.isna(x) else str(x))
        if pd.api.types.is_string_dtype(series.dtype) or series.dtype == object:
            series = series.apply(lambda x: None if pd.isna(x) else str(x))
        df[col] = series
    return df


def run(silver_path: str) -> str:
    df = pd.read_parquet(silver_path, engine="pyarrow")

    agg = (
        df.groupby(["state", "brewery_type"])  # group by location and type
        .size()
        .reset_index(name="count")
        .sort_values(["state", "count"], ascending=[True, False])
    )

    run_date = datetime.utcnow().strftime("%Y-%m-%d")
    agg["run_date"] = run_date
    agg = agg[["run_date", "state", "brewery_type", "count"]]

    delta_root = "/opt/airflow/data/gold_delta"
    os.makedirs(os.path.dirname(delta_root), exist_ok=True)

    try:
        from deltalake import write_deltalake

        safe_agg = _sanitize_for_delta(agg)
        mode = "append" if os.path.exists(os.path.join(delta_root, "_delta_log")) else "overwrite"
        try:
            write_deltalake(delta_root, safe_agg, mode=mode, partition_by=["run_date"])
            return delta_root
        except Exception:
            safe_table = pa.Table.from_pandas(safe_agg, preserve_index=False)
            write_deltalake(delta_root, safe_table, mode=mode, partition_by=["run_date"])
            return delta_root
    except Exception as exc:
        import logging

        logging.warning("Delta write failed; continuing without gold write: %s", exc)
        # log data-quality / run metrics
        try:
            from scripts.logging import log_event

            metrics = {
                "agg_rows": int(len(agg)),
                "total_count": int(agg["count"].sum()) if "count" in agg.columns else None,
                "gold_path": delta_root,
            }
            log_event(stage="gold", metrics=metrics)
        except Exception:
            pass
        return delta_root
