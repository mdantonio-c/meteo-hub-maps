"""Marine/SHYFEM forcing mosaic adapter."""

from pathlib import Path

from .cache import GWCInvalidator
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
                enabled=True,
            )
            filter_ok = invalidator.ensure_time_parameter_filter(layer_name)
            truncate_ok = invalidator.truncate(layer_name)
            times = invalidator.get_granule_times(layer_name, all_times=True)
            style_name = invalidator.get_default_style(layer_name)
            seed_ok = invalidator.seed(
                layer_name, wait=True, times=times, style_name=style_name
            )
            if not filter_ok or not truncate_ok or not seed_ok:
                import warnings

                warnings.warn(
                    f"GeoWebCache truncation/seed failed for {layer_name}",
                    RuntimeWarning,
                )
            _update_forcing_geoserver_ready_if_complete(
                forcing_dir, forcing_name, run_date
            )
