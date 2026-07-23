from restapi.connectors.celery import CeleryExt
from restapi.utilities.logs import log
import os
import re
import shutil
import requests
from datetime import datetime, timedelta
from restapi.connectors import celery
from restapi.env import Env
from maps.tasks.data_watcher import DataWatcher, DataWatcherStream
from maps.tasks.geoserver_utils import (
    create_workspace_generic,
    upload_geotiff_generic,
    publish_layer_generic,
    check_style_exists,
    upload_sld_generic,
    associate_sld_with_layer_generic,
)
# Thredds integration disabled.
# from maps.tasks.thredds import (  # noqa: F401
#     check_latest_data_and_trigger_thredds_ingestion,
#     ingest_MER_ready_directory,
# )

GEOSERVER_URL = "http://geoserver.dockerized.io:8080/geoserver" # TODO: get from env
USERNAME = Env.get("GEOSERVER_ADMIN_USER", None)
PASSWORD = Env.get("GEOSERVER_ADMIN_PASSWORD", None)
dataset = "icon"
area = "Italia"
GRANULE_RETENTION_HOURS = int(Env.get("RADAR_RETENTION_HOURS", 72))
SUB_SEASONAL_BASE_PATH = Env.get("SUB_SEASONAL_AIM_PATH", "/sub-seasonal-aim")
WW3_BASE_PATH = Env.get("WW3_DATA_PATH", "/ww3")
WINDY_INGEST_BASE_PATH = Env.get("WINDY_INGEST_BASE_PATH", "/windy")
WINDY_INGEST_AREA = Env.get("WINDY_INGEST_AREA", "Italia")
WINDY_INGEST_FOLDERS = [
    folder.strip()
    for folder in Env.get(
        "WINDY_INGEST_FOLDERS",
        "Windy-00-ICON_2I_all2km.web,Windy-12-ICON_2I_all2km.web",
    ).split(",")
    if folder.strip()
]
WINDY_WRF_INGEST_FOLDERS = [
    folder.strip()
    for folder in Env.get(
        "WINDY_WRF_INGEST_FOLDERS",
        "Windy-00-WRF.web,Windy-12-WRF.web",
    ).split(",")
    if folder.strip()
]
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


def _get_windy_ingest_paths() -> list[str]:
    return [
        os.path.join(WINDY_INGEST_BASE_PATH, folder, WINDY_INGEST_AREA)
        for folder in WINDY_INGEST_FOLDERS
    ]


def _get_windy_wrf_ingest_paths() -> list[str]:
    return [
        os.path.join(WINDY_INGEST_BASE_PATH, folder, WINDY_INGEST_AREA)
        for folder in WINDY_WRF_INGEST_FOLDERS
    ]


def _extract_dataset_from_path(path: str) -> str:
    folder = os.path.basename(os.path.dirname(path))
    match = re.match(r"^Windy-(\d{2})-(.+)\.web$", folder)
    if match:
        return match.group(2)
    log.warning(f"Could not parse windy dataset from path: {path}. Falling back to ICON_2I_all2km")
    return "ICON_2I_all2km"


def _is_wrf_path(path: str) -> bool:
    return _extract_dataset_from_path(path).upper() == "WRF"


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


def _enable_mer_time_dimension(geoserver_url: str, store_name: str, layer_name: str, username: str, password: str) -> None:
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

    response = requests.put(url, data=data, headers=headers, auth=(username, password))
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
            match = re.match(r"^(\d{8})T\d{6}\.(tif|tiff)$", filename, flags=re.IGNORECASE)
            if match:
                inferred_dates.append(match.group(1))

    if inferred_dates:
        inferred_run = min(inferred_dates)
        log.warning(
            f"No forcing READY marker found in {forcing_dir}; inferred run date {inferred_run} from TIFF filenames"
        )
        return inferred_run

    return None


def _read_run_from_marker(marker_path: str) -> str | None:
    if not os.path.exists(marker_path):
        return None
    try:
        with open(marker_path, "r") as f:
            for line in f:
                if line.startswith("Run:"):
                    return line.split(":", 1)[1].strip()
    except Exception as e:
        log.warning(f"Failed reading marker {marker_path}: {e}")
    return None


def _update_forcing_geoserver_ready_if_complete(forcing_dir: str, forcing_name: str, run_date: str) -> None:
    # Write forcing-level run marker used by the marine status endpoint.
    forcing_ready_file = os.path.join(forcing_dir, f"{run_date}.GEOSERVER.READY")

    # Keep only one forcing-level GEOSERVER.READY marker.
    for filename in os.listdir(forcing_dir):
        if filename.endswith(".GEOSERVER.READY") and filename != f"{run_date}.GEOSERVER.READY":
            try:
                os.remove(os.path.join(forcing_dir, filename))
            except Exception as e:
                log.warning(f"Failed removing stale forcing ready marker {filename}: {e}")

    with open(forcing_ready_file, "w") as f:
        f.write(f"Processed by GeoServer at {datetime.now().isoformat()}\n")
        f.write(f"Run: {run_date}\n")
        f.write(f"Forcing: {forcing_name}\n")

    log.info(f"Created forcing-level ready marker: {forcing_ready_file}")


def _ensure_mer_wl_style() -> bool:
    """Ensure the MER water_level style exists in GeoServer."""
    if check_style_exists(GEOSERVER_URL, MER_WL_STYLE_NAME, USERNAME, PASSWORD, GEOSERVER_WORKSPACE):
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

        if upload_sld_generic(GEOSERVER_URL, sld_content, MER_WL_STYLE_NAME, USERNAME, PASSWORD):
            return True

    log.error("Unable to ensure MER wl style 'water_level' in GeoServer")
    return False

@CeleryExt.task(idempotent=True)
def check_latest_data_and_trigger_geoserver_import_windy(
    self,
    paths: list[str] | None = None,
) -> None:
    """
    Check the latest data in the given paths.
    """
    if paths is None:
        paths = _get_windy_ingest_paths()

    wrf_paths = [p for p in paths if _is_wrf_path(p)]
    non_wrf_paths = [p for p in paths if not _is_wrf_path(p)]

    # Ensure WRF is checked in a dedicated pass, even when it is not listed in WINDY_INGEST_FOLDERS.
    configured_wrf_paths = _get_windy_wrf_ingest_paths()
    for wrf_path in configured_wrf_paths:
        if wrf_path not in wrf_paths:
            wrf_paths.append(wrf_path)

    def get_task_args(identifier, filename, path):
        date = identifier[:8]
        run = identifier[8:10]
        dataset_folder = _extract_dataset_from_path(path)
        return (GEOSERVER_URL, run, date, "/SLDs", dataset_folder)

    if non_wrf_paths:
        watcher = DataWatcher(
            paths=non_wrf_paths,
            sort_key=lambda f: datetime.strptime(f.split(".")[0], "%Y%m%d%H"),
            identifier_extractor=lambda f: f.split(".")[0],
        )

        watcher.check_and_trigger(
            task_name="update_geoserver_image_mosaic",
            task_args=get_task_args,
        )
    else:
        log.info("No non-WRF windy ingest paths configured")

    if wrf_paths:
        wrf_watcher = DataWatcher(
            paths=wrf_paths,
            sort_key=lambda f: datetime.strptime(f.split(".")[0], "%Y%m%d%H"),
            identifier_extractor=lambda f: f.split(".")[0],
        )

        wrf_watcher.check_and_trigger(
            task_name="update_geoserver_image_mosaic",
            task_args=get_task_args,
        )
    else:
        log.info("No WRF windy ingest paths configured")

    # Ensure MER ingestion check runs even if its periodic task is missing/stale.
    try:
        c = celery.get_instance()
        c.celery_app.send_task(
            "check_latest_data_and_trigger_geoserver_import_mer_bolam",
            args=(MER_BASE_PATH,),
        )
    except Exception as e:
        log.error(f"Failed to enqueue chained MER check from windy task: {e}")

    log.info("Finished checking latest windy data")


@CeleryExt.task(idempotent=True)
def check_latest_data_and_trigger_geoserver_import_seasonal(
    self,
    seasonal_path: str = "/seasonal-aim",
) -> None:
    """
    Check the latest seasonal data in the given path.
    """
    watcher = DataWatcher(
        paths=seasonal_path,
    )
    
    watcher.check_and_trigger(
        task_name="update_geoserver_seasonal_layers",
        task_args=lambda identifier, f, p: (identifier,)
    )
    log.info("Finished checking seasonal data")


@CeleryExt.task(idempotent=True)
def check_latest_data_and_trigger_geoserver_import_radar(
    self,
    radar_path: str = "/radar",
) -> None:
    """
    Check the latest radar data in the given path (sri and srt folders).
    """
    log.info("Checking latest radar data")
    if not os.path.exists(radar_path):
        # Try to find it in likely locations if default fails
        possible_paths = [radar_path, "/data/radar", os.path.join(os.getcwd(), "data/radar")]
        found = False
        for p in possible_paths:
            if os.path.exists(p):
                radar_path = p
                found = True
                break
        
        if not found:
            log.warning(f"Radar path does not exist: {radar_path}")
            return

    variables = ["sri", "srt"]
    
    for var in variables:
        log.info(f"Checking variable: {var}")
        var_path = os.path.join(radar_path, var)
        if not os.path.exists(var_path):
            log.warning(f"Radar variable path does not exist: {var_path}")
            continue

        watcher = DataWatcherStream(
            paths=var_path,
            ready_suffix=".READY",
            processed_suffix=".GEOSERVER.READY",
            debounce_seconds=1800, # 30 minutes for radar
            retention_hours=GRANULE_RETENTION_HOURS,
            sort_key=lambda f: f, # Default sort is fine (YYYYMMDDHHMM.READY)
            identifier_extractor=lambda f: f.split(".")[0]
        )

        watcher.check_and_trigger(
            task_name="update_geoserver_radar_layers",
            var_name=var
        )
            
    log.info("Finished checking radar data")


@CeleryExt.task(idempotent=True)
def check_latest_data_and_trigger_geoserver_import_sub_seasonal(
    self,
    sub_seasonal_path: str = SUB_SEASONAL_BASE_PATH,
) -> None:
    """
    Check the latest sub-seasonal data in the given path.
    """
    log.info("Checking latest sub-seasonal data")
    
    def custom_action(identifier, latest_file, path):
        run_date = identifier
        retry = 0
        
        # Calculate range from files in t2m/quintile_1
        # Get a random variable folder instead of hardcoding t2m
        var_dirs = [d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d)) and d not in ['.', '..']]
        if not var_dirs:
            log.warning(f"No variable directories found in {path}")
            return
        
        sample_var = var_dirs[0] if var_dirs[0] != "json_weekly" else var_dirs[1]  # Use first available variable folder
        var_path = os.path.join(path, sample_var)
        
        child_dirs = [d for d in os.listdir(var_path) if os.path.isdir(os.path.join(var_path, d)) and d not in ['.', '..']]
        if not child_dirs:
            log.warning(f"No child directories found in {var_path}")
            return
        
        sample_child = child_dirs[0]  # Use first available child folder
        sample_dir = os.path.join(var_path, sample_child)
        if not os.path.exists(sample_dir):
            log.warning(f"Sample directory {sample_dir} not found for run {run_date}")
            return

        files = [f for f in os.listdir(sample_dir) if f.endswith(".tiff") or f.endswith(".tif")]
        if not files:
            log.warning(f"No files found in {sample_dir}")
            return
            
        dates = []
        for f in files:
            try:
                d_str = f.split(".")[0]
                dates.append(datetime.strptime(d_str, "%Y-%m-%d"))
            except ValueError:
                continue
        
        if not dates:
            log.warning("No valid dates found in files")
            return
            
        min_date = min(dates)
        max_date = max(dates)
        range_str = f"{min_date.strftime('%Y%m%d')}-{max_date.strftime('%Y%m%d')}"
        
        # Check if processed
        geoserver_ready_file = os.path.join(path, f"{range_str}.GEOSERVER.READY")
        if os.path.exists(geoserver_ready_file):
            # Check if the run date inside matches the current run date
            try:
                with open(geoserver_ready_file, "r") as f:
                    content = f.read()
                    if f"Run: {run_date}" in content:
                        log.info(f"Range {range_str} already processed for run {run_date}")
                        return
                    else:
                        log.info(f"Range {range_str} exists but for a different run. Re-processing.")
            except Exception as e:
                log.warning(f"Failed to read {geoserver_ready_file}: {e}")
                # If we can't read it, assume we need to re-process or at least check pending
        
        # Check if pending (debounce)
        checked_file = os.path.join(path, f"{range_str}.CELERY.CHECKED")
        if os.path.exists(checked_file):
            # Check if pending for more than 300 seconds
            file_mtime = os.path.getmtime(checked_file)
            age_seconds = (datetime.now() - datetime.fromtimestamp(file_mtime)).total_seconds()
            # Read the retry count from the file
            try:
                with open(checked_file, "r") as f:
                    lines = f.readlines()
                    for line in reversed(lines):
                        if line.startswith("Retry:"):
                            retry = int(line.split(":")[1].strip())
                            break
            except Exception as e:
                log.warning(f"Failed to read retry count from {checked_file}: {e}")
                retry = 0
            if age_seconds > 300:
                log.info(f"Range {range_str} pending for {age_seconds:.0f}s (> 300s), removing and re-triggering")
                retry += 1
                if retry > 1:
                    log.error(f"Range {range_str} has been retried {retry} times, marking container as unhealthy")
                    # Mark container as unhealthy by creating/touching the health check failure file
                    health_check_file = "/status/health_check_failure"
                    with open(health_check_file, "w") as hf:
                        hf.write(f"Sub-seasonal processing stuck for range {range_str} after {retry} retries\n")
                        hf.write(f"Timestamp: {datetime.now().isoformat()}\n")
                    os.remove(checked_file)
                    return
                os.remove(checked_file)
            else:
                log.info(f"Range {range_str} already checked (pending for {age_seconds:.0f}s)")
                return
        if os.path.exists(checked_file):
            log.info(f"Range {range_str} already checked (pending)")
            return
            
        # Create CELERY.CHECKED
        with open(checked_file, "w") as f:
            f.write(f"Checked by Celery task at {datetime.now().isoformat()}\n")
            f.write(f"Run: {run_date}\n")
            f.write(f"Range: {range_str}\n")
            f.write(f"Retry: {retry}\n")
        log.info(f"Created {checked_file}")
        
        # Trigger task
        c = celery.get_instance()
        c.celery_app.send_task(
            "update_geoserver_sub_seasonal_layers",
            args=(run_date, range_str)
        )
        log.info(f"Triggered update_geoserver_sub_seasonal_layers for {run_date} range {range_str}")

    watcher = DataWatcher(
        paths=sub_seasonal_path,
        ready_suffix=".READY",
        processed_suffix=".GEOSERVER.READY"
    )
    
    watcher.check_and_trigger(
        custom_action=custom_action,
        skip_debounce=True
    )
    log.info("Finished checking sub-seasonal data")


@CeleryExt.task(idempotent=True)
def check_latest_data_and_trigger_geoserver_import_ww3(
    self,
    ww3_path: str = WW3_BASE_PATH,
) -> None:
    """
    Check the latest ww3 data in the given path.
    """
    log.info("Checking latest ww3 data")
    
    def custom_action(identifier, latest_file, path):
        run_date = identifier
        # retry = 0
        
        # # Check if processed
        # # If there's any GEOSERVER.READY file, return and we're okay
        # if any(f.endswith(".GEOSERVER.READY") for f in os.listdir(path)):
        #     log.info(f"GEOSERVER.READY file found in {path}, assuming run {run_date} is processed")
        #     return

        # # Check if pending (debounce)
        # checked_file = os.path.join(path, f"{run_date}.CELERY.CHECKED")
        # if os.path.exists(checked_file):
        #     # Check if pending for more than 300 seconds
        #     file_mtime = os.path.getmtime(checked_file)
        #     age_seconds = (datetime.now() - datetime.fromtimestamp(file_mtime)).total_seconds()
        #     # Read the retry count from the file
        #     try:
        #         with open(checked_file, "r") as f:
        #             lines = f.readlines()
        #             for line in reversed(lines):
        #                 if line.startswith("Retry:"):
        #                     retry = int(line.split(":")[1].strip())
        #                     break
        #     except Exception as e:
        #         log.warning(f"Failed to read retry count from {checked_file}: {e}")
        #         retry = 0
        #     if age_seconds > 300:
        #         log.info(f"Run {run_date} pending for {age_seconds:.0f}s (> 300s), removing and re-triggering")
        #         retry += 1
        #         if retry > 1:
        #             log.error(f"Run {run_date} has been retried {retry} times, marking container as unhealthy")
        #             # Mark container as unhealthy by creating/touching the health check failure file
        #             health_check_file = "/status/health_check_failure"
        #             with open(health_check_file, "w") as hf:
        #                 hf.write(f"WW3 processing stuck for run {run_date} after {retry} retries\n")
        #                 hf.write(f"Timestamp: {datetime.now().isoformat()}\n")
        #             os.remove(checked_file)
        #             return
        #         os.remove(checked_file)
        #     else:
        #         log.info(f"Run {run_date} already checked (pending for {age_seconds:.0f}s)")
        #         return
        # if os.path.exists(checked_file):
        #     log.info(f"Run {run_date} already checked (pending)")
        #     return
            
        # # Create CELERY.CHECKED
        # with open(checked_file, "w") as f:
        #     f.write(f"Checked by Celery task at {datetime.now().isoformat()}\n")
        #     f.write(f"Run: {run_date}\n")
        #     f.write(f"Retry: {retry}\n")
        # log.info(f"Created {checked_file}")
        
        # Trigger task
        c = celery.get_instance()
        c.celery_app.send_task(
            "update_geoserver_ww3_layers",
            args=(run_date,)
        )
        log.info(f"Triggered update_geoserver_ww3_layers for {run_date}")

    watcher = DataWatcher(
        paths=ww3_path,
        ready_suffix=".READY",
        processed_suffix=".GEOSERVER.READY"
    )
    
    watcher.check_and_trigger(
        custom_action=custom_action,
        skip_debounce=False
    )
    log.info("Finished checking ww3 data")


@CeleryExt.task(idempotent=True)
def check_latest_data_and_trigger_geoserver_import_mer_bolam(
    self,
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
                f for f in os.listdir(source_dir)
                if f.lower().endswith((".tif", ".tiff"))
            ]
            if not tiff_files:
                continue

            layer_name = f"SHYFEM-{forcing_name}-{variable_name}"
            checked_file = os.path.join(forcing_dir, f"{run_date}.{variable_name}.CELERY.CHECKED")
            ready_file = os.path.join(forcing_dir, f"{run_date}.GEOSERVER.READY")

            if os.path.exists(ready_file):
                log.info(f"{layer_name} already ingested for run {run_date}")
                continue

            retry = 0
            if os.path.exists(checked_file):
                age_seconds = (datetime.now() - datetime.fromtimestamp(os.path.getmtime(checked_file))).total_seconds()
                try:
                    with open(checked_file, "r") as f:
                        lines = f.readlines()
                        for line in reversed(lines):
                            if line.startswith("Retry:"):
                                retry = int(line.split(":", 1)[1].strip())
                                break
                except Exception as e:
                    log.warning(f"Failed to read retry count from {checked_file}: {e}")
                    retry = 0

                if age_seconds > 300:
                    retry += 1
                    if retry > 1:
                        log.error(f"MER processing stuck for {layer_name} after {retry} retries")
                        with open("/status/health_check_failure", "w") as hf:
                            hf.write(f"MER processing stuck for {layer_name} after {retry} retries\n")
                            hf.write(f"Timestamp: {datetime.now().isoformat()}\n")
                        os.remove(checked_file)
                        continue
                    os.remove(checked_file)
                else:
                    log.info(f"{layer_name} already checked (pending for {age_seconds:.0f}s)")
                    continue

            with open(checked_file, "w") as f:
                f.write(f"Checked by Celery task at {datetime.now().isoformat()}\n")
                f.write(f"Run: {run_date}\n")
                f.write(f"Layer: {layer_name}\n")
                f.write(f"Retry: {retry}\n")
            log.info(f"Created {checked_file}")

            c = celery.get_instance()
            c.celery_app.send_task(
                "update_geoserver_mer_bolam_layer",
                args=(source_dir, forcing_dir, forcing_name, variable_name, run_date),
            )
            log.info(f"Triggered update_geoserver_mer_bolam_layer for {layer_name} ({run_date})")

    log.info("Finished checking MER data")


@CeleryExt.task(idempotent=True)
def update_geoserver_mer_bolam_layer(
    self,
    source_dir: str,
    forcing_dir: str,
    forcing_name: str,
    variable_name: str,
    run_date: str,
) -> None:
    """
    Ingest a MER forcing variable folder into GeoServer as an ImageMosaic.
    """
    layer_name = f"SHYFEM-{forcing_name}-{variable_name}"
    store_name = f"mosaic-{layer_name}"
    checked_file = os.path.join(forcing_dir, f"{run_date}.{variable_name}.CELERY.CHECKED")
    ready_file = os.path.join(forcing_dir, f"{run_date}.GEOSERVER.READY")
    target_dir = os.path.join(GEOSERVER_COPIES_BASE_DIRECTORY, layer_name)

    if not os.path.exists(source_dir):
        log.warning(f"MER/BOLAM source directory not found: {source_dir}")
        return

    tiff_files = [
        f for f in os.listdir(source_dir)
        if f.lower().endswith((".tif", ".tiff"))
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
        shutil.copy2(os.path.join(source_dir, tif_name), os.path.join(target_dir, tif_name))

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

    _enable_mer_time_dimension(GEOSERVER_URL, store_name, layer_name, USERNAME, PASSWORD)

    # For water level layers, ensure style exists and set it as default.
    if variable_name.lower() == "wl":
        if not _ensure_mer_wl_style():
            log.error(f"Failed to ensure SLD style '{MER_WL_STYLE_NAME}' for layer {layer_name}")
            return

        if not associate_sld_with_layer_generic(
            GEOSERVER_URL,
            layer_name,
            MER_WL_STYLE_NAME,
            USERNAME,
            PASSWORD,
            GEOSERVER_WORKSPACE,
        ):
            log.error(f"Failed to associate style '{MER_WL_STYLE_NAME}' with layer {layer_name}")
            return

    with open(ready_file, "w") as f:
        f.write(f"Processed by GeoServer at {datetime.now().isoformat()}\n")
        f.write(f"Run: {run_date}\n")
        f.write(f"Layer: {layer_name}\n")
        f.write(f"Variable: {variable_name}\n")

    if os.path.exists(checked_file):
        os.remove(checked_file)

    _update_forcing_geoserver_ready_if_complete(forcing_dir, forcing_name, run_date)

    log.info(f"MER ingestion completed for {layer_name}")


@CeleryExt.task(idempotent=True)
def check_latest_data_and_trigger_thredds_ingestion(self) -> None:
    """No-op task kept for compatibility with stale periodic entries."""
    log.info("THREDDS ingestion task is disabled; skipping")