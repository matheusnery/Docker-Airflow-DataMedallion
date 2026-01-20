"""Bronze script: fetch raw data from OpenBreweryDB and save JSON.

This module contains a single function `run` that mirrors the previous in-DAG
logic: it fetches pages from the API, resilient to endpoint path changes,
and writes a timestamped JSON file under /opt/airflow/data/bronze.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import List, Dict, Any

import requests


def _fetch_page(base_url: str, page: int, per_page: int) -> List[Dict[str, Any]]:
    params = {"page": page, "per_page": per_page}
    resp = requests.get(base_url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def run(per_page: int = 50, max_pages: int = 5) -> str:
    """Fetch breweries pages and write raw JSON to bronze folder.

    Returns the path to the saved JSON file.
    """
    # prefer the v1 path, fallback to /breweries
    endpoints = [
        "https://api.openbrewerydb.org/v1/breweries",
        "https://api.openbrewerydb.org/breweries",
    ]

    items: List[Dict[str, Any]] = []
    base_url = None
    last_exc = None
    for ep in endpoints:
        try:
            # try a quick HEAD/GET for page=1
            _ = requests.get(ep, params={"page": 1, "per_page": 1}, timeout=10)
            base_url = ep
            break
        except Exception as exc:
            last_exc = exc

    if base_url is None:
        raise RuntimeError(f"Could not determine OpenBreweryDB endpoint: {last_exc}")

    for page in range(1, max_pages + 1):
        try:
            page_items = _fetch_page(base_url, page, per_page)
            if not page_items:
                break
            items.extend(page_items)
        except Exception:
            # stop fetching further pages on error
            break

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out_dir = "/opt/airflow/data/bronze"
    os.makedirs(out_dir, exist_ok=True)
    filename = f"bronze_breweries_{timestamp}.json"
    out_path = os.path.join(out_dir, filename)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False, indent=2)

    # collect simple data-quality metrics
    try:
        from scripts.logging import log_event

        item_count = len(items)
        pages_fetched = 0 if item_count == 0 else ((item_count - 1) // per_page) + 1
        # detect missing fields across items
        expected = {"id", "name", "brewery_type", "city", "state", "website_url"}
        missing_counts = {}
        for it in items:
            for f in expected:
                if f not in it or it.get(f) is None:
                    missing_counts[f] = missing_counts.get(f, 0) + 1

        metrics = {
            "item_count": item_count,
            "pages_fetched": pages_fetched,
            "missing_counts": missing_counts,
            "bronze_path": out_path,
        }
        log_event(stage="bronze", metrics=metrics)
    except Exception:
        # logging must not fail the pipeline; swallow errors
        pass

    return out_path
