"""Tests for priority-aware GeoWebCache task scheduling."""

from unittest.mock import MagicMock, patch

import pytest
from celery.exceptions import Ignore

from maps.tasks import cache_control


def test_schedule_cache_refresh_supersedes_previous_generation() -> None:
    redis_client = MagicMock()
    redis_client.incr.return_value = 7
    celery_app = MagicMock()

    with patch.object(cache_control, "_redis", return_value=redis_client), patch(
        "maps.tasks.cache_control.celery.get_instance"
    ) as get_instance:
        get_instance.return_value.celery_app = celery_app

        generation = cache_control.schedule_cache_refresh(
            "radar-sri",
            "http://geoserver",
            "admin",
            "password",
            "meteohub",
            times=["2026-01-01T00:00:00.000Z"],
        )

    assert generation == 7
    assert celery_app.send_task.call_args.args == ("invalidate_gwc_layer",)
    assert celery_app.send_task.call_args.kwargs["queue"] == "cache-control"
    assert celery_app.send_task.call_args.kwargs["kwargs"]["generation"] == 7
    assert celery_app.send_task.call_args.kwargs["kwargs"]["warm_times"] is None


def test_invalidation_discards_superseded_generation() -> None:
    task = MagicMock()
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


def test_invalidation_fails_when_layer_lock_is_held() -> None:
    task = MagicMock()
    redis_client = MagicMock()
    lock = MagicMock()
    lock.acquire.return_value = False
    redis_client.lock.return_value = lock

    with patch.object(cache_control, "_is_current", return_value=True), patch.object(
        cache_control, "_redis", return_value=redis_client
    ), pytest.raises(RuntimeError, match="could not acquire"):
        cache_control.invalidate_gwc_layer.run(
            layer_name="radar-sri",
            geoserver_url="http://geoserver",
            username="admin",
            password="password",
            workspace="meteohub",
            generation=1,
        )

def test_warm_task_submits_only_the_next_time() -> None:
    task = MagicMock()
    redis_client = MagicMock()
    lock = MagicMock()
    lock.acquire.return_value = True
    redis_client.lock.return_value = lock
    invalidator = MagicMock()
    celery_app = MagicMock()

    with patch.object(cache_control, "_is_current", return_value=True), patch.object(
        cache_control, "_invalidator", return_value=invalidator
    ), patch.object(cache_control, "_redis", return_value=redis_client), patch(
        "maps.tasks.cache_control.celery.get_instance"
    ) as get_instance:
        get_instance.return_value.celery_app = celery_app
        cache_control.warm_gwc_layer.run(
            layer_name="radar-sri",
            geoserver_url="http://geoserver",
            username="admin",
            password="password",
            workspace="meteohub",
            generation=1,
            times=["first", "second"],
        )

    invalidator._seed_request.assert_called_once_with(
        "radar-sri",
        "seed",
        "first",
        thread_count=1,
        style_name=invalidator.get_default_style.return_value,
    )
    invalidator._wait_for_seed_completion.assert_called_once_with("radar-sri")
    assert celery_app.send_task.call_args.kwargs["queue"] == "cache-warm"
    assert celery_app.send_task.call_args.kwargs["kwargs"]["times"] == ["second"]


def test_warm_lanes_match_gwc_core_pool(monkeypatch) -> None:
    monkeypatch.setattr(cache_control, "WARM_CONCURRENCY", 4)

    assert cache_control._warm_lanes(["a", "b", "c", "d", "e", "f"]) == [
        ["a", "e"],
        ["b", "f"],
        ["c"],
        ["d"],
    ]


def test_invalidation_uses_explicit_warm_times(monkeypatch) -> None:
    task = MagicMock()
    redis_client = MagicMock()
    lock = MagicMock()
    lock.acquire.return_value = True
    redis_client.lock.return_value = lock
    invalidator = MagicMock()
    celery_app = MagicMock()
    monkeypatch.setattr(cache_control, "_warm_lanes", lambda times: [times])

    with patch.object(cache_control, "_is_current", return_value=True), patch.object(
        cache_control, "_redis", return_value=redis_client
    ), patch.object(cache_control, "_invalidator", return_value=invalidator), patch(
        "maps.tasks.cache_control.celery.get_instance"
    ) as get_instance:
        get_instance.return_value.celery_app = celery_app
        cache_control.invalidate_gwc_layer.run(
            layer_name="radar-sri",
            geoserver_url="http://geoserver",
            username="admin",
            password="password",
            workspace="meteohub",
            generation=1,
            times=["replaced", "new"],
            warm_times=["new"],
        )

    invalidator.truncate.assert_called_once()
    assert celery_app.send_task.call_args.kwargs["kwargs"]["times"] == ["new"]


def test_cache_refresh_chord_writes_marker_after_all_invalidations(tmp_path) -> None:
    redis_client = MagicMock()
    redis_client.incr.side_effect = [3, 4]
    ready_file = tmp_path / "20260101.GEOSERVER.READY"
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
            ready_file=str(ready_file),
            ready_contents="ready\n",
        )

    assert chord_.call_args.args[0][0].kwargs["generation"] == 3
    assert chord_.call_args.args[0][1].kwargs["generation"] == 4
    chord_result.assert_called_once()


def test_disabled_gwc_refresh_schedules_ready_without_redis_or_header(tmp_path) -> None:
    callback = MagicMock()

    with patch.object(cache_control.Env, "get", return_value="0"), patch.object(
        cache_control, "_redis"
    ) as redis_factory, patch(
        "maps.tasks.cache_control.chord", side_effect=AssertionError("chord disabled")
    ), patch("maps.tasks.cache_control.signature", return_value=callback):
        cache_control.schedule_cache_refresh_chord(
            [
                {
                    "layer_name": "layer",
                    "geoserver_url": "http://geoserver",
                    "username": "admin",
                    "password": "password",
                    "workspace": "meteohub",
                }
            ],
            ready_file=str(tmp_path / "ready.GEOSERVER.READY"),
            ready_contents="ready\n",
        )

    redis_factory.assert_not_called()
    callback.apply_async.assert_called_once_with(args=[[]])


def test_write_geoserver_ready_writes_after_chord_completion(tmp_path) -> None:
    ready_file = tmp_path / "current.GEOSERVER.READY"
    obsolete_file = tmp_path / "stale.GEOSERVER.READY"
    checked_file = tmp_path / "run.CELERY.CHECKED"
    obsolete_file.touch()
    checked_file.touch()

    cache_control.write_geoserver_ready.run(
        [],
        str(ready_file),
        "ready\n",
        [str(obsolete_file)],
        [str(checked_file)],
        {},
    )

    assert ready_file.read_text() == "ready\n"
    assert not obsolete_file.exists()
    assert not checked_file.exists()
