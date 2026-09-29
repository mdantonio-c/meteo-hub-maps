"""Status is based on ingestion markers, including their written metadata."""

from pathlib import Path

import pytest
from maps.datasets.manifest import load_manifest
from maps.datasets.status import ingestion_status
from restapi.exceptions import NotFound


@pytest.fixture
def configs():
    return {
        config.identifier: config
        for config in load_manifest()
    }


def _configure(monkeypatch, config, root):
    monkeypatch.setenv(config.discovery["base_path_env"], str(root))


def test_windy_scans_each_run_area_and_ignores_old_checked(tmp_path, monkeypatch, configs):
    config = configs["wrf"]
    _configure(monkeypatch, config, tmp_path)
    area = tmp_path / "Windy-00-WRF.web" / "Italia"
    area.mkdir(parents=True)
    (area / "2026092800.GEOSERVER.READY").write_text("Data: 2026092800\nProcessed: 2026-09-28T10:00:00\n")
    (area / "2026092800.CELERY.CHECKED").touch()

    result = ingestion_status(config)
    assert result["status"] == "ready"
    assert result["lastRun"] == "2026092800"
    assert result["lastUpdate"] == "2026-09-28T10:00:00"
    assert result["pendingImport"] is None

    next_area = tmp_path / "Windy-12-WRF.web" / "Italia"
    next_area.mkdir(parents=True)
    (next_area / "2026092912.CELERY.CHECKED").touch()
    result = ingestion_status(config)
    assert result["status"] == "ready"
    assert result["pendingImport"]["run"] == "2026092912"


def test_radar_range_metadata_and_pending_chunk(tmp_path, monkeypatch, configs):
    config = configs["radar"]
    _configure(monkeypatch, config, tmp_path)
    sri = tmp_path / "sri"
    sri.mkdir()
    (sri / "202609261230-202609291230.GEOSERVER.READY").write_text(
        "Processed by GeoServer at 2026-09-29T12:45:00\n"
        "Time range: 2026-09-26T12:30:00 to 2026-09-29T12:30:00\n"
    )
    (sri / "202609291235-202609291240.CELERY.CHECKED").touch()
    result = ingestion_status(config, {"radar_type": "sri"})
    assert result["status"] == "ready"
    assert result["interval"] == "5m"
    assert result["from"] == "2026-09-26T12:30:00"
    assert result["to"] == "2026-09-29T12:30:00"
    assert result["lastUpdate"] == "2026-09-29T12:45:00"
    assert result["pendingImport"]["to"] == "2026-09-29T12:40:00"
    (sri / "202609291235-202609291240.GEOSERVER.READY").write_text(
        "Time range: 2026-09-29T12:35:00 to 2026-09-29T12:40:00\n"
    )
    assert ingestion_status(config, {"radar_type": "sri"})["pendingImport"] is None
    with pytest.raises(NotFound):
        ingestion_status(config, {"radar_type": "invalid"})


def test_sub_seasonal_preserves_run_and_coverage(tmp_path, monkeypatch, configs):
    config = configs["sub-seasonal"]
    _configure(monkeypatch, config, tmp_path)
    (tmp_path / "20260921-20261012.GEOSERVER.READY").write_text(
        "Processed by GeoServer at 2026-09-22T15:32:01\n"
        "Run: 20260918\nRange: 20260921-20261012\n"
    )
    result = ingestion_status(config)
    assert result["lastRun"] == "20260918"
    assert result["from"] == "2026-09-21T00:00:00"
    assert result["to"] == "2026-10-12T00:00:00"


def test_ww3_scans_mediterraneo_and_computes_offsets(tmp_path, monkeypatch, configs):
    config = configs["ww3"]
    _configure(monkeypatch, config, tmp_path)
    sea = tmp_path / "Mediterraneo"
    sea.mkdir()
    (sea / "2026092800.READY").touch()
    (sea / "2026092800-2026092900.GEOSERVER.READY").write_text(
        "Processed by GeoServer at 2026-09-29T01:00:00\nRun: 2026092800\n"
    )
    result = ingestion_status(config)
    assert result["status"] == "ready"
    assert result["lastRun"] == "2026092800"
    assert result["start_offset"] == 0
    assert result["end_offset"] == 24


def test_marine_forcings_are_reported_individually(tmp_path, monkeypatch, configs):
    config = configs["marine"]
    _configure(monkeypatch, config, tmp_path)
    monkeypatch.setenv("MER_FORCINGS", "BOLAM,ECMWF,ICON")
    for name, run in (("BOLAM", "20260928"), ("ECMWF", "20260928"), ("ICON", "20260927")):
        path = tmp_path / name
        path.mkdir()
        (path / f"{run}.GEOSERVER.READY").write_text(f"Run: {run}\n")
    (tmp_path / "ICON" / "20260929.wl.CELERY.CHECKED").touch()
    result = ingestion_status(config)
    assert result["availableForcings"] == ["BOLAM", "ECMWF"]
    assert result["forcings"]["ICON"]["pendingImport"]["run"] == "20260929"
    assert result["lastRun"] == "20260928"


def test_no_markers_and_only_raw_ready(tmp_path, monkeypatch, configs):
    config = configs["seasonal"]
    _configure(monkeypatch, config, tmp_path)
    assert ingestion_status(config)["status"] == "unknown"
    (tmp_path / "20260928.READY").touch()
    result = ingestion_status(config)
    assert result["status"] == "pending"
    assert result["pendingImport"]["run"] == "20260928"
