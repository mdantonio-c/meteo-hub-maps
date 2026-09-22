"""Windy forecast adapter seam.

The first migration keeps the established processing algorithm behind this
adapter while the low-level operations are progressively replaced by the
shared dataset modules.
"""

from .manifest import DatasetConfig
from .locking import DatasetLock
from .markers import MarkerStore
from pathlib import Path
from datetime import datetime


class WindyIngestionAdapter:
    """Delegate Windy processing through the dataset-owned interface."""

    def __init__(self, config: DatasetConfig) -> None:
        self.config = config

    def ingest(
        self,
        geoserver_url: str,
        run: str,
        date: str,
        sld_directory: str,
        dataset_folder: str,
    ) -> None:
        from restapi.env import Env

        # Import lazily so the adapter seam does not make the task module part
        # of manifest loading or backend startup.
        from maps.tasks.upload_image_mosaic import _ingest_windy_image_mosaic

        lock_root = Path(Env.get("GEOSERVER_COPIES_PATH", "/geoserver_data/copies"))
        lock_name = f"windy-{self.config.identifier}-{run}"
        with DatasetLock(lock_root, lock_name):
            _ingest_windy_image_mosaic(
                geoserver_url=geoserver_url,
                run=run,
                date=date,
                sld_directory=sld_directory,
                dataset_folder=dataset_folder,
                source_directory=str(
                    Path(Env.get("WINDY_INGEST_BASE_PATH", "/windy"))
                    / f"Windy-{run}-{dataset_folder}.web"
                    / Env.get("WINDY_INGEST_AREA", "Italia")
                ),
                config=self.config,
            )
            marker_path = Path(Env.get("WINDY_INGEST_BASE_PATH", "/windy"))
            marker_path = marker_path / f"Windy-{run}-{dataset_folder}.web" / Env.get(
                "WINDY_INGEST_AREA", "Italia"
            )
            MarkerStore(marker_path).create(
                f"{date}{run}",
                ".GEOSERVER.READY",
                f"Data: {date}{run}\nProcessed: {datetime.now().isoformat()}\n",
            )

            self._cleanup_old_stores(
                geoserver_url,
                Env.get("GEOSERVER_ADMIN_USER", ""),
                Env.get("GEOSERVER_ADMIN_PASSWORD", ""),
                date,
            )

    def _cleanup_old_stores(
        self,
        geoserver_url: str,
        username: str,
        password: str,
        date: str,
    ) -> None:
        from maps.tasks.geoserver_utils import cleanup_old_windy_stores

        workspace = str(self.config.geoserver.get("workspace", "meteohub"))
        try:
            cleanup_old_windy_stores(
                geoserver_url, username, password, date, workspace
            )
        except Exception:
            pass
