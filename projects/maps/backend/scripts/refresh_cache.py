#!/usr/bin/env python3
"""Refresh GeoWebCache tiles on demand.

Examples:
  python projects/maps/backend/scripts/refresh_cache.py --dataset radar --variable srt
  python projects/maps/backend/scripts/refresh_cache.py --layer radar-srt --times 2026-09-18T10:00:00Z
  python projects/maps/backend/scripts/refresh_cache.py --store radar-sri
"""

import argparse
import importlib.util
import os
import sys
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
        "--no-wait", action="store_true", help="Do not wait for GWC operations to finish"
    )
    args = parser.parse_args()

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
    print(f"Refreshing {invalidator.workspace}:{layer} using coverage store {store}")

    if not invalidator.ensure_time_parameter_filter(layer):
        return 1

    if args.times:
        ok = invalidator.truncate(layer, times=args.times)
        if ok:
            ok = invalidator.seed_new_times(
                layer, args.times, store_name=store, wait=not args.no_wait
            )
    else:
        ok = invalidator.refresh_temporal_layer(cache_layer)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
