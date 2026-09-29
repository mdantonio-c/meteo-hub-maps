"""Seasonal discovery and ingestion entry points."""

from restapi.utilities.logs import log

from .manifest import DatasetConfig
from .watcher import DataWatcher


class SeasonalIngestionAdapter:
    def __init__(self, config: DatasetConfig) -> None:
        self.config = config

    def discover(self, seasonal_path="/seasonal-aim") -> None:
        from .registry import load_registry

        DataWatcher(paths=seasonal_path).check_and_trigger(
            task_name=load_registry().ingestion_task("seasonal"),
            task_args=lambda identifier, filename, path: (identifier,),
        )
        log.info("Finished checking seasonal data")

    def ingest(self, date, geoserver_url=None, username=None, password=None, sld_directory=None) -> None:
        from .seasonal_processing import update_geoserver_seasonal_layers

        kwargs = {"date": date, "sld_directory": sld_directory,
                  "cache_config": self.config.geoserver.get("cache", {})}
        if geoserver_url is not None:
            kwargs.update(geoserver_url=geoserver_url)
        if username is not None:
            kwargs.update(username=username)
        if password is not None:
            kwargs.update(password=password)
        update_geoserver_seasonal_layers(None, **kwargs)
