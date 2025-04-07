from restapi.connectors.celery import CeleryExt
from restapi.utilities.logs import log
from typing import Optional
import os
import requests
import re
from datetime import datetime
from restapi.connectors import celery
from restapi.env import Env

GEOSERVER_URL = "http://geoserver.dockerized.io:8080/geoserver" # TODO: get from env
USERNAME = Env.get("GEOSERVER_ADMIN_USER", None)
PASSWORD = Env.get("GEOSERVER_ADMIN_PASSWORD", None)
dataset = "icon"
area = "Italia"

@CeleryExt.task(idempotent=True)
def check_latest_data_and_trigger_geoserver_import(
    self,
    paths: list[str] = [os.path.join("/meteo", f"Windy-00-ICON_2I_all2km.web/Italia"), os.path.join("/meteo", f"Windy-12-ICON_2I_all2km.web/Italia")],
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

    latest_ready_path, latest_ready_file = [ready_files[-1]["path"], ready_files[-1]["file"]]
    geoserver_ready_path = os.path.join(latest_ready_path, latest_ready_file.split(".")[0] + ".GEOSERVER.READY")
    celery_checked_path = os.path.join(latest_ready_path, latest_ready_file.split(".")[0] + ".CELERY.CHECKED")

    if not os.path.exists(geoserver_ready_path):
        log.info(f"No GEOSERVER.READY file found in {latest_ready_path}")
        latest_ready_date = latest_ready_file.split(".")[0]
        
        if os.path.exists(celery_checked_path):
            log.info(f"Skipping {latest_ready_file} as it has already been checked")
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
        c.celery_app.send_task(
                    "update_geoserver_layers",
                    args=(
                        GEOSERVER_URL,
                        USERNAME,
                        PASSWORD,
                        date,
                        run,
                    )
        )
            
    log.info("Finished checking latest data")