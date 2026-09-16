"""Radar sliding-window ingestion adapter seam."""

from typing import Any, List, Optional

from .manifest import DatasetConfig


class RadarIngestionAdapter:
    """Delegate radar batches through the dataset-owned interface."""

    def __init__(self, config: DatasetConfig) -> None:
        self.config = config

    def ingest(
        self,
        variable: str,
        filenames: Any,
        dates: Any,
        geoserver_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        sld_directory: Optional[str] = None,
    ) -> None:
        from maps.tasks.radar import _ingest_radar_layers

        # Resolve SLD name from manifest config
        sld_name = self.config.resolve_sld(variable=variable)

        _ingest_radar_layers(
            variable=variable,
            filenames=filenames,
            dates=dates,
            geoserver_url=geoserver_url,
            username=username,
            password=password,
            sld_directory=sld_directory,
            sld_name=sld_name,
        )
