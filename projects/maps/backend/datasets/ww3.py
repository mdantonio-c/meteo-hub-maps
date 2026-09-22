"""WW3 forecast mosaic adapter."""

from pathlib import Path
from typing import Optional

from .cache import GWCInvalidator, TemporalCacheLayer
from .locking import DatasetLock
from .manifest import DatasetConfig


class WW3IngestionAdapter:
    """Own the WW3 run orchestration while retaining its existing processor."""

    def __init__(self, config: DatasetConfig) -> None:
        self.config = config

    def ingest(self, run_date: str) -> None:
        from restapi.env import Env
        from maps.tasks.ww3 import _ingest_ww3_layers
        from .markers import MarkerStore

        geoserver_url = Env.get(
            "GEOSERVER_URL", "http://geoserver.dockerized.io:8080/geoserver"
        )
        username = Env.get("GEOSERVER_ADMIN_USER", "")
        password = Env.get("GEOSERVER_ADMIN_PASSWORD", "")
        with DatasetLock(
            Path(Env.get("GEOSERVER_COPIES_PATH", "/geoserver_data/copies")),
            "ww3",
        ):
            layers = _ingest_ww3_layers(run_date, config=self.config)
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
                    "GeoWebCache truncation/seed failed for WW3 layers",
                    RuntimeWarning,
                )

            marker_path = Path(Env.get("WW3_DATA_PATH", "/ww3")) / "Mediterraneo"
            MarkerStore(marker_path).create(
                run_date,
                ".GEOSERVER.READY",
                f"Processed by GeoServer for run {run_date}\n",
            )
