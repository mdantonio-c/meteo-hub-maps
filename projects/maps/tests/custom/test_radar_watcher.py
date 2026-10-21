"""Incremental radar discovery uses completed markers, not pending markers."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from maps.datasets import watcher


@pytest.mark.parametrize("marker", [
    "202609280955-202610010955.GEOSERVER.READY",
    "202610010955.GEOSERVER.READY",
])
def test_stream_submits_only_files_after_latest_completed_time(tmp_path, monkeypatch, marker):
    files = tmp_path / "files"
    files.mkdir()
    for name in ["28-09-2026-10-00.tif", "01-10-2026-09-55.tif", "01-10-2026-10-00.tif"]:
        (files / name).touch()
    (tmp_path / marker).touch()
    (tmp_path / "invalid.GEOSERVER.READY").touch()
    app = MagicMock()
    monkeypatch.setattr(watcher.celery, "get_instance", lambda: app)

    stream = watcher.DataWatcherStream(paths=str(tmp_path))
    stream._perform_action("202610011000", "202610011000.READY", str(tmp_path), "ingest", "sri")

    assert app.celery_app.send_task.call_args.kwargs["args"] == (
        "sri", ["01-10-2026-10-00.tif"], [datetime(2026, 10, 1, 10, 0)],
    )
    assert (tmp_path / "202610011000-202610011000.CELERY.CHECKED").exists()


def test_stream_initial_ingestion_is_bounded_by_retention(tmp_path, monkeypatch):
    files = tmp_path / "files"
    files.mkdir()
    for name in ["28-09-2026-09-55.tif", "28-09-2026-10-00.tif", "01-10-2026-10-00.tif"]:
        (files / name).touch()
    app = MagicMock()
    monkeypatch.setattr(watcher.celery, "get_instance", lambda: app)
    stream = watcher.DataWatcherStream(paths=str(tmp_path))
    stream._perform_action("202610011000", "202610011000.READY", str(tmp_path), "ingest", "sri")
    assert app.celery_app.send_task.call_args.kwargs["args"][1] == [
        "28-09-2026-10-00.tif", "01-10-2026-10-00.tif",
    ]


def test_stream_pending_marker_does_not_advance_completed_watermark(tmp_path, monkeypatch):
    files = tmp_path / "files"
    files.mkdir()
    (files / "01-10-2026-10-00.tif").touch()
    (tmp_path / "202610010955.GEOSERVER.READY").touch()
    pending = tmp_path / "202610011000-202610011000.CELERY.CHECKED"
    pending.write_text("Retry: 0\n")
    import os
    stale = (datetime.now() - timedelta(minutes=6)).timestamp()
    os.utime(pending, (stale, stale))
    app = MagicMock()
    monkeypatch.setattr(watcher.celery, "get_instance", lambda: app)
    stream = watcher.DataWatcherStream(paths=str(tmp_path))
    stream._perform_action("202610011000", "202610011000.READY", str(tmp_path), "ingest", "sri")
    assert app.celery_app.send_task.call_args.kwargs["args"][1] == ["01-10-2026-10-00.tif"]
