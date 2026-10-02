"""Publication overrides for datasets with nonstandard layouts or styles."""

from functools import lru_cache

from restapi.env import Env

from .behaviours import BulkOverrideAdapter
from .paths import dataset_base_path


@lru_cache(maxsize=1)
def _get_env_getter() -> callable:
    """Return a cached Env.get function for path resolution."""
    return Env.get


class SeasonalAdapter(BulkOverrideAdapter):
    def _get_base_path(self) -> str:
        """Resolve base path from manifest config with env var fallback."""
        return str(dataset_base_path(self.config, _get_env_getter()))

    def ingest(self, run, **kwargs):
        from .seasonal_processing import update_geoserver_seasonal_layers

        update_geoserver_seasonal_layers(
            None,
            run,
            base_path=self._get_base_path(),
            cache_config=self.config.geoserver.get("cache", {}),
            **{key: value for key, value in kwargs.items() if value is not None},
        )


class WW3Adapter(BulkOverrideAdapter):
    def _get_base_path(self) -> str:
        """Resolve base path from manifest config with env var fallback."""
        root = dataset_base_path(self.config, _get_env_getter())
        suffix = self.config.discovery.get("path_suffix", "")
        return str(root / suffix) if suffix else str(root)

    def ingest(self, run, **kwargs):
        from .ww3_processing import update_geoserver_ww3_layers

        update_geoserver_ww3_layers(
            None,
            run,
            base_path=self._get_base_path(),
            cache_config=self.config.geoserver.get("cache", {}),
        )
