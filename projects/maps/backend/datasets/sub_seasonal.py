"""Sub-seasonal forecast mosaic adapter."""

from pathlib import Path

from .cache import GWCInvalidator, TemporalCacheLayer
from .locking import DatasetLock
from .manifest import DatasetConfig
from .markers import MarkerStore


class SubSeasonalIngestionAdapter:
    """Run sub-seasonal variable/value ingestion and publish readiness last."""

    def __init__(self, config: DatasetConfig) -> None:
        self.config = config

    def ingest(
        self,
        run_date: str,
        range_str: str,
        geoserver_url: str,
        username: str,
        password: str,
        sld_directory: str,
    ) -> None:
        from restapi.env import Env
        from maps.tasks.sub_seasonal import _ingest_sub_seasonal_layers

        base_path = Path(Env.get("SUB_SEASONAL_DATA_PATH", "/sub-seasonal-aim"))
        copy_path = Path(Env.get("GEOSERVER_COPIES_PATH", "/geoserver_data/copies"))
        with DatasetLock(copy_path, "sub-seasonal"):
            layers = _ingest_sub_seasonal_layers(
                run_date=run_date,
                range_str=range_str,
                base_path=str(base_path),
                geoserver_url=geoserver_url,
                username=username,
                password=password,
                sld_directory=sld_directory,
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
                    TemporalCacheLayer(layer, store_name=f"mosaic-{layer}")
                ) and ok
            if not ok:
                import warnings

                warnings.warn(
                    "GeoWebCache truncation/seed failed for sub-seasonal layers",
                    RuntimeWarning,
                )
            MarkerStore(base_path).create(
                range_str,
                ".GEOSERVER.READY",
                f"Run: {run_date}\nRange: {range_str}\n",
            )
