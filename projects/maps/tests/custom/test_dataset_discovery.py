"""Discovery keeps dataset-specific marker and task dispatch behavior."""

from unittest.mock import MagicMock

import pytest
from maps.datasets import sub_seasonal_discovery
from maps.datasets.behaviours import BulkOverrideAdapter, FifoGranulesAdapter
from maps.datasets.manifest import ManifestError, validate_manifest
from maps.datasets.monitoring import discovery_schedules
from maps.datasets.registry import DatasetRegistry, load_registry
from restapi.env import Env


def test_sub_seasonal_ignores_json_folder_and_dispatches_range(tmp_path, monkeypatch):
    (tmp_path / "20260928.READY").touch()
    (tmp_path / "json_weekly" / "week1").mkdir(parents=True)
    variable = tmp_path / "t2m" / "week1"
    variable.mkdir(parents=True)
    (variable / "2026-09-28.tif").touch()
    (variable / "2026-10-04.tiff").touch()
    celery_instance = MagicMock()
    monkeypatch.setattr(
        sub_seasonal_discovery.celery, "get_instance", lambda: celery_instance
    )

    sub_seasonal_discovery.check_latest_data_and_trigger_geoserver_import_sub_seasonal(
        str(tmp_path)
    )

    celery_instance.celery_app.send_task.assert_called_once_with(
        "update_geoserver_sub_seasonal_layers",
        args=("20260928", "20260928-20261004"),
    )
    assert (tmp_path / "20260928-20261004.CELERY.CHECKED").exists()
    assert not (tmp_path / "20260928-20261004.GEOSERVER.READY").exists()


def test_ww3_discovery_dispatches_latest_run_once(tmp_path, monkeypatch):
    (tmp_path / "20260927.READY").touch()
    (tmp_path / "20260928.READY").touch()
    celery_instance = MagicMock()
    from maps.datasets import watcher

    monkeypatch.setattr(watcher.celery, "get_instance", lambda: celery_instance)

    adapter = load_registry().adapter("ww3")
    adapter.discover(str(tmp_path))
    adapter.discover(str(tmp_path))

    celery_instance.celery_app.send_task.assert_called_once_with(
        "update_geoserver_ww3_layers", args=("20260928",)
    )


def test_seasonal_generic_adapter_uses_configured_publication(monkeypatch):
    from maps.datasets import seasonal_processing

    publish = MagicMock()
    monkeypatch.setattr(
        seasonal_processing, "update_geoserver_seasonal_layers", publish
    )
    adapter = load_registry().adapter("seasonal")
    adapter.ingest("20260928", geoserver_url="http://geoserver", username=None)
    publish.assert_called_once_with(
        None,
        "20260928",
        geoserver_url="http://geoserver",
        cache_config=adapter.config.geoserver["cache"],
    )


def test_default_bulk_dataset_discovers_from_manifest_and_publishes(
    tmp_path, monkeypatch
):
    dataset = {
        "id": "example",
        "kind": "forecast",
        "discovery": {
            "base_path_env": "EXAMPLE_DATA_PATH",
            "base_path_default": "/unused",
            "path_suffix": "region",
            "markers": {
                "ready_suffix": ".READY",
                "completed_suffix": ".GEOSERVER.READY",
            },
        },
        "ingestion": {
            "behaviour": "bulk_override",
        },
        "temporal": {
            "filename_regex": "([0-9]{8})",
            "filename_format": "yyyyMMdd",
            "timezone": "UTC",
        },
        "geoserver": {"workspace": "meteohub", "store_type": "ImageMosaic"},
        "endpoint": {"route": "/example"},
    }
    config = validate_manifest({"version": 1, "datasets": [dataset]})[0]
    assert config.discovery["task"] == "discover_dataset"
    assert config.ingestion["task"] == "ingest_dataset"
    path = tmp_path / "region"
    path.mkdir()
    (path / "20260928.READY").touch()
    monkeypatch.setattr(
        Env,
        "get",
        lambda key, default=None: (
            str(tmp_path) if key == "EXAMPLE_DATA_PATH" else default
        ),
    )
    celery_instance = MagicMock()
    from maps.datasets import behaviours, watcher

    monkeypatch.setattr(watcher.celery, "get_instance", lambda: celery_instance)
    adapter = BulkOverrideAdapter(config)
    adapter.discover()
    celery_instance.celery_app.send_task.assert_called_once_with(
        "ingest_dataset", args=("20260928", "example")
    )

    (path / "temperature").mkdir()
    (path / "temperature" / "20260928.tif").touch()
    publisher = MagicMock()
    monkeypatch.setattr(behaviours, "GeoServerPublisher", lambda *args: publisher)
    monkeypatch.setattr(
        behaviours, "atomic_copy_to_mosaic", lambda *args: str(tmp_path / "stage")
    )
    monkeypatch.setattr(behaviours, "write_temporal_config", lambda *args: None)
    monkeypatch.setattr(behaviours, "finalize_atomic_copy", lambda *args: None)
    chord = MagicMock()
    monkeypatch.setattr("maps.tasks.cache_control.schedule_cache_refresh_chord", chord)
    adapter.ingest("20260928")
    publisher.publish_mosaic.assert_called_once()
    assert chord.call_args.kwargs["ready_file"] == str(
        path / "20260928.GEOSERVER.READY"
    )
    assert not (path / "20260928.GEOSERVER.READY").exists()


def test_generic_schedules_are_unique_per_dataset(monkeypatch):
    from maps.datasets import monitoring

    configs = [
        MagicMock(identifier=name, discovery={"task": "discover_dataset"})
        for name in ("first", "second")
    ]
    registry = MagicMock()
    registry.list.return_value = configs
    monkeypatch.setattr(monitoring, "load_registry", lambda: registry)
    assert discovery_schedules() == (
        ("discover-first", "discover_dataset", ("first",)),
        ("discover-second", "discover_dataset", ("second",)),
    )
    client = MagicMock()
    monitoring.start_monitoring(client)
    assert [
        call.kwargs["args"] for call in client.create_crontab_task.call_args_list
    ] == [["first"], ["second"]]


def test_behaviour_manifest_rejects_unsafe_suffix_and_invalid_retention():
    dataset = {
        "id": "example",
        "kind": "forecast",
        "discovery": {
            "task": "discover_dataset",
            "base_path_env": "EXAMPLE_PATH",
            "base_path_default": "/example",
            "path_suffix": "../other",
            "markers": {
                "ready_suffix": ".READY",
                "completed_suffix": ".GEOSERVER.READY",
            },
        },
        "ingestion": {
            "behaviour": "fifo_granules",
            "task": "ingest_dataset",
            "retention": {"hours": 0},
        },
        "temporal": {
            "filename_regex": "([0-9]{8})",
            "filename_format": "yyyyMMdd",
            "timezone": "UTC",
        },
        "geoserver": {"workspace": "meteohub", "store_type": "ImageMosaic"},
        "endpoint": {"route": "/example"},
    }
    with pytest.raises(ManifestError) as exc:
        validate_manifest({"version": 1, "datasets": [dataset]})
    assert "ingestion.retention.hours" in str(exc.value)
    assert "discovery.path_suffix" in str(exc.value)


def test_fifo_applies_time_and_count_to_granule_timestamps(tmp_path):
    from datetime import datetime, timezone

    config = validate_manifest(
        {
            "version": 1,
            "datasets": [
                {
                    "id": "queue",
                    "kind": "observation",
                    "discovery": {
                        "task": "discover_dataset",
                        "base_path_env": "QUEUE_PATH",
                        "base_path_default": str(tmp_path),
                        "markers": {
                            "ready_suffix": ".READY",
                            "completed_suffix": ".GEOSERVER.READY",
                        },
                    },
                    "ingestion": {
                        "behaviour": "fifo_granules",
                        "task": "ingest_dataset",
                        "retention": {"hours": 4, "max_granules": 2},
                    },
                    "temporal": {
                        "filename_regex": "([0-9]{10})",
                        "filename_format": "yyyyMMddHH",
                        "timezone": "UTC",
                    },
                    "geoserver": {"workspace": "meteohub", "store_type": "ImageMosaic"},
                    "endpoint": {"route": "/queue"},
                }
            ],
        }
    )[0]
    adapter = FifoGranulesAdapter(config)
    granules = [
        (
            datetime(2026, 9, 28, hour, tzinfo=timezone.utc),
            tmp_path / f"20260928{hour:02}.tif",
        )
        for hour in (8, 9, 10, 12, 13)
    ]
    assert [item[0].hour for item in adapter._select(granules)] == [12, 13]
    config.ingestion["retention"]["max_granules"] = 5
    assert [item[0].hour for item in adapter._select(granules)] == [9, 10, 12, 13]


def test_behaviour_resolution_prefers_matching_dataset_specialization():
    existing = load_registry().get("radar")
    assert (
        load_registry().adapter_path("radar")
        == "maps.datasets.radar.RadarIngestionAdapter"
    )
    from dataclasses import replace

    bulk_radar = DatasetRegistry((replace(existing, adapter="bulk_override"),))
    assert (
        bulk_radar.adapter_path("radar")
        == "maps.datasets.behaviours.BulkOverrideAdapter"
    )
    unknown = DatasetRegistry((replace(existing, identifier="new-radar"),))
    assert (
        unknown.adapter_path("new-radar")
        == "maps.datasets.behaviours.FifoGranulesAdapter"
    )


def test_fifo_merges_existing_granules_and_invalidates_removed_times(
    tmp_path, monkeypatch
):
    from dataclasses import replace

    from maps.datasets import behaviours

    original = load_registry().get("radar")
    source = tmp_path / "source"
    (source / "rain").mkdir(parents=True)
    target = tmp_path / "copies" / "queue-rain"
    target.mkdir(parents=True)
    for hour in (8, 9):
        (target / f"20260928{hour:02}.tif").touch()
    (source / "rain" / "2026092810.tif").touch()
    config = replace(
        original,
        identifier="queue",
        adapter="fifo_granules",
        discovery={
            "base_path_env": "QUEUE_SOURCE",
            "base_path_default": str(source),
            "variables": ["rain"],
            "markers": {
                "ready_suffix": ".READY",
                "completed_suffix": ".GEOSERVER.READY",
            },
        },
        ingestion={"task": "ingest_dataset", "retention": {"max_granules": 2}},
        temporal={"filename_regex": "([0-9]{10})", "filename_format": "yyyyMMddHH"},
    )
    adapter = FifoGranulesAdapter(config)
    monkeypatch.setattr(adapter, "_target", lambda layer: target)
    publisher = MagicMock()
    monkeypatch.setattr(behaviours, "GeoServerPublisher", lambda *args: publisher)
    copy = MagicMock(return_value=str(tmp_path / "stage"))
    monkeypatch.setattr(behaviours, "atomic_copy_to_mosaic", copy)
    monkeypatch.setattr(behaviours, "write_temporal_config", lambda *args: None)
    monkeypatch.setattr(behaviours, "finalize_atomic_copy", lambda *args: None)
    chord = MagicMock()
    monkeypatch.setattr("maps.tasks.cache_control.schedule_cache_refresh_chord", chord)

    adapter.ingest("20260928")

    assert copy.call_args.args[1] == [
        str(target / "2026092809.tif"),
        str(source / "rain" / "2026092810.tif"),
    ]
    request = chord.call_args.args[0][0]
    assert request["times"] == ["2026-09-28T08:00:00Z", "2026-09-28T10:00:00Z"]
    assert request["warm_times"] == ["2026-09-28T10:00:00Z"]
    assert not (source / "20260928.GEOSERVER.READY").exists()
