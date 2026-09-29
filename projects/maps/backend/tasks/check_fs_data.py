"""Stable Celery task names for dataset discovery and marine ingestion."""

from restapi.connectors.celery import CeleryExt

from maps.datasets.registry import load_adapter


@CeleryExt.task(idempotent=True)
def check_latest_data_and_trigger_geoserver_import_windy(self, paths=None):
    load_adapter("icon").discover(paths)


@CeleryExt.task(idempotent=True)
def check_latest_data_and_trigger_geoserver_import_seasonal(self, seasonal_path="/seasonal-aim"):
    load_adapter("seasonal").discover(seasonal_path)


@CeleryExt.task(idempotent=True)
def check_latest_data_and_trigger_geoserver_import_radar(self, radar_path="/radar"):
    load_adapter("radar").discover(radar_path)


@CeleryExt.task(idempotent=True)
def check_latest_data_and_trigger_geoserver_import_sub_seasonal(self, sub_seasonal_path=None):
    load_adapter("sub-seasonal").discover(sub_seasonal_path)


@CeleryExt.task(idempotent=True)
def check_latest_data_and_trigger_geoserver_import_ww3(self, ww3_path=None):
    load_adapter("ww3").discover(ww3_path)


@CeleryExt.task(idempotent=True)
def check_latest_data_and_trigger_geoserver_import_mer_bolam(self, mer_base_path=None):
    load_adapter("marine").discover(mer_base_path)


@CeleryExt.task(idempotent=True)
def update_geoserver_mer_bolam_layer(
    self, source_dir, forcing_dir, forcing_name, variable_name, run_date,
):
    load_adapter("marine").ingest(
        source_dir, forcing_dir, forcing_name, variable_name, run_date
    )


@CeleryExt.task(idempotent=True)
def check_latest_data_and_trigger_thredds_ingestion(self):
    """No-op retained for stale periodic entries; THREDDS is disabled."""
