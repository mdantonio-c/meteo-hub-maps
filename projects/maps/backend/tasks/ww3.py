"""Celery entry point for WW3 ingestion."""

from restapi.connectors.celery import CeleryExt

from maps.datasets.registry import load_adapter


@CeleryExt.task(idempotent=True)
def update_geoserver_ww3_layers(self, run_date):
    load_adapter("ww3").ingest(run_date)
