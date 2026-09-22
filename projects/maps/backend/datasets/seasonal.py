"""Seasonal full-replacement temporal mosaic adapter."""

from pathlib import Path

from .cache import GWCInvalidator, TemporalCacheLayer
from .locking import DatasetLock
from .manifest import DatasetConfig
from .markers import MarkerStore


class SeasonalIngestionAdapter:
    """Run seasonal replacement ingestion and publish readiness last."""

    def __init__(self, config: DatasetConfig) -> None:
        self.config = config

    def ingest(
        self,
        date: str,
        geoserver_url: str,
        username: str,
        password: str,
        sld_directory: str,
    ) -> None:
        from restapi.env import Env
        from maps.tasks.data_ready import _ingest_seasonal_layers

        base_path = Path(Env.get("SEASONAL_DATA_PATH", "/seasonal-aim"))
        copy_path = Path(Env.get("GEOSERVER_COPIES_PATH", "/geoserver_data/copies"))
        with DatasetLock(copy_path, "seasonal"):
            layers = _ingest_seasonal_layers(
                base_path=str(base_path),
                sld_directory=sld_directory,
                geoserver_url=geoserver_url,
                username=username,
                password=password,
                date=date,
                config=self.config,
            )
            invalidator = GWCInvalidator(
                geoserver_url,
                username,
                password,
                str(self.config.geoserver.get("workspace", "meteohub")),
                enabled=True,
            )
            ok = True
            for layer in layers:
                ok = invalidator.refresh_temporal_layer(
                    TemporalCacheLayer(layer, store_name=f"mosaic_{layer}")
                ) and ok
            if not ok:
                import warnings

                warnings.warn(
                    "GeoWebCache truncation/seed failed for seasonal layers",
                    RuntimeWarning,
                )
            MarkerStore(base_path).create(
                date,
                ".GEOSERVER.READY",
                f"Seasonal Data: {date}\n",
            )
