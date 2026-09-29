"""Windy discovery and ingestion entry points."""

import os
import re
from datetime import datetime

from restapi.connectors import celery
from restapi.env import Env
from restapi.utilities.logs import log

from .manifest import DatasetConfig
from .watcher import DataWatcher


class WindyIngestionAdapter:
    def __init__(self, config: DatasetConfig) -> None:
        self.config = config

    def discover(self, paths=None) -> None:
        from .registry import load_registry

        base_path = Env.get("WINDY_INGEST_BASE_PATH", "/windy")
        area = Env.get("WINDY_INGEST_AREA", "Italia")
        icon_folders = Env.get(
            "WINDY_INGEST_FOLDERS",
            "Windy-00-ICON_2I_all2km.web,Windy-12-ICON_2I_all2km.web",
        ).split(",")
        wrf_folders = Env.get(
            "WINDY_WRF_INGEST_FOLDERS", "Windy-00-WRF.web,Windy-12-WRF.web"
        ).split(",")
        if paths is None:
            paths = [os.path.join(base_path, folder.strip(), area) for folder in icon_folders if folder.strip()]
        wrf_paths = [path for path in paths if _is_wrf_path(path)]
        icon_paths = [path for path in paths if not _is_wrf_path(path)]
        for folder in wrf_folders:
            if folder.strip():
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
            celery.get_instance().celery_app.send_task(
                "check_latest_data_and_trigger_geoserver_import_mer_bolam",
                args=(Env.get("MER_DATA_PATH", "/shyfem"),),
            )
        except Exception as exc:
            log.error(f"Failed to enqueue chained MER check from windy task: {exc}")

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
