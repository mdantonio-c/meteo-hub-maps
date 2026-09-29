"""Publication overrides for datasets with nonstandard layouts or styles."""

from .behaviours import BulkOverrideAdapter


class SeasonalAdapter(BulkOverrideAdapter):
    def ingest(self, run, **kwargs):
        from .seasonal_processing import update_geoserver_seasonal_layers

        update_geoserver_seasonal_layers(
            None,
            run,
            cache_config=self.config.geoserver.get("cache", {}),
            **{key: value for key, value in kwargs.items() if value is not None},
        )


class WW3Adapter(BulkOverrideAdapter):
    def ingest(self, run, **kwargs):
        from .ww3_processing import update_geoserver_ww3_layers

        update_geoserver_ww3_layers(
            None, run, cache_config=self.config.geoserver.get("cache", {})
        )
