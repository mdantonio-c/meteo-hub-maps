"""Marine/SHYFEM forcing mosaic adapter."""

from pathlib import Path

from .cache import GWCInvalidator, TemporalCacheLayer
from .locking import DatasetLock
from .manifest import DatasetConfig


class MarineIngestionAdapter:
    """Ingest one forcing variable while preserving forcing-level markers."""

    def __init__(self, config: DatasetConfig) -> None:
        self.config = config

    def ingest(
        self,
        source_dir: str,
        forcing_dir: str,
        forcing_name: str,
        variable_name: str,
        run_date: str,
    ) -> None:
        from restapi.env import Env
        from maps.tasks.check_fs_data import (
            _ingest_mer_layer,
            _update_forcing_geoserver_ready_if_complete,
        )

        geoserver_url = Env.get(
            "GEOSERVER_URL", "http://geoserver.dockerized.io:8080/geoserver"
        )
        username = Env.get("GEOSERVER_ADMIN_USER", "")
        password = Env.get("GEOSERVER_ADMIN_PASSWORD", "")
        copy_path = Path(Env.get("GEOSERVER_COPIES_PATH", "/geoserver_data/copies"))
        with DatasetLock(copy_path, f"marine-{forcing_name}"):
            layer_name = f"SHYFEM-{forcing_name}-{variable_name}"
            if not _ingest_mer_layer(
                source_dir=source_dir,
                forcing_dir=forcing_dir,
                forcing_name=forcing_name,
                variable_name=variable_name,
                run_date=run_date,
            ):
                raise RuntimeError(
                    f"Marine ingestion failed for {forcing_name}/{variable_name}"
                )
            invalidator = GWCInvalidator(
                geoserver_url,
                username,
                password,
                str(self.config.geoserver.get("workspace", "meteohub")),
                enabled=bool(
                    self.config.geoserver.get("cache", {}).get("eligible", True)
                ),
                zoom_start=self.config.geoserver.get("cache", {}).get("zoom_start"),
                zoom_stop=self.config.geoserver.get("cache", {}).get("zoom_stop"),
            )
            cache_ok = invalidator.refresh_temporal_layer(
                TemporalCacheLayer(layer_name, store_name=f"mosaic_{layer_name}")
            )
            if not cache_ok:
                import warnings

                warnings.warn(
                    f"GeoWebCache truncation/seed failed for {layer_name}",
                    RuntimeWarning,
                )
            _update_forcing_geoserver_ready_if_complete(
                forcing_dir, forcing_name, run_date
            )
