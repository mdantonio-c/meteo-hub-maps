from restapi.connectors.celery import CeleryExt
from restapi.utilities.logs import log
from typing import Optional
import os
import requests
import re
from datetime import datetime, timedelta
from restapi.connectors import celery
from restapi.env import Env

GEOSERVER_URL = "http://geoserver.dockerized.io:8080/geoserver" # TODO: get from env
USERNAME = Env.get("GEOSERVER_ADMIN_USER", None)
PASSWORD = Env.get("GEOSERVER_ADMIN_PASSWORD", None)
dataset = "icon"
area = "Italia"
GRANULE_RETENTION_HOURS = int(Env.get("RADAR_RETENTION_HOURS", 72))

@CeleryExt.task(idempotent=True)
def check_latest_data_and_trigger_geoserver_import_windy(
    self,
    paths: list[str] = [os.path.join("/windy", f"Windy-00-ICON_2I_all2km.web/Italia"), os.path.join("/windy", f"Windy-12-ICON_2I_all2km.web/Italia")],
) -> None:
    """
    Check the latest data in the given paths.
    """
    ready_files = []
    log.info("Checking latest data in paths")
    for path in paths:
        if not os.path.exists(path):
            log.warning(f"Path does not exist: {path}")
            continue
        ready_files.extend([{"path": path, "file": f} for f in os.listdir(path) if f.endswith(".READY")])
        if not ready_files:
            log.info(f"No .READY files found in {path}")
            continue

    # Sort files by date (assuming the filename is a date)
    ready_files.sort(key=lambda x: datetime.strptime(x["file"].split(".")[0], "%Y%m%d%H"))
    if len(ready_files) == 0:
        log.info("No .READY files found in any path")
        return
    latest_ready_path, latest_ready_file = [ready_files[-1]["path"], ready_files[-1]["file"]]
    geoserver_ready_path = os.path.join(latest_ready_path, latest_ready_file.split(".")[0] + ".GEOSERVER.READY")
    celery_checked_path = os.path.join(latest_ready_path, latest_ready_file.split(".")[0] + ".CELERY.CHECKED")

    if not os.path.exists(geoserver_ready_path):
        log.info(f"No GEOSERVER.READY file found in {latest_ready_path}")
        latest_ready_date = latest_ready_file.split(".")[0]
        
        if os.path.exists(celery_checked_path):
            # if more than 10 minutes since last check, create a new CELERY.CHECKED file
            if (datetime.now() - datetime.fromtimestamp(os.path.getmtime(celery_checked_path))).total_seconds() > 600:
                os.remove(celery_checked_path)
                log.info(f"Deleted {celery_checked_path} as it was older than 10 minutes")
            else:
                log.info(f"Skipping {latest_ready_file} as it has already been checked within the last 10 minutes")
                return

        # Create a CELERY.CHECKED file for the latest .READY file
        celery_checked_path = os.path.join(latest_ready_path, f"{latest_ready_date}.CELERY.CHECKED")
        os.makedirs(os.path.dirname(celery_checked_path), exist_ok=True)
        with open(celery_checked_path, "w") as f:
            f.write("Checked by Celery task")
            log.info(f"Created {celery_checked_path}")
        c = celery.get_instance()
        run = latest_ready_file.split(".")[0][:8]
        date = latest_ready_file.split(".")[0][8:10]
        # c.celery_app.send_task(
        #             "update_geoserver_layers",
        #             args=(
        #                 GEOSERVER_URL,
        #                 USERNAME,
        #                 PASSWORD,
        #                 date,
        #                 run,
        #             )
        # )
        c.celery_app.send_task(
                    "update_geoserver_image_mosaic",
                    args=(
                        GEOSERVER_URL,
                        date,
                        run,
                    )
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
    log.info("Checking latest seasonal data")
    
    if not os.path.exists(seasonal_path):
        log.warning(f"Seasonal path does not exist: {seasonal_path}")
        return
    
    # Find .READY files in the seasonal directory
    ready_files = [f for f in os.listdir(seasonal_path) if f.endswith(".READY")]
    
    if not ready_files:
        log.info(f"No .READY files found in {seasonal_path}")
        return
    
    # Since there's only one READY file, take the first one
    latest_ready_file = ready_files[0]
    latest_ready_date = latest_ready_file.split(".")[0]
    
    geoserver_ready_path = os.path.join(seasonal_path, f"{latest_ready_date}.GEOSERVER.READY")
    celery_checked_path = os.path.join(seasonal_path, f"{latest_ready_date}.CELERY.CHECKED")
    
    if not os.path.exists(geoserver_ready_path):
        log.info(f"No GEOSERVER.READY file found for {latest_ready_file}")
        
        if os.path.exists(celery_checked_path):
            # If more than 10 minutes since last check, create a new CELERY.CHECKED file
            if (datetime.now() - datetime.fromtimestamp(os.path.getmtime(celery_checked_path))).total_seconds() > 600:
                os.remove(celery_checked_path)
                log.info(f"Deleted {celery_checked_path} as it was older than 10 minutes")
            else:
                log.info(f"Skipping {latest_ready_file} as it has already been checked within the last 10 minutes")
                return
        
        # Create a CELERY.CHECKED file for the seasonal data
        os.makedirs(os.path.dirname(celery_checked_path), exist_ok=True)
        with open(celery_checked_path, "w") as f:
            f.write("Checked by Celery task")
            log.info(f"Created {celery_checked_path}")
        
        c = celery.get_instance()
        # For seasonal data, we'll use a different task or parameters
        c.celery_app.send_task(
            "update_geoserver_seasonal_layers",
            args=(
                latest_ready_date,
            )
        )
        log.info(f"Triggered seasonal data update for {latest_ready_date}")
    else:
        log.info(f"GEOSERVER.READY already exists for {latest_ready_file}")
    
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
        end_dt = None
        log.info(f"Checking variable: {var}")
        var_path = os.path.join(radar_path, var)
        if not os.path.exists(var_path):
            log.warning(f"Radar variable path does not exist: {var_path}")
            continue
            
        # Find .READY files
        ready_files = [f for f in os.listdir(var_path) if f.endswith(".READY") and not f.endswith(".GEOSERVER.READY")]
        
        if not ready_files:
            log.info(f"No .READY files found in {var_path}")
            continue
            
        # Sort by date/time and get latest
        ready_files.sort()
        latest_ready_file = ready_files[-1]
        latest_ready_date = latest_ready_file.split(".")[0]
        
        # Parse the latest READY timestamp
        try:
            current_ready_dt = datetime.strptime(latest_ready_date, "%Y%m%d%H%M")
        except ValueError:
            log.error(f"Could not parse timestamp from READY file: {latest_ready_file}")
            continue
        
        # Find all date-range .GEOSERVER.READY files to determine last processed timestamp
        geoserver_ready_files = [f for f in os.listdir(var_path) if f.endswith(".GEOSERVER.READY")]
        
        if geoserver_ready_files:
            # Parse date range files (format: YYYYMMDDHHMM-YYYYMMDDHHMM.GEOSERVER.READY)
            for gf in geoserver_ready_files:
                try:
                    date_range = gf.split(".")[0]
                    if "-" in date_range:
                        # Date range format
                        from_date, to_date = date_range.split("-")
                        end_dt = datetime.strptime(to_date, "%Y%m%d%H%M")
                    else:
                        # Old single date format (backward compatibility)
                        end_dt = datetime.strptime(date_range, "%Y%m%d%H%M")
                    
                except ValueError:
                    log.warning(f"Could not parse GEOSERVER.READY file: {gf}")
        
        log.info(f"New data found for {var}: {latest_ready_file}")
        
        # Check CELERY.CHECKED debounce logic
        celery_checked_path = os.path.join(var_path, f"{latest_ready_date}.CELERY.CHECKED")
        if os.path.exists(celery_checked_path):
            if (datetime.now() - datetime.fromtimestamp(os.path.getmtime(celery_checked_path))).total_seconds() > 1800:
                os.remove(celery_checked_path)
                log.info(f"Deleted {celery_checked_path} as it was older than 30 minutes")
            else:
                log.info(f"Skipping {latest_ready_file} as it has already been checked within the last 30 minutes")
                continue
        
        # Determine time range to process
        start_dt = current_ready_dt - timedelta(hours=GRANULE_RETENTION_HOURS)
        
        # Collect all pending files in the time range
        pending_filenames = []
        pending_dates = []
        log.info(f"Processing {var} from {start_dt} to {current_ready_dt} {type(end_dt)} {end_dt is not None}")
        if end_dt is not None and current_ready_dt <= end_dt:
            continue 
        temp_dt = start_dt
        while temp_dt <= current_ready_dt:
            # Generate expected filename (format: DD-MM-YYYY-HH-MM.tif)
            expected_filename = temp_dt.strftime("%d-%m-%Y-%H-%M.tif")
            expected_path = os.path.join(var_path, 'files', expected_filename)
            
            if os.path.exists(expected_path):
                pending_filenames.append(expected_filename)
                pending_dates.append(temp_dt)
                log.debug(f"Found pending file: {expected_filename}")
            
            temp_dt += timedelta(minutes=1)
        
        if not pending_filenames:
            log.info(f"No pending files found for {var}")
            continue
        
        log.info(f"Found {len(pending_filenames)} pending file(s) for {var}")
        
        # Create CELERY.CHECKED file with date range
        min_date = min(pending_dates)
        max_date = max(pending_dates)

        date_range_str = f"{min_date.strftime('%Y%m%d%H%M')}-{max_date.strftime('%Y%m%d%H%M')}"
        celery_checked_path = os.path.join(var_path, f"{date_range_str}.CELERY.CHECKED")
        
        os.makedirs(os.path.dirname(celery_checked_path), exist_ok=True)
        with open(celery_checked_path, "w") as f:
            f.write(f"Checked by Celery task at {datetime.now().isoformat()}\n")
            f.write(f"Files: {len(pending_filenames)}\n")
        log.info(f"Created {celery_checked_path}")
        log.info(f"Pending files: {pending_filenames}")
        log.info(f"Pending dates: {pending_dates}")
        # Send batch to Celery task
        c = celery.get_instance()
        c.celery_app.send_task(
            "update_geoserver_radar_layers",
            args=(
                var,
                pending_filenames,  # List of filenames
                pending_dates,      # List of datetime objects
            )
        )
        log.info(f"Triggered batch radar data update for {var} with {len(pending_filenames)} file(s)")
            
    log.info("Finished checking radar data")