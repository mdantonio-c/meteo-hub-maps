"""Celery entry point for Windy/WRF ingestion."""

from datetime import datetime

from restapi.connectors.celery import CeleryExt

from maps.datasets.registry import load_adapter


@CeleryExt.task(idempotent=True)
def update_geoserver_image_mosaic(
    self, geoserver_url, run, date=None, sld_directory="/SLDs",
    dataset_folder="ICON_2I_all2km", source_directory=None,
):
    dataset = "wrf" if dataset_folder == "WRF" else "icon"
    load_adapter(dataset).ingest(
        geoserver_url, run, date or datetime.now().strftime("%Y-%m-%d"),
        sld_directory, dataset_folder, source_directory,
    )
