"""Regression tests for Windy ImageMosaic ingestion."""

from unittest.mock import MagicMock, patch

import yaml
from pathlib import Path

from maps.datasets import windy_processing


@patch.object(windy_processing.requests, "post")
def test_publish_layer_accepts_existing_mosaic_coverage(mock_post):
    mock_post.return_value = MagicMock(status_code=409, text="Coverage already exists")
    assert windy_processing.publish_layer("t2m-t2m", "t2m-t2m", "http://geoserver")


def test_ingestion_uses_watcher_source_directory():
    source_directory = "/windy/Windy-12-WRF.web/Italia"
    with patch.object(windy_processing, "_ingest_windy_image_mosaic", return_value=[]), patch(
        "maps.tasks.cache_control.schedule_cache_refresh_chord"
    ) as schedule:
        windy_processing.update_geoserver_image_mosaic(
            None, "http://geoserver", "12", "20260922", "/SLDs", "WRF", source_directory
        )

    assert windy_processing._ingest_windy_image_mosaic.call_args.kwargs[
        "source_directory"
    ] == source_directory
    assert schedule.call_args.kwargs["ready_file"] == (
        f"{source_directory}/2026092212.GEOSERVER.READY"
    )


def test_workers_receive_dedicated_wrf_ingest_folders() -> None:
    compose_config = Path(__file__).parents[3] / "confs" / "commons.yml"
    services = yaml.safe_load(compose_config.read_text(encoding="utf-8"))["services"]
    for service in ("backend", "celery"):
        assert (
            services[service]["environment"]["WINDY_WRF_INGEST_FOLDERS"]
            == "${WINDY_WRF_INGEST_FOLDERS}"
        )
