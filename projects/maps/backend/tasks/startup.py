"""GeoServer/GWC startup initialization tasks.

This module runs once per worker process startup to ensure GeoServer and
GeoWebCache are correctly configured before any ingestion or cache tasks
execute. Typical responsibilities include:
- Recreating GWC gridsets that may have been lost on restart
- Ensuring TIME parameter filters exist for all temporal layers
- Enabling direct WMS integration and configurable per-layer disk quotas
- Syncing SLD styles from the mounted volume
"""

from restapi.connectors.celery import CeleryExt
from restapi.connectors import celery
from restapi.env import Env
from restapi.utilities.logs import log
import requests
from celery.signals import worker_init
from typing import List, Optional

from maps.datasets.cache import GWCInvalidator
from maps.datasets.geoserver_utils import update_slds_from_local_folders
from maps.utils.geoserver import GEOSERVER_REQUEST_TIMEOUT

GEOSERVER_URL = Env.get("GEOSERVER_URL", "http://geoserver.dockerized.io:8080/geoserver")
GEOSERVER_USER = Env.get("GEOSERVER_ADMIN_USER", "admin")
GEOSERVER_PASSWORD = Env.get("GEOSERVER_ADMIN_PASSWORD", "D3vMode!")
GEOSERVER_WORKSPACE = Env.get("GEOSERVER_WORKSPACE", "meteohub")
SLD_BASE_DIRECTORY = Env.get("SLD_BASE_DIRECTORY", "/SLDs")


def _get_all_layers(
    geoserver_url: str,
    username: str,
    password: str,
    workspace: str,
) -> List[str]:
    """Fetch all layer names in the workspace."""
    url = f"{geoserver_url}/rest/layers.json"
    try:
        response = requests.get(
            url,
            auth=(username, password),
            headers={"Accept": "application/json"},
            timeout=GEOSERVER_REQUEST_TIMEOUT,
        )
        if response.status_code != 200:
            log.error(
                f"Failed to list layers: HTTP {response.status_code} {response.text}"
            )
            return []
        data = response.json()
        layers = data.get("layers", {}).get("layer", [])
        if isinstance(layers, dict):
            layers = [layers]
        result = []
        for layer in layers:
            name = layer.get("name", "")
            if name.startswith(f"{workspace}:"):
                result.append(name[len(workspace) + 1 :])
        return result
    except requests.RequestException:
        log.exception("Failed to list GeoServer layers")
        return []


@CeleryExt.task(idempotent=True)
def initialize_geoserver(self) -> bool:
    """Initialize GeoServer and GWC configuration on worker startup.
    
    This task ensures that:
    1. GWC gridsets exist for all configured layers
    2. TIME parameter filters are configured for temporal layers
    3. SLD styles are synced from the mounted volume
    4. Each cached layer has an independent configurable LRU disk quota
    
    Returns True if successful, False otherwise.
    """
    log.info("Starting GeoServer/GWC startup initialization")
    
    if Env.get("GEOSERVER_GWC_ENABLED", "1") != "1":
        log.info("GWC is disabled; skipping startup initialization")
        return True
    
    invalidator = GWCInvalidator(
        geoserver_url=GEOSERVER_URL,
        username=GEOSERVER_USER,
        password=GEOSERVER_PASSWORD,
        workspace=GEOSERVER_WORKSPACE,
        enabled=True,
        timeout=GEOSERVER_REQUEST_TIMEOUT,
    )
    
    if not invalidator.disable_direct_wms_integration():
        log.error("Could not disable direct WMS-C integration with GeoServer WMS")
        return False

    layers = _get_all_layers(GEOSERVER_URL, GEOSERVER_USER, GEOSERVER_PASSWORD, GEOSERVER_WORKSPACE)
    if not invalidator.ensure_disk_quota(layers):
        log.error("Could not configure GWC disk quotas")
        return False
    if not layers:
        log.warning("No layers found in GeoServer workspace; skipping GWC initialization")
        return True
    
    log.info(f"Found {len(layers)} layers in workspace {GEOSERVER_WORKSPACE}")
    
    success_count = 0
    failure_count = 0
    
    for layer_name in layers:
        try:
            if invalidator.ensure_time_parameter_filter(layer_name):
                log.info(f"GWC configuration verified for layer: {layer_name}")
                success_count += 1
            else:
                log.error(f"GWC configuration failed for layer: {layer_name}")
                failure_count += 1
        except Exception:
            log.exception(f"GWC configuration exception for layer: {layer_name}")
            failure_count += 1
    
    log.info(
        f"GWC initialization complete: {success_count} succeeded, {failure_count} failed"
    )
    
    sld_dir = Env.get("SLD_BASE_DIRECTORY", "/SLDs")
    if sld_dir and Env.get("SYNC_SLDS_ON_STARTUP", "1") == "1":
        log.info(f"Syncing SLD styles from {sld_dir}")
        try:
            if update_slds_from_local_folders(
                sld_base_directory=sld_dir,
                geoserver_url=GEOSERVER_URL,
                username=GEOSERVER_USER,
                password=GEOSERVER_PASSWORD,
            ):
                log.info("SLD sync completed successfully")
            else:
                log.warning("SLD sync completed with errors")
        except Exception:
            log.exception("SLD sync failed")
    
    return failure_count == 0


@worker_init.connect(weak=False)
def on_worker_init(sender, **kwargs):
    """Run initialization when a worker starts.
    
    This signal fires once per worker process startup, before any tasks
    are processed. We send the initialization task asynchronously so it
    executes in the worker's task processing context.
    """
    if Env.get("GEOSERVER_GWC_ENABLED", "1") != "1":
        return
    
    log.info("Worker initialization hook triggered")
    try:
        app = celery.get_instance().celery_app
        result = initialize_geoserver.apply_async(queue="ingest")
        log.info(f"Startup initialization task sent: {result.id}")
    except Exception:
        log.exception("Failed to send startup initialization task")
