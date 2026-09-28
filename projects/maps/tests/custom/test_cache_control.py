"""Tests for GWC invalidation chords and ready markers."""

from unittest.mock import MagicMock, patch

import pytest
from celery.exceptions import Ignore
from restapi.connectors.celery import CeleryRetryTask

from maps.tasks import cache_control


def test_chord_assigns_generations_and_waits_for_all_layers(tmp_path) -> None:
    redis_client = MagicMock()
    redis_client.incr.side_effect = [3, 4]
    chord_result = MagicMock()

    with patch.object(cache_control, "_redis", return_value=redis_client), patch(
        "maps.tasks.cache_control.chord", return_value=chord_result
    ) as chord_:
        cache_control.schedule_cache_refresh_chord(
            [
                {
                    "layer_name": "first",
                    "geoserver_url": "http://geoserver",
                    "username": "admin",
                    "password": "password",
                    "workspace": "meteohub",
                },
                {
                    "layer_name": "second",
                    "geoserver_url": "http://geoserver",
                    "username": "admin",
                    "password": "password",
                    "workspace": "meteohub",
                },
            ],
            ready_file=str(tmp_path / "current.GEOSERVER.READY"),
            ready_contents="ready\n",
        )

    header = chord_.call_args.args[0]
    assert header[0].kwargs["generation"] == 3
    assert header[1].kwargs["generation"] == 4
    chord_result.assert_called_once()


def test_chord_callback_is_success_body_for_all_header_tasks(tmp_path) -> None:
    redis_client = MagicMock()
    redis_client.incr.side_effect = [1, 1]
    chord_result = MagicMock()

    with patch.object(cache_control, "_redis", return_value=redis_client), patch(
        "maps.tasks.cache_control.chord", return_value=chord_result
    ) as chord_:
        cache_control.schedule_cache_refresh_chord(
            [
                {
                    "layer_name": "first",
                    "geoserver_url": "http://geoserver",
                    "username": "admin",
                    "password": "password",
                    "workspace": "meteohub",
                },
                {
                    "layer_name": "second",
                    "geoserver_url": "http://geoserver",
                    "username": "admin",
                    "password": "password",
                    "workspace": "meteohub",
                },
            ],
            ready_file=str(tmp_path / "current.GEOSERVER.READY"),
            ready_contents="ready\n",
        )

    header = chord_.call_args.args[0]
    callback = chord_result.call_args.args[0]
    assert len(header) == 2
    assert all(task.task == "invalidate_gwc_layer" for task in header)
    assert callback.task == "write_geoserver_ready"
    assert callback.options["queue"] == "ingest"
    # Celery chords execute their body only after all header tasks succeed; a
    # failed header task leaves this success callback undispatched.


def test_chord_callback_runs_without_invalidations_when_gwc_is_disabled(
    tmp_path,
) -> None:
    callback = MagicMock()

    with patch.object(cache_control.Env, "get", return_value="0"), patch.object(
        cache_control, "_redis"
    ) as redis_factory, patch(
        "maps.tasks.cache_control.chord", side_effect=AssertionError("no chord")
    ), patch("maps.tasks.cache_control.signature", return_value=callback):
        cache_control.schedule_cache_refresh_chord(
            [
                {
                    "layer_name": "first",
                    "geoserver_url": "http://geoserver",
                    "username": "admin",
                    "password": "password",
                    "workspace": "meteohub",
                }
            ],
            ready_file=str(tmp_path / "current.GEOSERVER.READY"),
            ready_contents="ready\n",
        )

    redis_factory.assert_not_called()
    callback.apply_async.assert_called_once_with(args=[[]])


def test_ready_marker_is_written_only_by_successful_chord_callback(tmp_path) -> None:
    ready_file = tmp_path / "current.GEOSERVER.READY"
    stale_file = tmp_path / "stale.GEOSERVER.READY"
    checked_file = tmp_path / "run.CELERY.CHECKED"
    stale_file.touch()
    checked_file.touch()

    cache_control.write_geoserver_ready.run(
        [],
        str(ready_file),
        "ready\n",
        [str(stale_file)],
        [str(checked_file)],
        {},
    )

    assert ready_file.read_text() == "ready\n"
    assert not stale_file.exists()
    assert not checked_file.exists()


def test_superseded_invalidation_fails_before_creating_a_ready_marker() -> None:
    with patch.object(cache_control, "_is_current", return_value=False), patch.object(
        cache_control, "_redis"
    ) as redis_factory, pytest.raises(Ignore, match="superseded"):
        cache_control.invalidate_gwc_layer.run(
            layer_name="radar-sri",
            geoserver_url="http://geoserver",
            username="admin",
            password="password",
            workspace="meteohub",
            generation=1,
        )

    redis_factory.assert_not_called()


def test_lock_contention_fails_the_invalidation_header_task() -> None:
    redis_client = MagicMock()
    lock = MagicMock()
    lock.acquire.return_value = False
    redis_client.lock.return_value = lock

    with patch.object(cache_control, "_is_current", return_value=True), patch.object(
        cache_control, "_redis", return_value=redis_client
    ), pytest.raises(CeleryRetryTask):
        cache_control.invalidate_gwc_layer.run(
            layer_name="radar-sri",
            geoserver_url="http://geoserver",
            username="admin",
            password="password",
            workspace="meteohub",
            generation=1,
        )

    redis_client.lock.assert_called_once_with(
        "gwc:lock:meteohub:radar-sri", timeout=3600, blocking_timeout=30
    )


def test_truncate_failure_fails_the_header_and_does_not_schedule_warming() -> None:
    redis_client = MagicMock()
    lock = MagicMock()
    lock.acquire.return_value = True
    redis_client.lock.return_value = lock
    invalidator = MagicMock()
    invalidator.truncate.return_value = False

    with patch.object(cache_control, "_is_current", return_value=True), patch.object(
        cache_control, "_redis", return_value=redis_client
    ), patch.object(cache_control, "_invalidator", return_value=invalidator), patch(
        "maps.tasks.cache_control.celery.get_instance"
    ) as get_instance, pytest.raises(Ignore, match="could not truncate"):
        cache_control.invalidate_gwc_layer.run(
            layer_name="radar-sri",
            geoserver_url="http://geoserver",
            username="admin",
            password="password",
            workspace="meteohub",
            generation=1,
            times=["2026-01-01T00:00:00.000Z"],
        )

    invalidator.truncate.assert_called_once()
    get_instance.assert_not_called()
    lock.release.assert_called_once()
