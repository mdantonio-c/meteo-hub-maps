from datetime import datetime
from pathlib import Path
import re

from restapi import decorators
from restapi.env import Env
from restapi.exceptions import NotFound
from restapi.rest.definition import EndpointResource, Response

MER_BASE_PATH = Path(Env.get("MER_DATA_PATH", "/MER"))
THREDDS_TARGET_PATH = Path(Env.get("THREDDS_DATA_PATH", "/thredds_ugrid"))
THREDDS_PRODUCTS = {
    ("arpae", "water-level"): {
        "name": "arpae/water-level",
        "source_folder": "water-level-arpae",
    },
    ("dpc", "water-level"): {
        "name": "dpc/water-level",
        "source_folder": "water-level-dpc",
    },
}

_TIMESTAMP_PATTERNS = [
    (re.compile(r"(?<!\d)(\d{12})(?!\d)"), "%Y%m%d%H%M"),
    (re.compile(r"(?<!\d)(\d{10})(?!\d)"), "%Y%m%d%H"),
    (re.compile(r"(?<!\d)(\d{8})(?!\d)"), "%Y%m%d"),
    (re.compile(r"(?<!\d)(\d{2}-\d{2}-\d{4}-\d{2}-\d{2})(?!\d)"), "%d-%m-%Y-%H-%M"),
    (re.compile(r"(?<!\d)(\d{2}-\d{2}-\d{4}-\d{2})(?!\d)"), "%d-%m-%Y-%H"),
]


def _extract_timestamps_from_name(name: str) -> list[str]:
    found: set[str] = set()

    for pattern, format_string in _TIMESTAMP_PATTERNS:
        for match in pattern.findall(name):
            try:
                parsed = datetime.strptime(match, format_string)
                found.add(parsed.strftime("%Y-%m-%dT%H:%M:%SZ"))
            except ValueError:
                continue

    return sorted(found)


def _latest_ingestion_for_layer(layer_dir: Path) -> str | None:
    latest = None
    for marker in layer_dir.rglob("INGESTION.META"):
        try:
            with open(marker, "r", encoding="utf-8") as meta_file:
                for line in meta_file:
                    if line.startswith("IngestedAt:"):
                        value = line.split(":", 1)[1].strip()
                        try:
                            marker_time = datetime.fromisoformat(value)
                        except ValueError:
                            marker_time = datetime.fromtimestamp(marker.stat().st_mtime)
                        if latest is None or marker_time > latest:
                            latest = marker_time
                        break
        except OSError:
            marker_time = datetime.fromtimestamp(marker.stat().st_mtime)
            if latest is None or marker_time > latest:
                latest = marker_time

    if latest is None:
        return None

    return latest.isoformat() + "Z"


def _latest_marker_date(source_dir: Path, suffix: str, expected_len: int = 8) -> str | None:
    latest: str | None = None

    for marker in source_dir.glob(f"*.{suffix}"):
        date_part = marker.name.split(".", 1)[0]
        if len(date_part) != expected_len or not date_part.isdigit():
            continue
        if latest is None or date_part > latest:
            latest = date_part

    return latest


def _parse_ingestion_metadata(meta_file: Path) -> dict[str, str]:
    parsed: dict[str, str] = {}

    if not meta_file.exists():
        return parsed

    try:
        with open(meta_file, "r", encoding="utf-8") as meta_handle:
            for line in meta_handle:
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                parsed[key.strip()] = value.strip()
    except OSError:
        return parsed

    return parsed


def _latest_ingested_files(layer_dir: Path) -> tuple[list[str], str | None]:
    ingestion_meta = _parse_ingestion_metadata(layer_dir / "INGESTION.META")
    copied_file = ingestion_meta.get("CopiedFile")
    ingested_at = ingestion_meta.get("IngestedAt")

    if copied_file:
        return [copied_file], ingested_at

    netcdf_files = [f for f in layer_dir.glob("*.nc") if f.is_file()]
    if not netcdf_files:
        return [], ingested_at

    netcdf_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    latest_file = netcdf_files[0]

    if ingested_at is None:
        ingested_at = datetime.fromtimestamp(latest_file.stat().st_mtime).isoformat()

    return [latest_file.name], ingested_at


def _thredds_product_payload(provider: str, product: str) -> dict:
    product_key = (provider, product)
    product_config = THREDDS_PRODUCTS.get(product_key)
    if product_config is None:
        raise NotFound(f"Unsupported THREDDS product {provider}/{product}")

    source_dir = MER_BASE_PATH / product_config["source_folder"]
    target_dir = THREDDS_TARGET_PATH / "MER" / product_config["source_folder"]

    source_ready = _latest_marker_date(source_dir, "READY")
    thredds_ready = _latest_marker_date(source_dir, "THREDDS.READY")

    latest_files: list[str] = []
    ingested_at = None
    if target_dir.exists() and target_dir.is_dir():
        latest_files, ingested_at = _latest_ingested_files(target_dir)

    status = None
    if thredds_ready is not None and (source_ready is None or thredds_ready >= source_ready):
        status = "ingested"
    elif source_ready is not None:
        status = "ingesting"

    return {
        "product": product_config["name"],
        "sourcePath": str(source_dir),
        "threddsPath": str(target_dir),
        "ingestion": {
            "status": status,
            "lastSourceReady": source_ready,
            "lastThreddsReady": thredds_ready,
            "lastIngestedAt": ingested_at,
            "latestIngestedFiles": latest_files,
        },
    }


def _layer_status(layer_dir: Path) -> dict:
    timestamps: set[str] = set()
    files = 0

    for file_path in layer_dir.rglob("*"):
        if not file_path.is_file():
            continue

        if file_path.name.endswith(".META"):
            continue

        files += 1
        timestamps.update(_extract_timestamps_from_name(file_path.name))

    return {
        "layer": layer_dir.name,
        "ingestionDate": _latest_ingestion_for_layer(layer_dir),
        "timestamps": sorted(timestamps),
        "files": files,
    }


class ThreddsLayersStatusEndpoint(EndpointResource):
    labels = ["thredds"]

    @decorators.endpoint(
        path="/thredds/status",
        summary="Get available THREDDS layers and timestamps",
        responses={
            200: "THREDDS layers status",
            404: "THREDDS data path not found",
        },
    )
    def get(self) -> Response:
        if not THREDDS_TARGET_PATH.exists():
            raise NotFound(f"THREDDS data path {THREDDS_TARGET_PATH} does not exist")

        layers = []
        for layer_dir in sorted(THREDDS_TARGET_PATH.iterdir()):
            if not layer_dir.is_dir():
                continue
            if layer_dir.name.startswith("."):
                continue
            layers.append(_layer_status(layer_dir))

        return self.response(
            {
                "root": str(THREDDS_TARGET_PATH),
                "layers": layers,
            }
        )


class ThreddsLayerStatusEndpoint(EndpointResource):
    labels = ["thredds"]

    @decorators.endpoint(
        path="/thredds/status/<layer>",
        summary="Get status and available timestamps for one THREDDS layer",
        responses={
            200: "THREDDS layer status",
            404: "THREDDS layer not found",
        },
    )
    def get(self, layer: str) -> Response:
        if not THREDDS_TARGET_PATH.exists():
            raise NotFound(f"THREDDS data path {THREDDS_TARGET_PATH} does not exist")

        layer_dir = THREDDS_TARGET_PATH / layer
        if not layer_dir.exists() or not layer_dir.is_dir():
            raise NotFound(f"THREDDS layer {layer} not found")

        return self.response(_layer_status(layer_dir))


class ThreddsLatestProductsEndpoint(EndpointResource):
    labels = ["thredds"]

    @decorators.endpoint(
        path="/thredds/latest",
        summary="Get latest THREDDS ingested files for supported MER products",
        responses={
            200: "Latest THREDDS ingestion status per product",
        },
    )
    def get(self) -> Response:
        products = [
            _thredds_product_payload(provider, product)
            for provider, product in sorted(THREDDS_PRODUCTS.keys())
        ]

        return self.response({"products": products})


class ThreddsLatestProductEndpoint(EndpointResource):
    labels = ["thredds"]

    @decorators.endpoint(
        path="/thredds/<provider>/<product>/latest",
        summary="Get latest THREDDS ingested files for a specific MER product",
        responses={
            200: "Latest THREDDS ingestion status",
            404: "Unsupported THREDDS product",
        },
    )
    def get(self, provider: str, product: str) -> Response:
        return self.response(_thredds_product_payload(provider, product))
