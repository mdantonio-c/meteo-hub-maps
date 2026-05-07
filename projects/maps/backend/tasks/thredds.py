from datetime import datetime
from pathlib import Path
import shutil
import re

from restapi.connectors import celery
from restapi.connectors.celery import CeleryExt
from restapi.env import Env
from restapi.utilities.logs import log

MER_BASE_PATH = Path(Env.get("MER_DATA_PATH", "/MER"))
THREDDS_TARGET_PATH = Path(Env.get("THREDDS_DATA_PATH", "/thredds_ugrid"))
MER_WATER_LEVEL_FOLDERS = ("water-level-arpae", "water-level-dpc")
READY_FILE_PATTERN = re.compile(r"^(\d{8})\.READY$")
THREDDS_READY_FILE_PATTERN = re.compile(r"^(\d{8})\.THREDDS\.READY$")


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
