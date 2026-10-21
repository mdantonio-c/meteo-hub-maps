"""Periodic maintenance for GeoWebCache's parameter metadata."""

from pathlib import Path
from typing import Dict

from maps.datasets.cache_cleanup import cleanup_parameter_files
from restapi.connectors.celery import CeleryExt
from restapi.env import Env


@CeleryExt.task(idempotent=True)
def cleanup_gwc_parameters(self) -> Dict[str, int]:
    """Remove expired or orphaned parameters files from the shared GWC volume."""
    if Env.get("GEOSERVER_GWC_ENABLED", "1") != "1":
        return {"scanned": 0, "expired": 0, "orphaned": 0, "errors": 0}
    cache_root = Path(Env.get("GEOSERVER_DATA_PATH", "/geoserver_data")) / "gwc"
    return cleanup_parameter_files(cache_root)
