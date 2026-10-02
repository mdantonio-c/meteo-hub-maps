from pathlib import Path

import pytest
from maps.datasets import cache
from maps.datasets.cache import GWCInvalidator
from maps.datasets.locking import DatasetLock
from maps.datasets.manifest import (
    DatasetConfig,
    ManifestError,
    load_manifest,
    validate_manifest,
)
from maps.datasets.markers import MarkerStore
from maps.datasets.paths import safe_dataset_file_path
from maps.datasets.registry import DatasetRegistry
from maps.datasets.temporal import write_temporal_config
from restapi.env import Env


def test_loads_windy_and_radar_manifest() -> None:
    path = Path(Env.get("DATASET_CONFIG_PATH", "/etc/meteohub/datasets.yml"))

    datasets = load_manifest(path)

    assert [dataset.identifier for dataset in datasets] == [
        "icon",
        "wrf",
        "radar",
        "ww3",
        "seasonal",
        "sub-seasonal",
        "marine",
    ]
    assert datasets[0].adapter == "bulk_override"
    assert datasets[1].adapter == "bulk_override"
    assert datasets[2].discovery["variables"] == ["sri", "srt"]


def test_allows_duplicate_route_templates() -> None:
    document = {
        "version": 1,
        "datasets": [
            {
                "id": "first",
                "kind": "forecast",
                "discovery": {
                    "task": "discover_dataset",
                    "base_path_env": "FIRST_PATH",
                    "base_path_default": "/first",
                    "markers": {
                        "ready_suffix": ".READY",
                        "completed_suffix": ".GEOSERVER.READY",
                    },
                },
                "ingestion": {"behaviour": "bulk_override", "task": "ingest_dataset"},
                "temporal": {
                    "filename_regex": "(.*)",
                    "filename_format": "yyyyMMddHH",
                    "timezone": "UTC",
                },
                "geoserver": {"workspace": "meteohub", "store_type": "ImageMosaic"},
                "endpoint": {"route": "/datasets/{dataset}"},
            },
            {
                "id": "second",
                "kind": "forecast",
                "discovery": {
                    "task": "discover_dataset",
                    "base_path_env": "SECOND_PATH",
                    "base_path_default": "/second",
                    "markers": {
                        "ready_suffix": ".READY",
                        "completed_suffix": ".GEOSERVER.READY",
                    },
                },
                "ingestion": {"behaviour": "bulk_override", "task": "ingest_dataset"},
                "temporal": {
                    "filename_regex": "(.*)",
                    "filename_format": "yyyyMMddHH",
                    "timezone": "UTC",
                },
                "geoserver": {"workspace": "meteohub", "store_type": "ImageMosaic"},
                "endpoint": {"route": "/datasets/{dataset}"},
            },
        ],
    }

    datasets = validate_manifest(document)
    assert len(datasets) == 2
    assert datasets[0].route == "/datasets/{dataset}"
    assert datasets[1].route == "/datasets/{dataset}"


def test_registry_rejects_unknown_dataset() -> None:
    registry = DatasetRegistry(
        load_manifest(
            Path(Env.get("DATASET_CONFIG_PATH", "/etc/meteohub/datasets.yml"))
        )
    )

    with pytest.raises(ManifestError, match="unknown dataset"):
        registry.get("missing")


def test_registry_resolves_configured_adapter() -> None:
    registry = DatasetRegistry(
        load_manifest(
            Path(Env.get("DATASET_CONFIG_PATH", "/etc/meteohub/datasets.yml"))
        )
    )

    assert registry.get("icon").adapter == "bulk_override"
    assert registry.get("wrf").adapter == "bulk_override"
    assert registry.adapter_path("radar") == "maps.datasets.radar.RadarIngestionAdapter"
    assert registry.adapter_path("ww3") == "maps.datasets.specialized.WW3Adapter"


def test_marker_store_creates_and_finds_markers(tmp_path: Path) -> None:
    store = MarkerStore(tmp_path / "Italia")

    marker = store.create("202501011200", ".READY", "ready\n")

    assert marker.read_text(encoding="utf-8") == "ready\n"
    assert store.exists("202501011200", ".READY")
    assert store.latest(".READY") == marker

    store.remove("202501011200", ".READY")
    assert not store.exists("202501011200", ".READY")


def test_temporal_config_writer_creates_geoserver_files(tmp_path: Path) -> None:
    write_temporal_config(tmp_path, r".*([0-9]{10}).*", "yyyyMMddHH")

    assert "TimestampFileNameExtractorSPI" in (
        tmp_path / "indexer.properties"
    ).read_text(encoding="utf-8")
    assert "format=yyyyMMddHH" in (tmp_path / "timeregex.properties").read_text(
        encoding="utf-8"
    )


def test_dataset_lock_is_reentrant_after_release(tmp_path: Path) -> None:
    with DatasetLock(tmp_path, "windy-icon-00"):
        assert (tmp_path / ".windy-icon-00.lock").exists()

    with DatasetLock(tmp_path, "windy-icon-00"):
        pass


def test_gwc_invalidator_is_noop_when_disabled() -> None:
    assert GWCInvalidator(
        "http://geoserver", "user", "password", "meteohub", enabled=False
    ).truncate("t2m")


def test_gwc_invalidator_adds_time_parameter_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        status_code = 200
        content = b"""<GeoServerLayer>
          <name>meteohub:layer</name>
          <parameterFilters>
            <styleParameterFilter><key>STYLES</key><defaultValue/></styleParameterFilter>
          </parameterFilters>
        </GeoServerLayer>"""

    put_calls = []

    def fake_get(*args, **kwargs):
        return Response()

    def fake_put(*args, **kwargs):
        put_calls.append((args, kwargs))
        return Response()

    monkeypatch.setattr(cache.requests, "get", fake_get)
    monkeypatch.setattr(cache.requests, "put", fake_put)
    monkeypatch.setattr(GWCInvalidator, "ensure_disk_quota", lambda *args: True)

    invalidator = GWCInvalidator(
        "http://geoserver", "user", "password", "meteohub", enabled=True
    )

    assert invalidator.ensure_time_parameter_filter("layer")
    assert put_calls[0][0][0] == "http://geoserver/gwc/rest/layers/meteohub:layer.xml"
    payload = put_calls[0][1]["data"]
    assert b"<regexParameterFilter><key>TIME</key>" in payload
    assert b"<regex>.*</regex>" in payload
    assert b"<gridSetName>EPSG:900913_1024</gridSetName>" in payload
    assert b"<expireCache>86400</expireCache>" in payload
    assert (
        f"<expireClients>{cache.GWC_CLIENT_EXPIRE_SECONDS}</expireClients>".encode()
        in payload
    )


def test_gwc_invalidator_keeps_existing_time_parameter_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        status_code = 200
        content = f"""<GeoServerLayer><gridSubsets><gridSubset>
          <gridSetName>EPSG:900913_1024</gridSetName>
        </gridSubset></gridSubsets><expireCache>86400</expireCache><expireClients>{cache.GWC_CLIENT_EXPIRE_SECONDS}</expireClients><parameterFilters>
          <regexParameterFilter><key>TIME</key><defaultValue/><regex>.*</regex></regexParameterFilter>
        </parameterFilters></GeoServerLayer>""".encode()

    monkeypatch.setattr(cache.requests, "get", lambda *args, **kwargs: Response())
    monkeypatch.setattr(GWCInvalidator, "ensure_disk_quota", lambda *args: True)
    monkeypatch.setattr(
        cache.requests,
        "put",
        lambda *args, **kwargs: pytest.fail("existing TIME filter must not be updated"),
    )

    invalidator = GWCInvalidator(
        "http://geoserver", "user", "password", "meteohub", enabled=True
    )

    assert invalidator.ensure_time_parameter_filter("layer")


def test_dataset_file_path_is_confined_to_dataset_root(tmp_path: Path) -> None:
    config = DatasetConfig(
        identifier="test",
        kind="observation",
        adapter="fifo_granules",
        endpoint={"operations": ["file_download"]},
        discovery={"base_path_default": str(tmp_path)},
        ingestion={},
        temporal={},
        geoserver={},
        raw={},
    )
    (tmp_path / "valid.tif").write_bytes(b"data")

    assert (
        safe_dataset_file_path(config, "valid.tif", lambda name, default: default)
        == (tmp_path / "valid.tif").resolve()
    )
    with pytest.raises(ManifestError, match="invalid dataset file path"):
        safe_dataset_file_path(config, "../outside.tif", lambda name, default: default)
