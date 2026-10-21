#!/usr/bin/env python3
"""Refresh GeoWebCache tiles on demand.

Examples:
  python projects/maps/backend/scripts/refresh_cache.py --dataset radar --variable srt
  python projects/maps/backend/scripts/refresh_cache.py --layer radar-srt --times 2026-09-18T10:00:00Z
  python projects/maps/backend/scripts/refresh_cache.py --store radar-sri
  python projects/maps/backend/scripts/refresh_cache.py --dataset radar --variable sri --parallelism 4
"""

import argparse
import importlib.util
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote, unquote, urlparse

import requests


BACKEND = Path(__file__).resolve().parents[1]
PROJECT = BACKEND.parent
# RAPyDo mounts backend/ as the `maps` package inside its containers.
package = importlib.util.spec_from_file_location(
    "maps", BACKEND / "__init__.py", submodule_search_locations=[str(BACKEND)]
)
assert package is not None and package.loader is not None
maps = importlib.util.module_from_spec(package)
sys.modules["maps"] = maps
package.loader.exec_module(maps)

from maps.datasets.cache import GWCInvalidator, TemporalCacheLayer  # noqa: E402
from maps.datasets.manifest import load_manifest  # noqa: E402


def _progress(message: str) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    print(f"[{timestamp}] {message}", flush=True)


def _dataset_config(dataset_id: str):
    path = os.environ.get(
        "DATASET_CONFIG_PATH",
        str(PROJECT / "datasets.yml"),
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


def _geoserver_json(invalidator, path: str, allow_missing: bool = False):
    response = requests.get(
        f"{invalidator.base_url}/rest/{path}",
        auth=(invalidator.username, invalidator.password),
        timeout=invalidator.timeout,
    )
    if allow_missing and response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def _resolve_cache_layer(invalidator, layer: Optional[str], store: Optional[str]):
    """Resolve actual coverage-store names from GeoServer, not naming conventions."""
    workspace = quote(invalidator.workspace, safe="")
    if not layer:
        # Accept an actual store, or a published layer name as a convenience.
        document = _geoserver_json(
            invalidator,
            f"workspaces/{workspace}/coveragestores/{quote(store, safe='')}/coverages.json",
            allow_missing=True,
        )
        if document is not None:
            coverages = document.get("coverages", {}).get("coverage", [])
            if len(coverages) != 1:
                raise ValueError(
                    f"Store {store!r} has {len(coverages)} coverages; specify --layer"
                )
            return TemporalCacheLayer(coverages[0]["name"], store_name=store)
        layer, store = store, None

    document = _geoserver_json(
        invalidator, f"layers/{workspace}:{quote(layer, safe='')}.json"
    )
    resource = document.get("layer", {}).get("resource", {})
    parts = urlparse(resource.get("href", "")).path.split("/")
    if "coveragestores" not in parts:
        raise ValueError(f"Layer {layer!r} is not backed by a coverage store")
    actual_store = unquote(parts[parts.index("coveragestores") + 1])
    if store and store != actual_store:
        raise ValueError(
            f"Layer {layer!r} belongs to store {actual_store!r}, not {store!r}"
        )
    return TemporalCacheLayer(layer, store_name=actual_store)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="radar")
    parser.add_argument("--variable")
    parser.add_argument("--layer")
    parser.add_argument("--store", help="Coverage store (or layer name when used alone)")
    parser.add_argument("--times", nargs="+", help="ISO8601 TIME values to refresh")
    parser.add_argument(
        "--parallelism",
        type=int,
        default=4,
        help="Maximum parallel timestep seed jobs (default: 4)",
    )
    parser.add_argument(
        "--no-wait", action="store_true", help="Do not wait for the final seed batch"
    )
    args = parser.parse_args()
    if args.parallelism < 1:
        parser.error("--parallelism must be at least 1")

    dataset = _dataset_config(args.dataset)
    layer = (
        _resolve_layer(dataset, args.variable, args.layer)
        if args.layer or args.variable or not args.store
        else None
    )
    cache_config = dataset.geoserver.get("cache", {})
    invalidator = GWCInvalidator(
        os.environ.get("GEOSERVER_URL", "http://geoserver.dockerized.io:8080/geoserver"),
        os.environ.get("GEOSERVER_ADMIN_USER", "admin"),
        os.environ.get("GEOSERVER_ADMIN_PASSWORD", "D3vMode!"),
        str(dataset.geoserver.get("workspace", "meteohub")),
        enabled=bool(cache_config.get("eligible", True)),
        zoom_start=cache_config.get("zoom_start"),
        zoom_stop=cache_config.get("zoom_stop"),
    )

    try:
        cache_layer = _resolve_cache_layer(invalidator, layer, args.store)
    except (requests.RequestException, ValueError, KeyError) as exc:
        print(f"Cannot resolve GeoServer layer/store: {exc}", file=sys.stderr)
        return 1
    layer, store = cache_layer.name, cache_layer.store_name
    _progress(
        f"Refreshing {invalidator.workspace}:{layer} using coverage store {store}"
    )
    _progress(
        f"Zoom range: {invalidator.zoom_start}–{invalidator.zoom_stop}; "
        f"server cache expiry: {invalidator._cache_expiry_seconds(layer)} seconds; "
        f"seed parallelism: {args.parallelism}"
    )

    _progress("Cancelling existing seed jobs and waiting for the layer queue to drain")
    if not invalidator.cancel_seed_tasks(layer):
        _progress("ERROR: could not cancel existing seed jobs")
        return 1
    if not invalidator._wait_for_seed_completion(layer):
        _progress("ERROR: layer queue did not drain")
        return 1
    _progress("Checking GWC TIME filter, gridset and expiry configuration")
    if not invalidator.ensure_time_parameter_filter(layer):
        _progress("ERROR: could not configure GWC layer")
        return 1

    _progress("Resolving timestep list")
    times = args.times or invalidator.get_granule_times(
        layer, store_name=store, all_times=True
    )
    if not times:
        print(f"No granule times found for {layer}", file=sys.stderr)
        return 1
    style_name = invalidator.get_default_style(layer)
    if not style_name:
        print(f"Cannot resolve default style for {layer}", file=sys.stderr)
        return 1
    _progress(
        f"Found {len(times)} timestep(s), from {times[0]} to {times[-1]}; style={style_name}"
    )
    _progress(
        f"Truncating {len(times)} timestep(s); waiting for each truncate to complete"
    )
    for index, time_value in enumerate(times, start=1):
        _progress(f"Truncate {index}/{len(times)}: {time_value}")
        if not invalidator.truncate(layer, times=[time_value], style_name=style_name):
            _progress(f"ERROR: cache truncation failed for {time_value}")
            return 1
    _progress("Truncation complete; starting parallel seed batches")
    batch_count = (len(times) + args.parallelism - 1) // args.parallelism
    for offset in range(0, len(times), args.parallelism):
        batch = times[offset : offset + args.parallelism]
        number = offset // args.parallelism + 1
        wait = not args.no_wait or number < batch_count
        _progress(
            f"Seed batch {number}/{batch_count}: submitting {len(batch)} job(s) "
            f"({', '.join(batch)}); "
            + ("waiting for completion" if wait else "leaving final batch running")
        )
        ok = invalidator.seed(
            layer,
            times=batch,
            style_name=style_name,
            wait=wait,
            parallelism=args.parallelism,
        )
        if not ok:
            _progress(f"ERROR: seed batch {number}/{batch_count} failed")
            return 1
        _progress(
            f"Seed batch {number}/{batch_count} "
            + (
                f"complete ({offset + len(batch)}/{len(times)} timesteps)"
                if wait
                else "accepted"
            )
        )
    _progress(
        "Refresh complete"
        if not args.no_wait
        else "Refresh submitted; final seed batch may still be running"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
