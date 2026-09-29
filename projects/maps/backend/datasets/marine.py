"""Marine forcing discovery and ingestion entry points."""

from .manifest import DatasetConfig


class MarineIngestionAdapter:
    def __init__(self, config: DatasetConfig) -> None:
        self.config = config

    def discover(self, mer_base_path=None) -> None:
        from .discovery import check_latest_data_and_trigger_geoserver_import_mer_bolam, MER_BASE_PATH

        check_latest_data_and_trigger_geoserver_import_mer_bolam(None, mer_base_path or MER_BASE_PATH)

    def ingest(self, source_dir, forcing_dir, forcing_name, variable_name, run_date) -> None:
        from .discovery import update_geoserver_mer_bolam_layer

        update_geoserver_mer_bolam_layer(
            None, source_dir, forcing_dir, forcing_name, variable_name, run_date,
            cache_config=self.config.geoserver.get("cache", {}),
        )
