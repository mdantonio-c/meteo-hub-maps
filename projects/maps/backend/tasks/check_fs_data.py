"""Stable Celery task names for dataset discovery and marine ingestion."""

from maps.datasets.registry import load_adapter
from restapi.connectors.celery import CeleryExt


@CeleryExt.task(idempotent=True)
def check_latest_data_and_trigger_geoserver_import_windy(self, paths=None):
    load_adapter("icon").discover(paths)


@CeleryExt.task(idempotent=True)
def check_latest_data_and_trigger_geoserver_import_seasonal(self, seasonal_path=None):
    load_adapter("seasonal").discover(seasonal_path)


@CeleryExt.task(idempotent=True)
def check_latest_data_and_trigger_geoserver_import_radar(self, radar_path="/radar"):
    load_adapter("radar").discover(radar_path)


@CeleryExt.task(idempotent=True)
def check_latest_data_and_trigger_geoserver_import_sub_seasonal(
    self, sub_seasonal_path=None
):
    load_adapter("sub-seasonal").discover(sub_seasonal_path)


@CeleryExt.task(idempotent=True)
def check_latest_data_and_trigger_geoserver_import_ww3(self, ww3_path=None):
    load_adapter("ww3").discover(ww3_path)


@CeleryExt.task(idempotent=True)
def ingest_dataset(self, run, dataset_id):
    """Run the manifest-selected publication implementation for a READY run."""
    load_adapter(dataset_id).ingest(run)


@CeleryExt.task(idempotent=True)
def discover_dataset(self, dataset_id):
    """Discover READY runs using the manifest-selected adapter."""
    load_adapter(dataset_id).discover()


@CeleryExt.task(idempotent=True)
def check_latest_data_and_trigger_geoserver_import_mer_bolam(self, mer_base_path=None):
    load_adapter("marine").discover(mer_base_path)


@CeleryExt.task(idempotent=True)
def update_geoserver_mer_bolam_layer(
    self,
    source_dir,
    forcing_dir,
    forcing_name,
    variable_name,
    run_date,
):
    load_adapter("marine").ingest(
        source_dir, forcing_dir, forcing_name, variable_name, run_date
    )


@CeleryExt.task(idempotent=True)
def check_latest_data_and_trigger_thredds_ingestion(self):
    """No-op retained for stale periodic entries; THREDDS is disabled."""
