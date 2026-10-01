"""Exercise metadata expiry and orphan detection against a real cache layout."""

import os
from pathlib import Path
from unittest.mock import MagicMock

from maps.datasets import cache_cleanup
from maps.datasets.monitoring import start_cache_maintenance

NOW = 2_000_000_000


def parameter_file(layer: Path, parameter_hash: str, age: int = 0) -> Path:
    layer.mkdir(parents=True, exist_ok=True)
    path = layer / f"parameters-{parameter_hash}.properties"
    path.write_text("TIME=2026-10-01T00\\:00\\:00Z\n")
    os.utime(path, (NOW - age, NOW - age))
    return path


def test_removes_expired_associated_and_recent_orphaned_metadata(tmp_path):
    layer = tmp_path / "meteohub_radar-sri"
    expired = parameter_file(
        layer, "expired", cache_cleanup.PARAMETER_MAX_AGE_SECONDS + 1
    )
    orphaned = parameter_file(layer, "orphaned")
    current = parameter_file(layer, "current")
    boundary = parameter_file(
        layer, "boundary", cache_cleanup.PARAMETER_MAX_AGE_SECONDS
    )
    for parameter_hash in ("expired", "current", "boundary"):
        (layer / f"EPSG_900913_1024_05_{parameter_hash}").mkdir()
    tile = layer / "EPSG_900913_1024_05_expired" / "tile.png"
    tile.write_bytes(b"tile")
    unrelated = layer / "geowebcache.xml"
    unrelated.touch()

    result = cache_cleanup.cleanup_parameter_files(tmp_path, now=NOW)

    assert result == {"scanned": 4, "expired": 1, "orphaned": 1, "errors": 0}
    assert not expired.exists()
    assert not orphaned.exists()
    assert current.exists()
    assert boundary.exists()  # Exactly three days is not older than three days.
    assert tile.read_bytes() == b"tile"
    assert unrelated.exists()


def test_association_is_exact_and_scoped_to_same_layer(tmp_path):
    layer = tmp_path / "meteohub_radar-sri"
    same_hash = parameter_file(layer, "abcdef")
    short_hash = parameter_file(layer, "def")
    other_layer = tmp_path / "meteohub_radar-srt"
    other_layer.mkdir()
    (other_layer / "EPSG_900913_05_abcdef").mkdir()
    # A filename or a suffix substring is not an associated directory.
    (layer / "EPSG_900913_05_abcdef").touch()
    (layer / "EPSG_900913_06_abcdef").mkdir()

    result = cache_cleanup.cleanup_parameter_files(tmp_path, now=NOW)

    assert result["orphaned"] == 1
    assert same_hash.exists()
    assert not short_hash.exists()
    (layer / "EPSG_900913_06_abcdef").rmdir()
    assert cache_cleanup.cleanup_parameter_files(tmp_path, now=NOW)["orphaned"] == 1
    assert not same_hash.exists()  # Another layer cannot retain this metadata.


def test_skips_symlinks_and_nested_files(tmp_path):
    root = tmp_path / "gwc"
    root.mkdir()
    outside = tmp_path / "outside"
    external_file = parameter_file(outside, "external")
    (root / "linked-layer").symlink_to(outside, target_is_directory=True)
    layer = root / "meteohub_radar-sri"
    layer.mkdir()
    (layer / "parameters-link.properties").symlink_to(external_file)
    nested = parameter_file(layer / "nested", "nested")

    assert cache_cleanup.cleanup_parameter_files(root, now=NOW)["scanned"] == 0
    assert external_file.exists()
    assert nested.exists()


def test_missing_root_and_repeated_cleanup_are_harmless(tmp_path):
    root = tmp_path / "missing"
    assert cache_cleanup.cleanup_parameter_files(root)["errors"] == 0
    parameter_file(root / "meteohub_radar-sri", "orphaned")
    assert cache_cleanup.cleanup_parameter_files(root, now=NOW)["orphaned"] == 1
    assert cache_cleanup.cleanup_parameter_files(root, now=NOW)["scanned"] == 0


def test_unlink_failure_does_not_prevent_other_deletions(tmp_path, monkeypatch):
    layer = tmp_path / "meteohub_radar-sri"
    blocked = parameter_file(layer, "blocked")
    removable = parameter_file(layer, "removable")
    unlink = os.unlink

    def failing_unlink(path):
        if Path(path) == blocked:
            raise PermissionError("read-only metadata")
        unlink(path)

    monkeypatch.setattr(cache_cleanup.os, "unlink", failing_unlink)
    result = cache_cleanup.cleanup_parameter_files(tmp_path, now=NOW)
    assert result["errors"] == 1
    assert result["orphaned"] == 1
    assert blocked.exists()
    assert not removable.exists()


def test_hourly_maintenance_schedule():
    client = MagicMock()
    start_cache_maintenance(client)
    client.create_crontab_task.assert_called_once_with(
        name="cleanup_gwc_parameters",
        hour="*",
        minute="0",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        task="cleanup_gwc_parameters",
        args=[],
    )
