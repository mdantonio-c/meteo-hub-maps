"""Marine forcing discovery and publication."""

import os
import re
import shutil
from datetime import datetime

import requests
from maps.datasets.geoserver_utils import (
    associate_sld_with_layer_generic,
    check_style_exists,
    create_workspace_generic,
    publish_layer_generic,
    upload_geotiff_generic,
    upload_sld_generic,
)
from maps.tasks.cache_control import schedule_cache_refresh_chord
from maps.utils.geoserver import GEOSERVER_REQUEST_TIMEOUT
from restapi.connectors import celery
from restapi.env import Env
from restapi.utilities.logs import log

from .watcher import mark_ingestion_unhealthy, read_retry_count

GEOSERVER_URL = "http://geoserver.dockerized.io:8080/geoserver"  # TODO: get from env
USERNAME = Env.get("GEOSERVER_ADMIN_USER", None)
PASSWORD = Env.get("GEOSERVER_ADMIN_PASSWORD", None)
MER_BASE_PATH = Env.get("MER_DATA_PATH", "/shyfem")
MER_FORCINGS = [
    forcing.strip().upper()
    for forcing in Env.get("MER_FORCINGS", "BOLAM,ECMWF,ICON").split(",")
    if forcing.strip()
]
GEOSERVER_WORKSPACE = "meteohub"
GEOSERVER_COPIES_BASE_DIRECTORY = "/geoserver_data/copies"
MER_WL_STYLE_NAME = "water_level"
MER_WL_STYLE_CANDIDATE_PATHS = [
    "/SLDs/MER/water_level.sld",
    "/projects/maps/builds/geoserver/SLDs/MER/water_level.sld",
]


def _create_mer_mosaic_config(target_dir: str) -> None:
    indexer_content = (
        "PropertyCollectors=TimestampFileNameExtractorSPI[timeregex](time)\n"
        "TimeAttribute=time\n"
        "Schema=*the_geom:Polygon,location:String,time:java.util.Date\n"
    )
    # Matches filenames like 20240107T010000.tif
    timeregex_content = "regex=([0-9]{8}T[0-9]{6}),format=yyyyMMdd'T'HHmmss\n"

    with open(os.path.join(target_dir, "indexer.properties"), "w") as f:
        f.write(indexer_content)

    with open(os.path.join(target_dir, "timeregex.properties"), "w") as f:
        f.write(timeregex_content)


def _enable_mer_time_dimension(
    geoserver_url: str, store_name: str, layer_name: str, username: str, password: str
) -> None:
    url = f"{geoserver_url}/rest/workspaces/{GEOSERVER_WORKSPACE}/coveragestores/{store_name}/coverages/{layer_name}"
    headers = {
        "Content-Type": "application/xml",
        "Accept": "application/xml",
    }
    data = """
    <coverage>
        <enabled>true</enabled>
        <metadata>
            <entry key="time">
                <dimensionInfo>
                    <enabled>true</enabled>
                    <presentation>LIST</presentation>
                    <units>ISO8601</units>
                    <defaultValue>
                        <strategy>MINIMUM</strategy>
                    </defaultValue>
                </dimensionInfo>
            </entry>
        </metadata>
    </coverage>
    """.strip()

    response = requests.put(
        url,
        data=data,
        headers=headers,
        auth=(username, password),
        timeout=GEOSERVER_REQUEST_TIMEOUT,
    )
    if response.status_code not in [200, 201]:
        log.error(f"Failed to enable time dimension for {layer_name}: {response.text}")


def _extract_mer_run_date(ready_filename: str) -> str | None:
    match = re.match(r"^(\d{8})\.READY$", ready_filename)
    if match:
        return match.group(1)
    return None


def _get_latest_mer_ready_run(forcing_dir: str) -> str | None:
    ready_runs: list[str] = []
    for filename in os.listdir(forcing_dir):
        run_date = _extract_mer_run_date(filename)
        if run_date:
            ready_runs.append(run_date)
    if ready_runs:
        return max(ready_runs)

    # Fallback: infer run date from TIFF names (YYYYMMDDTHHMMSS.tif)
    # using the minimum date found in variable folders.
    inferred_dates: list[str] = []
    for variable_name in os.listdir(forcing_dir):
        variable_path = os.path.join(forcing_dir, variable_name)
        if not os.path.isdir(variable_path):
            continue
        for filename in os.listdir(variable_path):
            match = re.match(
                r"^(\d{8})T\d{6}\.(tif|tiff)$", filename, flags=re.IGNORECASE
            )
            if match:
                inferred_dates.append(match.group(1))

    if inferred_dates:
        inferred_run = min(inferred_dates)
        log.warning(
            f"No forcing READY marker found in {forcing_dir}; inferred run date {inferred_run} from TIFF filenames"
        )
        return inferred_run

    return None


def _update_forcing_geoserver_ready_if_complete(
    forcing_dir: str, forcing_name: str, run_date: str
) -> None:
    # Write forcing-level run marker used by the marine status endpoint.
    forcing_ready_file = os.path.join(forcing_dir, f"{run_date}.GEOSERVER.READY")

    # Keep only one forcing-level GEOSERVER.READY marker.
    for filename in os.listdir(forcing_dir):
        if (
            filename.endswith(".GEOSERVER.READY")
            and filename != f"{run_date}.GEOSERVER.READY"
        ):
            try:
                os.remove(os.path.join(forcing_dir, filename))
            except Exception as e:
                log.warning(
                    f"Failed removing stale forcing ready marker {filename}: {e}"
                )

    with open(forcing_ready_file, "w") as f:
        f.write(f"Processed by GeoServer at {datetime.now().isoformat()}\n")
        f.write(f"Run: {run_date}\n")
        f.write(f"Forcing: {forcing_name}\n")

    log.info(f"Created forcing-level ready marker: {forcing_ready_file}")


def _ensure_mer_wl_style() -> bool:
    """Ensure the MER water_level style exists in GeoServer."""
    if check_style_exists(
        GEOSERVER_URL, MER_WL_STYLE_NAME, USERNAME, PASSWORD, GEOSERVER_WORKSPACE
    ):
        return True

    for style_path in MER_WL_STYLE_CANDIDATE_PATHS:
        if not os.path.exists(style_path):
            continue

        try:
            with open(style_path, "r", encoding="utf-8") as sld_file:
                sld_content = sld_file.read().strip()
        except Exception as e:
            log.error(f"Failed reading MER wl SLD from {style_path}: {e}")
            continue

        if not sld_content:
            log.error(f"MER wl SLD is empty: {style_path}")
            continue

        if upload_sld_generic(
            GEOSERVER_URL, sld_content, MER_WL_STYLE_NAME, USERNAME, PASSWORD
        ):
            return True

    log.error("Unable to ensure MER wl style 'water_level' in GeoServer")
    return False


def check_latest_data_and_trigger_geoserver_import_mer_bolam(
    mer_base_path: str = MER_BASE_PATH,
) -> None:
    """
    Scan MER forcing directories and trigger ingestion per variable folder.

    Layer names are built as SHYFEM-<FORCING>-<variable>,
    for example BOLAM/wl -> SHYFEM-BOLAM-wl.
    """
    log.info(f"Checking latest MER data in {mer_base_path}")

    if not os.path.exists(mer_base_path):
        log.warning(f"MER base path does not exist: {mer_base_path}")
        return

    for forcing_name in MER_FORCINGS:
        forcing_dir = os.path.join(mer_base_path, forcing_name)
        if not os.path.exists(forcing_dir):
            log.info(f"Forcing directory not found, skipping: {forcing_dir}")
            continue

        run_date = _get_latest_mer_ready_run(forcing_dir)
        if not run_date:
            log.info(f"No forcing READY marker found in {forcing_dir}")
            continue

        variable_dirs = [
            d
            for d in os.listdir(forcing_dir)
            if os.path.isdir(os.path.join(forcing_dir, d))
        ]

        for variable_name in variable_dirs:
            source_dir = os.path.join(forcing_dir, variable_name)
            tiff_files = [
                f
                for f in os.listdir(source_dir)
                if f.lower().endswith((".tif", ".tiff"))
            ]
            if not tiff_files:
                continue

            layer_name = f"SHYFEM-{forcing_name}-{variable_name}"
            checked_file = os.path.join(
                forcing_dir, f"{run_date}.{variable_name}.CELERY.CHECKED"
            )
            ready_file = os.path.join(forcing_dir, f"{run_date}.GEOSERVER.READY")

            if os.path.exists(ready_file):
                log.info(f"{layer_name} already ingested for run {run_date}")
                continue

            retry = 0
            if os.path.exists(checked_file):
                age_seconds = (
                    datetime.now()
                    - datetime.fromtimestamp(os.path.getmtime(checked_file))
                ).total_seconds()
                retry = read_retry_count(checked_file)

                if age_seconds > 300:
                    retry += 1
                    if retry > 1:
                        log.error(
                            f"MER processing stuck for {layer_name} after {retry} retries"
                        )
                        mark_ingestion_unhealthy(
                            f"MER processing stuck for {layer_name} after {retry} retries"
                        )
                        os.remove(checked_file)
                        continue
                    os.remove(checked_file)
                else:
                    log.info(
                        f"{layer_name} already checked (pending for {age_seconds:.0f}s)"
                    )
                    continue

            with open(checked_file, "w") as f:
                f.write(f"Checked by Celery task at {datetime.now().isoformat()}\n")
                f.write(f"Run: {run_date}\n")
                f.write(f"Layer: {layer_name}\n")
                f.write(f"Retry: {retry}\n")
            log.info(f"Created {checked_file}")

            c = celery.get_instance()
            from .registry import load_registry

            c.celery_app.send_task(
                load_registry().ingestion_task("marine"),
                args=(source_dir, forcing_dir, forcing_name, variable_name, run_date),
            )
            log.info(
                f"Triggered update_geoserver_mer_bolam_layer for {layer_name} ({run_date})"
            )

    log.info("Finished checking MER data")


def update_geoserver_mer_bolam_layer(
    self,
    source_dir: str,
    forcing_dir: str,
    forcing_name: str,
    variable_name: str,
    run_date: str,
    cache_config=None,
) -> None:
    """
    Ingest a MER forcing variable folder into GeoServer as an ImageMosaic.
    """
    layer_name = f"SHYFEM-{forcing_name}-{variable_name}"
    store_name = f"mosaic-{layer_name}"
    checked_file = os.path.join(
        forcing_dir, f"{run_date}.{variable_name}.CELERY.CHECKED"
    )
    ready_file = os.path.join(forcing_dir, f"{run_date}.GEOSERVER.READY")
    target_dir = os.path.join(GEOSERVER_COPIES_BASE_DIRECTORY, layer_name)

    if not os.path.exists(source_dir):
        log.warning(f"MER/BOLAM source directory not found: {source_dir}")
        return

    tiff_files = [
        f for f in os.listdir(source_dir) if f.lower().endswith((".tif", ".tiff"))
    ]
    if not tiff_files:
        log.warning(f"No TIFF files found in {source_dir}")
        if os.path.exists(checked_file):
            os.remove(checked_file)
        return

    log.info(f"Starting MER ingestion for {layer_name}, run {run_date}")
    create_workspace_generic(GEOSERVER_URL, USERNAME, PASSWORD, GEOSERVER_WORKSPACE)

    if os.path.exists(target_dir):
        shutil.rmtree(target_dir)
    os.makedirs(target_dir, exist_ok=True)

    for tif_name in tiff_files:
        shutil.copy2(
            os.path.join(source_dir, tif_name), os.path.join(target_dir, tif_name)
        )

    _create_mer_mosaic_config(target_dir)

    upload_ok = upload_geotiff_generic(
        GEOSERVER_URL,
        target_dir,
        store_name,
        USERNAME,
        PASSWORD,
        GEOSERVER_WORKSPACE,
    )
    if not upload_ok:
        log.error(f"Failed to upload ImageMosaic for {layer_name}")
        return

    publish_ok = publish_layer_generic(
        GEOSERVER_URL,
        store_name,
        layer_name,
        USERNAME,
        PASSWORD,
        GEOSERVER_WORKSPACE,
    )
    if not publish_ok:
        log.error(f"Failed to publish layer {layer_name}")
        return

    _enable_mer_time_dimension(
        GEOSERVER_URL, store_name, layer_name, USERNAME, PASSWORD
    )

    # For water level layers, ensure style exists and set it as default.
    if variable_name.lower() == "wl":
        if not _ensure_mer_wl_style():
            log.error(
                f"Failed to ensure SLD style '{MER_WL_STYLE_NAME}' for layer {layer_name}"
            )
            return

        if not associate_sld_with_layer_generic(
            GEOSERVER_URL,
            layer_name,
            MER_WL_STYLE_NAME,
            USERNAME,
            PASSWORD,
            GEOSERVER_WORKSPACE,
        ):
            log.error(
                f"Failed to associate style '{MER_WL_STYLE_NAME}' with layer {layer_name}"
            )
            return

    schedule_cache_refresh_chord(
        [
            {
                "layer_name": layer_name,
                "geoserver_url": GEOSERVER_URL,
                "username": USERNAME,
                "password": PASSWORD,
                "workspace": GEOSERVER_WORKSPACE,
                "store_name": store_name,
                "zoom_start": (cache_config or {}).get("zoom_start"),
                "zoom_stop": (cache_config or {}).get("zoom_stop"),
            }
        ],
        ready_file=ready_file,
        ready_contents=(
            f"Processed by GeoServer at {datetime.now().isoformat()}\n"
            f"Run: {run_date}\nLayer: {layer_name}\nVariable: {variable_name}\n"
        ),
        checked_files=[checked_file],
        completion={
            "forcing_dir": forcing_dir,
            "forcing_name": forcing_name,
            "run_date": run_date,
        },
    )
    log.info("MER ingestion submitted for cache invalidation: {}", layer_name)
