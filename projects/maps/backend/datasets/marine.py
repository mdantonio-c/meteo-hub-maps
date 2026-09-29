"""Marine forcing discovery and ingestion entry points."""

from .manifest import DatasetConfig


class MarineIngestionAdapter:
    def __init__(self, config: DatasetConfig) -> None:
        self.config = config

    def discover(self, mer_base_path=None) -> None:
        from .marine_processing import (
            MER_BASE_PATH,
            check_latest_data_and_trigger_geoserver_import_mer_bolam,
        )

        check_latest_data_and_trigger_geoserver_import_mer_bolam(
            mer_base_path if mer_base_path is not None else MER_BASE_PATH
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
