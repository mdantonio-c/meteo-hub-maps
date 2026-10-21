"""Shared HTTP timeout policy for GeoServer REST and GeoWebCache calls."""

import os
from typing import Tuple


GEOSERVER_REQUEST_TIMEOUT_SECONDS = float(
    os.environ.get("GEOSERVER_REQUEST_TIMEOUT_SECONDS", "600")
)
GEOSERVER_REQUEST_TIMEOUT: Tuple[float, float] = (10.0, GEOSERVER_REQUEST_TIMEOUT_SECONDS)
