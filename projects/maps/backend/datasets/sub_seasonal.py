"""Sub-seasonal discovery and ingestion entry points."""

from functools import lru_cache

from restapi.env import Env

from .manifest import DatasetConfig
from .paths import dataset_base_path


@lru_cache(maxsize=1)
def _get_env_getter() -> callable:
    """Return a cached Env.get function for path resolution."""
    return Env.get


class SubSeasonalIngestionAdapter:
    def __init__(self, config: DatasetConfig) -> None:
        self.config = config

    def _get_base_path(self) -> str:
        """Resolve base path from manifest config with env var fallback."""
        return str(dataset_base_path(self.config, _get_env_getter()))

    def discover(self, sub_seasonal_path=None) -> None:
        from .sub_seasonal_discovery import (
            check_latest_data_and_trigger_geoserver_import_sub_seasonal,
        )

        check_latest_data_and_trigger_geoserver_import_sub_seasonal(
            sub_seasonal_path
            if sub_seasonal_path is not None
            else self._get_base_path()
        )

    def ingest(self, run_date, range_str) -> None:
        from .sub_seasonal_processing import update_geoserver_sub_seasonal_layers

        update_geoserver_sub_seasonal_layers(
            None,
            run_date,
            range_str,
            cache_config=self.config.geoserver.get("cache", {}),
        )
