"""Windy discovery and ingestion entry points."""

import os
import re
from datetime import datetime
from functools import lru_cache
from typing import Any

from restapi.connectors import celery
from restapi.env import Env
from restapi.utilities.logs import log

from .manifest import DatasetConfig
from .watcher import DataWatcher


@lru_cache(maxsize=1)
def _get_env_getter() -> callable:
    """Return a cached Env.get function for path resolution."""
    return Env.get


class WindyIngestionAdapter:
    def __init__(self, config: DatasetConfig) -> None:
        self.config = config

    def _get_base_path(self) -> str:
        """Resolve base path from manifest config with env var fallback."""
        discovery = self.config.discovery
        env_name = discovery.get("base_path_env")
        default = discovery.get("base_path_default", "/windy")
        env_get = _get_env_getter()
        if env_name:
            return env_get(env_name, default)
        return default

    def _get_area(self) -> str:
        """Resolve area from manifest config."""
        return self.config.discovery.get("area", "Italia")

    def _get_ingest_folders(self) -> list[str]:
        """Resolve ingest folders from manifest folder_pattern."""
        folder_pattern = self.config.discovery.get("folder_pattern", "Windy-{run}-ICON_2I_all2km.web")
        runs = self.config.discovery.get("runs", ["00", "12"])
        folders = []
        for run in runs:
            folders.append(folder_pattern.format(run=run))
        return folders

    def discover(self, paths=None) -> None:
        from .registry import load_registry

        base_path = self._get_base_path()
        area = self._get_area()
        icon_folders = self._get_ingest_folders()
        
        if paths is None:
            paths = [os.path.join(base_path, folder.strip(), area) for folder in icon_folders if folder.strip()]
        wrf_paths = [path for path in paths if _is_wrf_path(path)]
        icon_paths = [path for path in paths if not _is_wrf_path(path)]
        
        for folder in icon_folders:
            if folder.strip() and "WRF" in folder.upper():
                path = os.path.join(base_path, folder.strip(), area)
                if path not in wrf_paths:
                    wrf_paths.append(path)

        def task_args(identifier, filename, path):
            return (
                Env.get("GEOSERVER_URL", "http://geoserver.dockerized.io:8080/geoserver"),
                identifier[8:10], identifier[:8], "/SLDs",
                _extract_dataset_from_path(path), path,
            )

        registry = load_registry()
        for dataset_id, folders in (("icon", icon_paths), ("wrf", wrf_paths)):
            if not folders:
                continue
            watcher = DataWatcher(
                paths=folders,
                sort_key=lambda name: datetime.strptime(name.split(".")[0], "%Y%m%d%H"),
                identifier_extractor=lambda name: name.split(".")[0],
            )
            watcher.check_and_trigger(
                task_name=registry.ingestion_task(dataset_id), task_args=task_args
            )

        # Retain the additional MER scan for stale/missing periodic entries.
        try:
            from .registry import load_registry as load_dataset_registry
            mer_config = load_dataset_registry().get("marine")
            mer_base_path = self._resolve_dataset_path(mer_config)
            celery.get_instance().celery_app.send_task(
                "check_latest_data_and_trigger_geoserver_import_mer_bolam",
                args=(str(mer_base_path),),
            )
        except Exception as exc:
            log.error(f"Failed to enqueue chained MER check from windy task: {exc}")

    def _resolve_dataset_path(self, config: DatasetConfig) -> str:
        """Resolve dataset base path from manifest config."""
        from .paths import dataset_base_path
        return dataset_base_path(config, Env.get)

    def ingest(
        self, geoserver_url, run, date, sld_directory="/SLDs",
        dataset_folder="ICON_2I_all2km", source_directory=None,
    ) -> None:
        from .windy_processing import update_geoserver_image_mosaic

        update_geoserver_image_mosaic(
            None, geoserver_url, run, date, sld_directory,
            dataset_folder, source_directory,
            cache_config=self.config.geoserver.get("cache", {}),
        )


def _extract_dataset_from_path(path: str) -> str:
    match = re.match(r"^Windy-(\d{2})-(.+)\.web$", os.path.basename(os.path.dirname(path)))
    if match:
        return match.group(2)
    log.warning(f"Could not parse windy dataset from path: {path}. Falling back to ICON_2I_all2km")
    return "ICON_2I_all2km"


def _is_wrf_path(path: str) -> bool:
    return _extract_dataset_from_path(path).upper() == "WRF"
