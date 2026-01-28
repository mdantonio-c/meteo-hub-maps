from restapi.connectors.celery import CeleryExt
from restapi.utilities.logs import log
import os
from datetime import datetime, timedelta
from restapi.connectors import celery
from restapi.env import Env
from maps.tasks.data_watcher import DataWatcher, DataWatcherStream

GEOSERVER_URL = "http://geoserver.dockerized.io:8080/geoserver" # TODO: get from env
USERNAME = Env.get("GEOSERVER_ADMIN_USER", None)
PASSWORD = Env.get("GEOSERVER_ADMIN_PASSWORD", None)
dataset = "icon"
area = "Italia"
GRANULE_RETENTION_HOURS = int(Env.get("RADAR_RETENTION_HOURS", 72))
SUB_SEASONAL_BASE_PATH = Env.get("SUB_SEASONAL_AIM_PATH", "/sub-seasonal-aim")
WW3_BASE_PATH = Env.get("WW3_DATA_PATH", "/ww3")

@CeleryExt.task(idempotent=True)
def check_latest_data_and_trigger_geoserver_import_windy(
    self,
    paths: list[str] = [os.path.join("/windy", f"Windy-00-ICON_2I_all2km.web/Italia"), os.path.join("/windy", f"Windy-12-ICON_2I_all2km.web/Italia")],
) -> None:
    """
    Check the latest data in the given paths.
    """
    def get_task_args(identifier, filename, path):
        run = identifier[:8]
        date = identifier[8:10]
        return (GEOSERVER_URL, date, run)

    watcher = DataWatcher(
        paths=paths,
        sort_key=lambda f: datetime.strptime(f.split(".")[0], "%Y%m%d%H"),
        identifier_extractor=lambda f: f.split(".")[0]
    )
    
    watcher.check_and_trigger(
        task_name="update_geoserver_image_mosaic",
        task_args=get_task_args
    )
    log.info("Finished checking latest data")


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