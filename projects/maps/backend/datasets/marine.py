"""Marine forcing discovery and ingestion entry points."""

from functools import lru_cache

from restapi.env import Env

from .manifest import DatasetConfig
from .paths import dataset_base_path


@lru_cache(maxsize=1)
def _get_env_getter() -> callable:
    """Return a cached Env.get function for path resolution."""
    return Env.get


class MarineIngestionAdapter:
    def __init__(self, config: DatasetConfig) -> None:
        self.config = config

    def _get_base_path(self) -> str:
        """Resolve base path from manifest config with env var fallback."""
        return str(dataset_base_path(self.config, _get_env_getter()))

    def _get_forcings(self) -> list[str]:
        """Resolve forcings from manifest config."""
        discovery = self.config.discovery
        env_name = discovery.get("forcings_env")
        if env_name:
            forcings_str = Env.get(env_name, "BOLAM,ECMWF,ICON")
        else:
            forcings_str = "BOLAM,ECMWF,ICON"
        return [
            forcing.strip().upper()
            for forcing in forcings_str.split(",")
            if forcing.strip()
        ]

    def discover(self, mer_base_path=None) -> None:
        from .marine_processing import (
            check_latest_data_and_trigger_geoserver_import_mer_bolam,
        )

        check_latest_data_and_trigger_geoserver_import_mer_bolam(
            mer_base_path=mer_base_path if mer_base_path is not None else self._get_base_path(),
            mer_forcings=self._get_forcings(),
        )

    def ingest(
        self, source_dir, forcing_dir, forcing_name, variable_name, run_date
    ) -> None:
        from .marine_processing import update_geoserver_mer_bolam_layer

        update_geoserver_mer_bolam_layer(
            None,
            source_dir,
            forcing_dir,
            forcing_name,
            variable_name,
            run_date,
            cache_config=self.config.geoserver.get("cache", {}),
        )
