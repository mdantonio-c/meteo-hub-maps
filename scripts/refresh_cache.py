#!/usr/bin/env python3
"""Refresh GeoWebCache tiles on demand.

Examples:
  python scripts/refresh_cache.py --dataset radar --variable srt
  python scripts/refresh_cache.py --layer radar-srt --times 2026-09-18T10:00:00Z
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional


BACKEND = Path(__file__).resolve().parents[1] / "projects" / "maps" / "backend"
sys.path.insert(0, str(BACKEND))

from datasets.cache import GWCInvalidator, TemporalCacheLayer  # noqa: E402
from datasets.manifest import load_manifest  # noqa: E402


def _dataset_config(dataset_id: str):
    path = os.environ.get(
        "DATASET_CONFIG_PATH",
        str(BACKEND.parent / "datasets.yml"),
    )
    for dataset in load_manifest(path):
        if dataset.identifier == dataset_id:
            return dataset
    raise SystemExit(f"Dataset not found in manifest: {dataset_id}")


def _resolve_layer(dataset, variable: Optional[str], layer: Optional[str]):
    if layer:
        return layer
    if not variable:
        raise SystemExit("Specify --layer or both --dataset and --variable")
    variable_config = dataset.geoserver.get("variables", {}).get(variable, {})
    layer_name = variable_config.get("layer_name")
    if not layer_name:
        raise SystemExit(f"No layer mapping for variable {variable!r}")
    return str(layer_name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="radar")
    parser.add_argument("--variable")
    parser.add_argument("--layer")
    parser.add_argument("--store")
    parser.add_argument("--times", nargs="+", help="ISO8601 TIME values to refresh")
    parser.add_argument(
        "--no-wait", action="store_true", help="Do not wait for GWC operations to finish"
    )
    args = parser.parse_args()

    dataset = _dataset_config(args.dataset)
    layer = _resolve_layer(dataset, args.variable, args.layer)
    store = args.store or f"mosaic_{layer}"
    cache_config = dataset.geoserver.get("cache", {})
    invalidator = GWCInvalidator(
        os.environ.get("GEOSERVER_URL", "http://localhost:8081/geoserver"),
        os.environ.get("GEOSERVER_ADMIN_USER", "admin"),
        os.environ.get("GEOSERVER_ADMIN_PASSWORD", "D3vMode!"),
        str(dataset.geoserver.get("workspace", "meteohub")),
        enabled=bool(cache_config.get("eligible", True)),
        zoom_start=cache_config.get("zoom_start"),
        zoom_stop=cache_config.get("zoom_stop"),
    )

    if not invalidator.ensure_time_parameter_filter(layer):
        return 1

    if args.times:
        ok = invalidator.truncate(layer, times=args.times)
        if ok:
            ok = invalidator.seed_new_times(
                layer, args.times, store_name=store, wait=not args.no_wait
            )
    else:
        ok = invalidator.refresh_temporal_layer(
            TemporalCacheLayer(layer, store_name=store)
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
