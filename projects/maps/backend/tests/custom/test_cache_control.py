"""Tests for priority-aware GeoWebCache task scheduling."""

from unittest.mock import MagicMock, patch

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
    ) as redis_factory:
        cache_control.invalidate_gwc_layer.run(
            task,
            layer_name="radar-sri",
            geoserver_url="http://geoserver",
            username="admin",
            password="password",
            workspace="meteohub",
            generation=1,
        )

    redis_factory.assert_not_called()


def test_invalidation_requeues_when_layer_lock_is_held() -> None:
    task = MagicMock()
    redis_client = MagicMock()
    lock = MagicMock()
    lock.acquire.return_value = False
    redis_client.lock.return_value = lock
    celery_app = MagicMock()

    with patch.object(cache_control, "_is_current", return_value=True), patch.object(
        cache_control, "_redis", return_value=redis_client
    ), patch("maps.tasks.cache_control.celery.get_instance") as get_instance:
        get_instance.return_value.celery_app = celery_app
        cache_control.invalidate_gwc_layer.run(
            task,
            layer_name="radar-sri",
            geoserver_url="http://geoserver",
            username="admin",
            password="password",
            workspace="meteohub",
            generation=1,
        )

    assert celery_app.send_task.call_args.args == ("invalidate_gwc_layer",)
    assert celery_app.send_task.call_args.kwargs["countdown"] == 5


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
            task,
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
            task,
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
