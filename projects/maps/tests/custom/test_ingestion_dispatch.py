"""Keep scheduled Celery names wired to the manifest-selected dataset workflows."""

from unittest.mock import MagicMock, patch
from importlib import import_module
from flask import Flask
from restapi.connectors.celery import CeleryExt

from maps.datasets.monitoring import discovery_tasks, start_monitoring, stop_monitoring
from maps.datasets.registry import load_registry
from maps.tasks import check_fs_data, data_ready, radar, sub_seasonal, upload_image_mosaic, ww3


def test_registry_resolves_live_adapters_and_ingestion_tasks():
    registry = load_registry()
    for config in registry.list():
        adapter = registry.adapter(config.identifier)
        assert adapter.config is config
        assert callable(adapter.discover)
        assert callable(adapter.ingest)
        assert registry.ingestion_task(config.identifier).startswith("update_geoserver_")


def test_existing_celery_names_delegate_to_dataset_adapters(monkeypatch):
    monkeypatch.setattr(CeleryExt, "app", Flask(__name__))
    adapter = MagicMock()
    with patch("maps.tasks.check_fs_data.load_adapter", return_value=adapter) as load:
        check_fs_data.check_latest_data_and_trigger_geoserver_import_windy.run(paths=["/windy"])
        load.assert_called_once_with("icon")
        adapter.discover.assert_called_once_with(["/windy"])

    adapter.reset_mock()
    with patch("maps.tasks.check_fs_data.load_adapter", return_value=adapter) as load:
        check_fs_data.update_geoserver_mer_bolam_layer.run(
            "/source", "/forcing", "BOLAM", "wl", "20260928"
        )
        load.assert_called_once_with("marine")
        adapter.ingest.assert_called_once_with(
            "/source", "/forcing", "BOLAM", "wl", "20260928"
        )

    for task, dataset, args in (
        (radar.update_geoserver_radar_layers, "radar", ("sri", ["file.tif"], ["202609280930"])),
        (ww3.update_geoserver_ww3_layers, "ww3", ("20260928",)),
        (sub_seasonal.update_geoserver_sub_seasonal_layers, "sub-seasonal", ("20260928", "20260928-20261004")),
        (data_ready.update_geoserver_seasonal_layers, "seasonal", ("20260928",)),
        (upload_image_mosaic.update_geoserver_image_mosaic, "wrf", ("http://geoserver", "12", "20260928", "/SLDs", "WRF", "/windy/wrf")),
    ):
        adapter.reset_mock()
        with patch.object(import_module(task.run.__module__), "load_adapter", return_value=adapter) as load:
            task.run(*args)
        load.assert_called_once_with(dataset)
        assert adapter.ingest.called, dataset


def test_monitoring_uses_unique_manifest_adapters():
    assert len(discovery_tasks()) == 6  # ICON and WRF share one watcher
    client = MagicMock()
    start_monitoring(client)
    assert client.create_crontab_task.call_count == 6
    client.get_periodic_task.return_value = True
    assert stop_monitoring(client)
    assert client.delete_periodic_task.call_count == 6
