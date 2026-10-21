"""Celery entry point for sub-seasonal ingestion."""

from restapi.connectors.celery import CeleryExt

from maps.datasets.registry import load_adapter


@CeleryExt.task(idempotent=True)
def update_geoserver_sub_seasonal_layers(self, run_date, range_str):
    load_adapter("sub-seasonal").ingest(run_date, range_str)
