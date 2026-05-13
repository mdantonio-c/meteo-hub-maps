from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import re
import xml.etree.ElementTree as ET

import requests

from restapi.connectors import celery
from restapi.connectors.celery import CeleryExt
from restapi.env import Env
from restapi.utilities.logs import log

from maps.tasks.mer_wms_bboxes import BBOXES_BY_ZOOM

MER_BASE_PATH = Path(Env.get("MER_DATA_PATH", "/MER"))
THREDDS_TARGET_PATH = Path(Env.get("THREDDS_DATA_PATH", "/thredds_ugrid"))
MER_WATER_LEVEL_FOLDERS = ("water-level-arpae", "water-level-dpc")
READY_FILE_PATTERN = re.compile(r"^(\d{8})\.READY$")
THREDDS_READY_FILE_PATTERN = re.compile(r"^(\d{8})\.THREDDS\.READY$")

MER_WMS_BASE_URL = Env.get("MER_WMS_BASE_URL", "https://meteohub-maps.hpc.cineca.it/thredds/wms/mer")
MER_WMS_LAYER = Env.get("MER_WMS_LAYER", "water_level")
MER_WMS_STYLE = Env.get("MER_WMS_STYLE", "raster/x-Sst")
MER_WMS_NUM_COLOR_BANDS = Env.get("MER_WMS_NUM_COLOR_BANDS", "20")
MER_WMS_ABOVE_MAX_COLOR = Env.get("MER_WMS_ABOVE_MAX_COLOR", "extend")
MER_WMS_BELOW_MIN_COLOR = Env.get("MER_WMS_BELOW_MIN_COLOR", "extend")
MER_WMS_FILENAME_TEMPLATE = Env.get("MER_WMS_FILENAME_TEMPLATE", "{date}.nc")
MER_WMS_COLOR_SCALE_RANGE = Env.get("MER_WMS_COLOR_SCALE_RANGE", "-1.23,1.94")
MER_WMS_COLOR_SCALE_RANGE_ARPAE = Env.get("MER_WMS_COLOR_SCALE_RANGE_ARPAE", MER_WMS_COLOR_SCALE_RANGE)
MER_WMS_COLOR_SCALE_RANGE_DPC = Env.get("MER_WMS_COLOR_SCALE_RANGE_DPC", MER_WMS_COLOR_SCALE_RANGE)
MER_WMS_TIME_OFFSETS_HOURS = Env.get("MER_WMS_TIME_OFFSETS_HOURS", "-24")
MER_WMS_REQUEST_TIMEOUT_SECONDS = float(Env.get("MER_WMS_REQUEST_TIMEOUT_SECONDS", 20.0))
MER_WMS_CACHE_THREADS = int(Env.get("MER_WMS_CACHE_THREADS", 4))
# Zoom levels for which every available time step in the NC file is requested.
MER_WMS_ALL_TIMES_ZOOM_LEVELS = Env.get("MER_WMS_ALL_TIMES_ZOOM_LEVELS", "5,6")
MANDATORY_ALL_TIMES_ZOOM_LEVELS = frozenset({5, 6})


def _parse_time_offsets_hours() -> list[int]:
    offsets: list[int] = []
    for part in MER_WMS_TIME_OFFSETS_HOURS.split(","):
        value = part.strip()
        if not value:
            continue
        try:
            offsets.append(int(value))
        except ValueError:
            log.warning(f"Invalid MER_WMS_TIME_OFFSETS_HOURS token skipped: {value}")
    return offsets or [0]


def _build_time_list_from_ingested_date(date_str: str) -> list[str]:
    base_time = datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=timezone.utc)
    times: set[str] = set()
    for hour_offset in _parse_time_offsets_hours():
        timestamp = base_time + timedelta(hours=hour_offset)
        times.add(timestamp.strftime("%Y-%m-%dT%H:%M:%S.000Z"))
    return sorted(times)


def _parse_all_times_zoom_levels() -> frozenset[int]:
    levels: set[int] = set()
    for part in MER_WMS_ALL_TIMES_ZOOM_LEVELS.split(","):
        value = part.strip()
        if not value:
            continue
        try:
            levels.add(int(value))
        except ValueError:
            log.warning(f"Invalid MER_WMS_ALL_TIMES_ZOOM_LEVELS token skipped: {value}")
    # Always force zoom levels 5 and 6 to run against every available time step.
    return frozenset(levels).union(MANDATORY_ALL_TIMES_ZOOM_LEVELS)


def _get_wms_available_times(wms_base_url: str) -> list[str]:
    """Query WMS GetCapabilities and return all time values for the layer."""
    params = {"service": "WMS", "version": "1.1.1", "request": "GetCapabilities"}
    try:
        response = requests.get(wms_base_url, params=params, timeout=MER_WMS_REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException as exc:
        log.warning(f"GetCapabilities request failed for {wms_base_url}: {exc}")
        return []

    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as exc:
        log.warning(f"Failed to parse GetCapabilities XML from {wms_base_url}: {exc}")
        return []

    # WMS 1.1.1: <Layer><Dimension name="time">val1,val2,...</Dimension></Layer>
    # Namespaces vary; search broadly.
    times: list[str] = []
    for dim in root.iter():
        local = dim.tag.split("}")[-1] if "}" in dim.tag else dim.tag
        if local == "Dimension" and dim.get("name", "").lower() == "time" and dim.text:
            times = [t.strip() for t in dim.text.split(",") if t.strip()]
            break

    if not times:
        log.warning(f"No time dimension found in GetCapabilities response from {wms_base_url}")
    else:
        log.info(f"GetCapabilities returned {len(times)} time steps from {wms_base_url}")
    return times


def _color_scale_range_for_product(source_folder: str) -> str:
    if source_folder == "water-level-arpae":
        return MER_WMS_COLOR_SCALE_RANGE_ARPAE
    if source_folder == "water-level-dpc":
        return MER_WMS_COLOR_SCALE_RANGE_DPC
    return MER_WMS_COLOR_SCALE_RANGE


def _extract_wms_error_message(response: requests.Response) -> str | None:
    """Extract WMS/OGC exception text from a GetMap response payload."""
    content_type = response.headers.get("Content-Type", "").lower()
    body_preview = response.text[:1200].strip()
    is_text_payload = "xml" in content_type or "text" in content_type or body_preview.startswith("<")
    if not is_text_payload:
        return None

    try:
        root = ET.fromstring(response.content)
    except ET.ParseError:
        # Some WMS servers may return plain text errors with HTTP 200.
        lowered = body_preview.lower()
        if "serviceexception" in lowered or "exception" in lowered or "error" in lowered:
            return body_preview[:400]
        return None

    messages: list[str] = []
    for elem in root.iter():
        local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if local in {"ServiceException", "ExceptionText", "Exception"} and elem.text:
            text = elem.text.strip()
            if text:
                messages.append(text)

    if messages:
        return " | ".join(messages[:3])

    root_local = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    if root_local in {"ServiceExceptionReport", "ExceptionReport"}:
        return body_preview[:400] or "WMS returned an exception report"

    return None


def _populate_mer_cache(
    source_folder: str,
    filename: str,
    dates: list[str],
    date_str: str,
) -> None:
    if not dates:
        log.warning(f"No dates provided for MER cache population ({source_folder})")
        return

    color_scale_range = _color_scale_range_for_product(source_folder)
    getmap_url = f"{MER_WMS_BASE_URL.rstrip('/')}/{source_folder}/{filename}"
    getcap_url = f"{MER_WMS_BASE_URL.rstrip('/')}/{source_folder}"
    bboxes_by_zoom: dict[int, list[tuple[float, float, float, float]]] = {
        z: b for z, b in BBOXES_BY_ZOOM.items() if z in {5, 6}
    }

    # Always use 72 hourly steps for zooms 5, 6
    def generate_72_hourly_steps(base_date: str) -> list[str]:
        base_time = datetime.strptime(base_date, "%Y%m%d").replace(tzinfo=timezone.utc)
        return [
            (base_time + timedelta(hours=step)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            for step in range(72)
        ]

    work_items: list[tuple[int, str, str]] = []
    for zoom, bboxes in sorted(bboxes_by_zoom.items()):
        # Use the original date_str (YYYYMMDD) for generating 72h steps
        zoom_dates = generate_72_hourly_steps(date_str) if dates else []
        log.info(
            f"MER cache population {source_folder}: zoom={zoom} tiles={len(bboxes)} "
            f"time_steps={len(zoom_dates)} (forced 72h)"
        )
        for date_value in zoom_dates:
            for min_x, min_y, max_x, max_y in bboxes:
                work_items.append((zoom, date_value, f"{min_x},{min_y},{max_x},{max_y}"))

    def _fetch(item: tuple[int, str, str]) -> tuple[int, str, str, Exception | None]:
        zoom, date_value, bbox = item
        params = {
            "service": "WMS",
            "request": "GetMap",
            "layers": MER_WMS_LAYER,
            "styles": MER_WMS_STYLE,
            "format": "image/png",
            "transparent": "true",
            "version": "1.1.1",
            "COLORSCALERANGE": color_scale_range,
            "NUMCOLORBANDS": MER_WMS_NUM_COLOR_BANDS,
            "ABOVEMAXCOLOR": MER_WMS_ABOVE_MAX_COLOR,
            "BELOWMINCOLOR": MER_WMS_BELOW_MIN_COLOR,
            "time": date_value,
            "width": "256",
            "height": "256",
            "srs": "EPSG:3857",
            "bbox": bbox,
        }
        log.info(
            f"MER cache request {source_folder} zoom={zoom} date={date_value} "
            f"bbox={bbox} url={getmap_url} params={params}"
        )
        try:
            response = requests.get(getmap_url, params=params, timeout=MER_WMS_REQUEST_TIMEOUT_SECONDS)
            # content_type = response.headers.get("Content-Type", "")
            # response_preview = response.text[:400].replace("\n", " ").strip() if "image" not in content_type.lower() else "<binary image payload>"
            # log.info(
            #     f"MER cache response {source_folder} zoom={zoom} date={date_value} "
            #     f"bbox={bbox} status={response.status_code} content_type={content_type} "
            #     f"url={response.url} body_preview={response_preview}"
            # )
            response.raise_for_status()
            wms_error = _extract_wms_error_message(response)
            if wms_error is not None:
                return zoom, date_value, bbox, RuntimeError(
                    f"WMS error response with HTTP {response.status_code}: {wms_error}"
                )
            return zoom, date_value, bbox, None
        except requests.RequestException as exc:
            return zoom, date_value, bbox, exc

    failed_tiles = 0
    with ThreadPoolExecutor(max_workers=MER_WMS_CACHE_THREADS) as pool:
        futures = {pool.submit(_fetch, item): item for item in work_items}
        for future in as_completed(futures):
            zoom, date_value, bbox, exc = future.result()
            if exc is not None:
                failed_tiles += 1
                log.warning(
                    f"MER cache request failed for {source_folder} zoom={zoom} "
                    f"date={date_value} bbox={bbox}: {exc}"
                )

    log.info(
        f"MER cache population finished for {source_folder}: "
        f"dates={len(dates)} zoom_levels={len(bboxes_by_zoom)} "
        f"total_requests={len(work_items)} failures={failed_tiles}"
    )


def _source_mer_directories(root: Path) -> list[Path]:
    directories = []
    for folder in MER_WATER_LEVEL_FOLDERS:
        source_dir = root / folder
        if source_dir.exists() and source_dir.is_dir():
            directories.append(source_dir)
        else:
            log.info(f"MER source folder not found, skipping: {source_dir}")
    return directories


def _latest_source_ready_date(source_dir: Path) -> str | None:
    files_dir = source_dir / "files"
    if not files_dir.exists() or not files_dir.is_dir():
        log.info(f"No files/ subdirectory found in {source_dir}, skipping")
        return None
    latest_date: str | None = None

    for ready_file in source_dir.glob("*.READY"):
        match = READY_FILE_PATTERN.match(ready_file.name)
        if not match:
            continue

        date_str = match.group(1)
        nc_file = files_dir / f"{date_str}.nc"
        if not nc_file.exists():
            continue

        if latest_date is None or date_str > latest_date:
            latest_date = date_str

    return latest_date


def _latest_thredds_ready_date(source_dir: Path) -> str | None:
    latest_date: str | None = None

    for marker in source_dir.glob("*.THREDDS.READY"):
        match = THREDDS_READY_FILE_PATTERN.match(marker.name)
        if not match:
            continue

        date_str = match.group(1)
        if latest_date is None or date_str > latest_date:
            latest_date = date_str

    return latest_date

def _copy_netcdf_file(source_file: Path, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / source_file.name
    shutil.copy2(source_file, target_file)
    return target_file


def _cleanup_old_netcdf_files(target_dir: Path, keep_file_name: str) -> int:
    deleted = 0
    for existing in target_dir.glob("*.nc"):
        if existing.name == keep_file_name:
            continue
        existing.unlink(missing_ok=True)
        deleted += 1
    return deleted


def _ingestion_metadata(layer_target_dir: Path, source_relative_dir: str, copied_file: str, deleted_files: int) -> None:
    marker = layer_target_dir / "INGESTION.META"
    with open(marker, "w", encoding="utf-8") as meta:
        meta.write(f"IngestedAt: {datetime.now().isoformat()}\n")
        meta.write(f"Source: {source_relative_dir}\n")
        meta.write(f"CopiedFile: {copied_file}\n")
        meta.write(f"DeletedFiles: {deleted_files}\n")


@CeleryExt.task(idempotent=True)
def check_latest_data_and_trigger_thredds_ingestion(
    self,
    MER_path: str = str(MER_BASE_PATH),
) -> None:
    MER_root = Path(MER_path)
    if not MER_root.exists():
        log.warning(f"MER path does not exist: {MER_root}")
        return

    c = celery.get_instance()
    for source_dir in _source_mer_directories(MER_root):
        latest_ready_date = _latest_source_ready_date(source_dir)
        if latest_ready_date is None:
            log.info(
                f"No valid YYYYMMDD.READY (in {source_dir}) + YYYYMMDD.nc "
                f"(in {source_dir / 'files'}) pair found"
            )
            continue

        latest_thredds_ready_date = _latest_thredds_ready_date(source_dir)
        if latest_thredds_ready_date is not None and latest_ready_date <= latest_thredds_ready_date:
            log.info(
                f"Skipping ingestion for {source_dir}: source date {latest_ready_date} "
                f"is not newer than THREDDS marker {latest_thredds_ready_date}"
            )
            continue

        c.celery_app.send_task(
            "ingest_MER_ready_directory",
            args=(str(source_dir), latest_ready_date),
        )
        log.info(f"Triggered THREDDS ingestion for {source_dir} ({latest_ready_date})")


@CeleryExt.task(idempotent=True)
def ingest_MER_ready_directory(self, source_or_ready_path: str, date_str: str | None = None) -> None:
    source_path = Path(source_or_ready_path)

    if date_str is None:
        ready_match = READY_FILE_PATTERN.match(source_path.name)
        if source_path.is_file() and ready_match:
            source_dir = source_path.parent
            files_dir = source_dir / "files"
            date_str = ready_match.group(1)
        else:
            log.warning(
                f"Cannot infer date from legacy task argument {source_path}. "
                "Expected a YYYYMMDD.READY file path in the source directory."
            )
            return
    else:
        source_dir = source_path
        files_dir = source_dir / "files"

    if not files_dir.exists() or not files_dir.is_dir():
        log.warning(f"Files directory does not exist: {files_dir}")
        return

    ready_file = source_dir / f"{date_str}.READY"
    source_nc_file = files_dir / f"{date_str}.nc"
    thredds_ready_file = source_dir / f"{date_str}.THREDDS.READY"

    if not ready_file.exists():
        log.warning(f"READY file does not exist: {ready_file}")
        return

    if not source_nc_file.exists():
        log.warning(f"NetCDF file does not exist: {source_nc_file}")
        return

    try:
        source_relative_dir = str(source_dir.relative_to(MER_BASE_PATH.parent))
    except ValueError:
        log.warning(f"{source_dir} is not within {MER_BASE_PATH.parent}, skipping")
        return

    target_dir = THREDDS_TARGET_PATH / source_relative_dir
    copied_file = _copy_netcdf_file(source_nc_file, target_dir)
    deleted_files = _cleanup_old_netcdf_files(target_dir, copied_file.name)
    _ingestion_metadata(target_dir, source_relative_dir, copied_file.name, deleted_files)

    with open(thredds_ready_file, "w", encoding="utf-8") as marker:
        marker.write(f"Ingested by THREDDS task at {datetime.now().isoformat()}\n")
        marker.write(f"Source READY: {ready_file.name}\n")
        marker.write(f"Source netCDF: {source_nc_file.name}\n")
        marker.write(f"Target: {target_dir}\n")
        marker.write(f"Copied file: {copied_file.name}\n")
        marker.write(f"Deleted old netCDF files: {deleted_files}\n")

    log.info(f"Created {thredds_ready_file}")

    # Trigger cache population for the product that was just ingested.
    c = celery.get_instance()
    if source_dir.name == "water-level-arpae":
        c.celery_app.send_task("populate_mer_cache_after_arpae_ingestion", args=(date_str,))
    elif source_dir.name == "water-level-dpc":
        c.celery_app.send_task("populate_mer_cache_after_dpc_ingestion", args=(date_str,))


@CeleryExt.task(idempotent=True)
def populate_mer_cache_after_arpae_ingestion(self, date_str: str) -> None:
    dates = _build_time_list_from_ingested_date(date_str)
    filename = MER_WMS_FILENAME_TEMPLATE.format(date=date_str, source="water-level-arpae")
    _populate_mer_cache("water-level-arpae", filename, dates, date_str)


@CeleryExt.task(idempotent=True)
def populate_mer_cache_after_dpc_ingestion(self, date_str: str) -> None:
    dates = _build_time_list_from_ingested_date(date_str)
    filename = MER_WMS_FILENAME_TEMPLATE.format(date=date_str, source="water-level-dpc")
    _populate_mer_cache("water-level-dpc", filename, dates, date_str)
