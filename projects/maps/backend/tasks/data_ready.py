"""Celery entry points for seasonal ingestion and SLD synchronization."""

from datetime import datetime

from restapi.connectors.celery import CeleryExt

from maps.datasets.registry import load_adapter


@CeleryExt.task(idempotent=True)
def update_geoserver_seasonal_layers(
    self=None, date=None, geoserver_url=None, username=None, password=None,
    sld_directory=None,
):
    load_adapter("seasonal").ingest(
        date or datetime.now().strftime("%Y%m%d"),
        geoserver_url, username, password, sld_directory,
    )


@CeleryExt.task(idempotent=True)
def update_slds_from_local(self, geoserver_url=None, username=None, password=None, sld_base_directory="/SLDs"):
    from maps.datasets.seasonal_processing import update_slds_from_local as sync_styles

    kwargs = {"sld_base_directory": sld_base_directory}
    if geoserver_url is not None:
        kwargs.update(geoserver_url=geoserver_url, username=username, password=password)
    sync_styles(None, **kwargs)
