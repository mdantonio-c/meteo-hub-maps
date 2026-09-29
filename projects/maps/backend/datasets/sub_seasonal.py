"""Sub-seasonal discovery and ingestion entry points."""

from .manifest import DatasetConfig


class SubSeasonalIngestionAdapter:
    def __init__(self, config: DatasetConfig) -> None:
        self.config = config

    def discover(self, sub_seasonal_path=None) -> None:
        from .discovery import check_latest_data_and_trigger_geoserver_import_sub_seasonal, SUB_SEASONAL_BASE_PATH

        check_latest_data_and_trigger_geoserver_import_sub_seasonal(
            None, sub_seasonal_path or SUB_SEASONAL_BASE_PATH
        )

    def ingest(self, run_date, range_str) -> None:
        from .sub_seasonal_processing import update_geoserver_sub_seasonal_layers

        update_geoserver_sub_seasonal_layers(
            None, run_date, range_str, cache_config=self.config.geoserver.get("cache", {})
        )
