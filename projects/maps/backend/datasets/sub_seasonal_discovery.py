"""Discover sub-seasonal runs and debounce publication by date range."""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from restapi.connectors import celery
from restapi.env import Env
from restapi.utilities.logs import log

from .registry import load_registry
from .watcher import DataWatcher, mark_ingestion_unhealthy, read_retry_count


def check_latest_data_and_trigger_geoserver_import_sub_seasonal(
    sub_seasonal_path: Optional[str] = None,
) -> None:
    """Trigger publication for the newest READY run and its TIFF date range.
    
    Args:
        sub_seasonal_path: Base path for sub-seasonal data. If None, uses
            default fallback for backward compatibility. Caller should pass
            path resolved from manifest config.
    """
    if sub_seasonal_path is None:
        sub_seasonal_path = Env.get("SUB_SEASONAL_AIM_PATH", "/sub-seasonal-aim")
    """Trigger publication for the newest READY run and its TIFF date range."""
    log.info("Checking latest sub-seasonal data")

    def custom_action(identifier, latest_file, path):
        run_date = identifier
        var_dirs = [
            d
            for d in os.listdir(path)
            if d != "json_weekly" and os.path.isdir(os.path.join(path, d))
        ]
        if not var_dirs:
            log.warning(f"No variable directories found in {path}")
            return

        var_path = os.path.join(path, var_dirs[0])
        child_dirs = [
            d for d in os.listdir(var_path) if os.path.isdir(os.path.join(var_path, d))
        ]
        if not child_dirs:
            log.warning(f"No child directories found in {var_path}")
            return

        sample_dir = os.path.join(var_path, child_dirs[0])
        dates = []
        for filename in os.listdir(sample_dir):
            if filename.endswith((".tiff", ".tif")):
                try:
                    dates.append(datetime.strptime(filename.split(".")[0], "%Y-%m-%d"))
                except ValueError:
                    continue
        if not dates:
            log.warning(f"No valid TIFF dates found in {sample_dir}")
            return

        range_str = f"{min(dates):%Y%m%d}-{max(dates):%Y%m%d}"
        geoserver_ready_file = os.path.join(path, f"{range_str}.GEOSERVER.READY")
        if os.path.exists(geoserver_ready_file):
            try:
                with open(geoserver_ready_file) as marker:
                    if f"Run: {run_date}" in marker.read():
                        log.info(
                            f"Range {range_str} already processed for run {run_date}"
                        )
                        return
            except OSError as exc:
                log.warning(f"Failed to read {geoserver_ready_file}: {exc}")

        checked_file = os.path.join(path, f"{range_str}.CELERY.CHECKED")
        retry = 0
        if os.path.exists(checked_file):
            age = (
                datetime.now() - datetime.fromtimestamp(os.path.getmtime(checked_file))
            ).total_seconds()
            retry = read_retry_count(checked_file)
            if age <= 300:
                log.info(f"Range {range_str} already checked (pending for {age:.0f}s)")
                return
            retry += 1
            if retry > 1:
                log.error(
                    f"Range {range_str} has been retried {retry} times, marking container as unhealthy"
                )
                mark_ingestion_unhealthy(
                    f"Sub-seasonal processing stuck for range {range_str} after {retry} retries"
                )
                os.remove(checked_file)
                return
            os.remove(checked_file)

        with open(checked_file, "w") as marker:
            marker.write(f"Checked by Celery task at {datetime.now().isoformat()}\n")
            marker.write(f"Run: {run_date}\nRange: {range_str}\nRetry: {retry}\n")
        celery.get_instance().celery_app.send_task(
            load_registry().ingestion_task("sub-seasonal"), args=(run_date, range_str)
        )
        log.info(f"Triggered sub-seasonal publication for {run_date} range {range_str}")

    DataWatcher(
        paths=sub_seasonal_path,
        ready_suffix=".READY",
        processed_suffix=".GEOSERVER.READY",
    ).check_and_trigger(custom_action=custom_action, skip_debounce=True)
    log.info("Finished checking sub-seasonal data")
