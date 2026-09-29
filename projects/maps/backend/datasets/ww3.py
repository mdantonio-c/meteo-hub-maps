"""WW3 discovery and ingestion entry points."""

from .manifest import DatasetConfig


class WW3IngestionAdapter:
    def __init__(self, config: DatasetConfig) -> None:
        self.config = config

    def discover(self, ww3_path=None) -> None:
        from .discovery import check_latest_data_and_trigger_geoserver_import_ww3, WW3_BASE_PATH

        check_latest_data_and_trigger_geoserver_import_ww3(None, ww3_path or WW3_BASE_PATH)

    def ingest(self, run_date) -> None:
        from .ww3_processing import update_geoserver_ww3_layers

        update_geoserver_ww3_layers(None, run_date, cache_config=self.config.geoserver.get("cache", {}))
