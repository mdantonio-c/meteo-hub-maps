from restapi.utilities.logs import log
from restapi.connectors import celery
from datetime import datetime, timedelta
import os
from typing import List, Optional, Union, Callable, Any, Tuple

class DataWatcher:
    def __init__(
        self,
        paths: Union[str, List[str]],
        ready_suffix: str = ".READY",
        processed_suffix: str = ".GEOSERVER.READY",
        debounce_seconds: int = 600,
        sort_key: Optional[Callable[[str], Any]] = None,
        identifier_extractor: Optional[Callable[[str], str]] = None,
    ):
        self.paths = [paths] if isinstance(paths, str) else paths
        self.ready_suffix = ready_suffix
        self.processed_suffix = processed_suffix
        self.debounce_seconds = debounce_seconds
        self.sort_key = sort_key
        self.identifier_extractor = identifier_extractor or (lambda f: f.split(self.ready_suffix)[0] if f.endswith(self.ready_suffix) else f.split(".")[0])

    def check_and_trigger(
        self,
        task_name: Optional[str] = None,
        task_args: Optional[Union[tuple, Callable[[str, str, str], tuple]]] = None,
        on_marker_creation: Optional[Callable[[str, str], None]] = None,
        dry_run: bool = False,
        custom_processed_check: Optional[Callable[[str, str], bool]] = None,
        custom_action: Optional[Callable[[str, str, str], None]] = None,
        skip_debounce: bool = False,
    ) -> None:
        
        ready_files = []
        # log.info(f"Checking latest data in {self.paths}")
        for path in self.paths:
            if not os.path.exists(path):
                log.warning(f"Path does not exist: {path}")
                continue
            log.info(os.listdir(path))
            files = [f for f in os.listdir(path) if f.endswith(self.ready_suffix)]
            
            for f in files:
                # Avoid picking up the processed file if suffixes overlap (e.g. .READY and .GEOSERVER.READY)
                if f.endswith(self.processed_suffix):
                    continue
                ready_files.append({"path": path, "file": f})

        if not ready_files:
            log.info(f"No {self.ready_suffix} files found in {self.paths}")
            return

        # Sort files
        sort_key_func = self.sort_key
        if sort_key_func:
            try:
                ready_files.sort(key=lambda x: sort_key_func(x["file"]))
            except Exception as e:
                log.error(f"Error sorting files: {e}")
                return
        else:
            ready_files.sort(key=lambda x: x["file"])

        latest = ready_files[-1]
        latest_path = latest["path"]
        latest_file = latest["file"]
        
        identifier = self.identifier_extractor(latest_file)
        
        processed_path = os.path.join(latest_path, f"{identifier}{self.processed_suffix}")
        debounce_path = os.path.join(latest_path, f"{identifier}.CELERY.CHECKED")

        is_processed = False
        if custom_processed_check:
            is_processed = custom_processed_check(identifier, latest_path)
        elif os.path.exists(processed_path):
            is_processed = True

        if is_processed:
            log.info(f"{self.processed_suffix} already exists for {latest_file} (or custom check passed)")
            return

        retry = 0
        if not skip_debounce:
            if os.path.exists(debounce_path):
                age = (datetime.now() - datetime.fromtimestamp(os.path.getmtime(debounce_path))).total_seconds()
                # Read the retry count from the file
                try:
                    with open(debounce_path, "r") as f:
                        lines = f.readlines()
                        for line in reversed(lines):
                            if line.startswith("Retry:"):
                                retry = int(line.split(":")[1].strip())
                                break
                            else :
                                retry = 0
                except Exception as e:
                    log.warning(f"Failed to read retry count from {debounce_path}: {e}")
                    retry = 0
                
                if age > self.debounce_seconds:
                    log.info(f"Identifier {identifier} pending for {age:.0f}s (> 300s), removing and re-triggering")
                    retry += 1
                    if retry > 1:
                        log.error(f"Identifier {identifier} has been retried {retry} times, marking container as unhealthy")
                        # Mark container as unhealthy by creating/touching the health check failure file
                        health_check_file = "/status/health_check_failure"
                        with open(health_check_file, "w") as hf:
                            hf.write(f"DataWatcher processing stuck for identifier {identifier} after {retry} retries\n")
                            hf.write(f"Timestamp: {datetime.now().isoformat()}\n")
                        os.remove(debounce_path)
                        return
                    os.remove(debounce_path)
                else:
                    log.info(f"Skipping {latest_file} - already checked within last {self.debounce_seconds}s")
                    return

            # Create debounce file
            os.makedirs(os.path.dirname(debounce_path), exist_ok=True)
            with open(debounce_path, "w") as f:
                f.write(f"Checked by Celery task at {datetime.now().isoformat()}\n")
                f.write(f"File: {latest_file}\n")
                f.write(f"Retry: {retry}\n")
            log.info(f"Created {debounce_path}")

        if dry_run:
            log.info(f"Dry run: would trigger task {task_name} for {identifier}")
            return

        if custom_action:
            custom_action(identifier, latest_file, latest_path)
            return

        if task_name:
            c = celery.get_instance()
            args = task_args
            if callable(task_args):
                args = task_args(identifier, latest_file, latest_path)
            
            c.celery_app.send_task(task_name, args=args)
            log.info(f"Triggered task {task_name} for {identifier}")
        
        if on_marker_creation:
             on_marker_creation(processed_path, identifier)

class DataWatcherStream(DataWatcher):
    def __init__(
        self,
        retention_hours: int = 72,
        time_format: str = "%Y%m%d%H%M",
        file_time_format: str = "%d-%m-%Y-%H-%M.tif",
        **kwargs
    ):
        super().__init__(**kwargs)
        self.retention_hours = retention_hours
        self.time_format = time_format
        self.file_time_format = file_time_format

    def _check_processed(self, identifier: str, path: str) -> bool:
        try:
            current_ready_dt = datetime.strptime(identifier, self.time_format)
        except ValueError:
            log.error(f"Could not parse timestamp from READY file: {identifier}")
            return False

        # Find all date-range .GEOSERVER.READY files
        geoserver_ready_files = [f for f in os.listdir(path) if f.endswith(self.processed_suffix)]
        
        if geoserver_ready_files:
            for gf in geoserver_ready_files:
                try:
                    date_range = gf.split(".")[0]
                    if "-" in date_range:
                        _, to_date = date_range.split("-")
                        end_dt = datetime.strptime(to_date, self.time_format)
                        if current_ready_dt <= end_dt:
                            return True
                    else:
                        # Old single date format
                        end_dt = datetime.strptime(date_range, self.time_format)
                        if current_ready_dt <= end_dt:
                            return True
                except ValueError:
                    log.warning(f"Could not parse {self.processed_suffix} file: {gf}")
        return False

    def _perform_action(self, identifier: str, latest_file: str, path: str, task_name: str, var_name: str) -> None:
        try:
            current_ready_dt = datetime.strptime(identifier, self.time_format)
        except ValueError:
            log.error(f"Could not parse timestamp from READY file: {identifier}")
            return

        # Custom Debounce Check using range-based CELERY.CHECKED files
        celery_checked_files = [f for f in os.listdir(path) if f.endswith(".CELERY.CHECKED")]
        for cf in celery_checked_files:
            try:
                date_range = cf.split(".")[0]
                if "-" in date_range:
                    _, to_date = date_range.split("-")
                    end_dt = datetime.strptime(to_date, self.time_format)
                    if current_ready_dt <= end_dt:
                        cf_path = os.path.join(path, cf)
                        age = (datetime.now() - datetime.fromtimestamp(os.path.getmtime(cf_path))).total_seconds()
                        retry = 0
                        # Read the retry count from the file
                        try:
                            with open(cf_path, "r") as f:
                                lines = f.readlines()
                                for line in reversed(lines):
                                    if line.startswith("Retry:"):
                                        retry = int(line.split(":")[1].strip())
                                        break
                        except Exception as e:
                            log.warning(f"Failed to read retry count from {cf_path}: {e}")
                            retry = 0
                        
                        if age > 300:
                            log.info(f"File range {date_range} pending for {age:.0f}s (> 300s), removing and re-triggering")
                            retry += 1
                            if retry > 1:
                                log.error(f"File range {date_range} has been retried {retry} times, marking container as unhealthy")
                                # Mark container as unhealthy by creating/touching the health check failure file
                                health_check_file = "/status/health_check_failure"
                                with open(health_check_file, "w") as hf:
                                    hf.write(f"DataWatcher {var_name} processing stuck for range {date_range} after {retry} retries\n")
                                    hf.write(f"Timestamp: {datetime.now().isoformat()}\n")
                                return
                            try:
                                os.remove(cf_path)
                                log.info(f"Deleted stale debounce file {cf}")
                            except OSError as e:
                                log.warning(f"Failed to delete stale debounce file {cf}: {e}")
                        else:
                            log.info(f"Skipping {latest_file} - covered by {cf} (checked {age:.0f}s ago)")
                            return
            except ValueError:
                continue

        start_dt = current_ready_dt - timedelta(hours=self.retention_hours)
        
        pending_filenames = []
        pending_dates = []
        
        temp_dt = start_dt
        while temp_dt <= current_ready_dt:
            expected_filename = temp_dt.strftime(self.file_time_format)
            expected_path = os.path.join(path, 'files', expected_filename)
            
            if os.path.exists(expected_path):
                pending_filenames.append(expected_filename)
                pending_dates.append(temp_dt)
            
            temp_dt += timedelta(minutes=1)
        
        if not pending_filenames:
            log.info(f"No pending files found for {var_name}")
            return
        
        log.info(f"Found {len(pending_filenames)} pending file(s) for {var_name}")
        
        min_date = min(pending_dates)
        max_date = max(pending_dates)
        date_range_str = f"{min_date.strftime(self.time_format)}-{max_date.strftime(self.time_format)}"
        celery_checked_path = os.path.join(path, f"{date_range_str}.CELERY.CHECKED")
        
        os.makedirs(os.path.dirname(celery_checked_path), exist_ok=True)
        with open(celery_checked_path, "w") as f:
            f.write(f"Checked by Celery task at {datetime.now().isoformat()}\n")
            f.write(f"Files: {len(pending_filenames)}\n")
            f.write(f"Retry: 0\n")
        log.info(f"Created {celery_checked_path}")

        if task_name:
            c = celery.get_instance()
            c.celery_app.send_task(
                task_name,
                args=(
                    var_name,
                    pending_filenames,
                    pending_dates,
                )
            )
            log.info(f"Triggered batch task {task_name} for {var_name} with {len(pending_filenames)} file(s)")

    def check_and_trigger(
        self,
        task_name: Optional[str] = None,
        var_name: Optional[str] = None,
        skip_debounce: bool = True,
        **kwargs
    ) -> None:
        super().check_and_trigger(
            task_name=None, # We handle triggering manually in _perform_action
            custom_processed_check=self._check_processed,
            custom_action=lambda id, f, p: self._perform_action(id, f, p, task_name, var_name),
            skip_debounce=skip_debounce,
            **kwargs
        )
