"""Radar discovery and rolling-window ingestion entry points."""

import os
from functools import lru_cache
from pathlib import Path

from restapi.env import Env
from restapi.utilities.logs import log

from .manifest import DatasetConfig
from .paths import dataset_base_path
from .watcher import DataWatcherStream


@lru_cache(maxsize=1)
def _get_env_getter() -> callable:
    """Return a cached Env.get function for path resolution."""
    return Env.get


class RadarIngestionAdapter:
    def __init__(self, config: DatasetConfig) -> None:
        self.config = config

    def _get_base_path(self) -> Path:
        """Resolve base path from manifest config with env var fallback."""
        return dataset_base_path(self.config, _get_env_getter())

    def _get_retention_hours(self) -> int:
        """Resolve retention hours from manifest config."""
        retention = self.config.ingestion.get("retention", {})
        return retention.get("hours", 72)

    def _get_variables(self) -> list[str]:
        """Resolve variables from manifest config."""
        return self.config.discovery.get("variables", ["sri", "srt"])

    def discover(self, radar_path=None) -> None:
        from .registry import load_registry

        if radar_path is None:
            radar_path = str(self._get_base_path())
        
        if not os.path.exists(radar_path):
            candidates = (radar_path, "/data/radar", os.path.join(os.getcwd(), "data/radar"))
            radar_path = next((path for path in candidates if os.path.exists(path)), None)
        if not radar_path:
            log.warning("Radar path does not exist")
            return
        task_name = load_registry().ingestion_task("radar")
        for variable in self._get_variables():
            var_path = os.path.join(radar_path, variable)
            if not os.path.exists(var_path):
                log.warning(f"Radar variable path does not exist: {var_path}")
                continue
            DataWatcherStream(
                paths=var_path,
                ready_suffix=".READY",
                processed_suffix=".GEOSERVER.READY",
                debounce_seconds=1800,
                retention_hours=self._get_retention_hours(),
                sort_key=lambda name: name,
                identifier_extractor=lambda name: name.split(".")[0],
            ).check_and_trigger(task_name=task_name, var_name=variable)
        log.info("Finished checking radar data")

    def ingest(
        self, variable, filenames, dates, geoserver_url=None,
        username=None, password=None, sld_directory=None, cache_config=None,
    ) -> None:
        from .radar_processing import update_geoserver_radar_layers

        kwargs = {"cache_config": cache_config if cache_config is not None else self.config.geoserver.get("cache", {})}
        if geoserver_url is not None:
            kwargs.update(geoserver_url=geoserver_url)
        if username is not None:
            kwargs.update(username=username)
        if password is not None:
            kwargs.update(password=password)
        if sld_directory is not None:
            kwargs.update(sld_directory=sld_directory)
        update_geoserver_radar_layers(None, variable, filenames, dates, **kwargs)
