"""Celery entry point for radar ingestion."""

from restapi.connectors.celery import CeleryExt

from maps.datasets.registry import load_adapter


@CeleryExt.task(idempotent=True)
def update_geoserver_radar_layers(
    self, variable, filenames, dates, geoserver_url=None,
    username=None, password=None, sld_directory=None, cache_config=None,
):
    load_adapter("radar").ingest(
        variable, filenames, dates, geoserver_url,
        username, password, sld_directory, cache_config,
    )
