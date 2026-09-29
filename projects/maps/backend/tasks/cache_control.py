"""Priority-aware GeoWebCache orchestration.

Celery queues isolate ingestion from cache work, but cannot reorder jobs that
have already reached GeoWebCache.  This module therefore cancels obsolete
per-layer GWC work before every truncate and uses Redis generations to make
queued warm requests harmless after a newer publication.
"""

import os
from typing import Any, Iterable, List, Optional

from celery import chord, signature
from redis import Redis
from restapi.connectors import celery
from restapi.connectors.celery import CeleryExt, CeleryRetryTask
from restapi.env import Env
from restapi.utilities.logs import log

from maps.datasets.cache import GWCInvalidator

CACHE_CONTROL_QUEUE = "cache-control"
CACHE_WARM_QUEUE = "cache-warm"
GENERATION_PREFIX = "gwc:generation"
LOCK_PREFIX = "gwc:lock"
LOCK_TIMEOUT_SECONDS = 3600
WARM_CONCURRENCY = max(1, int(Env.get("GWC_SEEDER_CORE_POOL_SIZE", "1")))


def _redis() -> Redis:
    return Redis(
        host=Env.get("REDIS_HOST", "redis.dockerized.io"),
        port=int(Env.get("REDIS_PORT", "6379")),
        password=Env.get("REDIS_PASSWORD", None),
        decode_responses=True,
    )


def _key(prefix: str, workspace: str, layer_name: str) -> str:
    return f"{prefix}:{workspace}:{layer_name}"


def _generation(workspace: str, layer_name: str) -> int:
    value = _redis().get(_key(GENERATION_PREFIX, workspace, layer_name))
    return int(value) if value is not None else 0


def _is_current(workspace: str, layer_name: str, generation: int) -> bool:
    return _generation(workspace, layer_name) == generation


def _warm_lanes(times: List[str]) -> List[List[str]]:
    """Split warming into at most one lane per GWC core seeder thread."""
    lanes = [[] for _ in range(min(WARM_CONCURRENCY, len(times)))]
    for index, time_value in enumerate(times):
        lanes[index % len(lanes)].append(time_value)
    return lanes


def _schedule_warm_task(
    layer_name: str,
    geoserver_url: str,
    username: str,
    password: str,
    workspace: str,
    generation: int,
    times: List[str],
    zoom_start: Optional[int],
    zoom_stop: Optional[int],
) -> None:
    celery.get_instance().celery_app.send_task(
        "warm_gwc_layer",
        kwargs={
            "layer_name": layer_name,
            "geoserver_url": geoserver_url,
            "username": username,
            "password": password,
            "workspace": workspace,
            "generation": generation,
            "times": times,
            "zoom_start": zoom_start,
            "zoom_stop": zoom_stop,
        },
        queue=CACHE_WARM_QUEUE,
        routing_key=CACHE_WARM_QUEUE,
    )


def schedule_cache_refresh(
    layer_name: str,
    geoserver_url: str,
    username: str,
    password: str,
    workspace: str,
    store_name: Optional[str] = None,
    times: Optional[Iterable[str]] = None,
    warm_times: Optional[Iterable[str]] = None,
    zoom_start: Optional[int] = None,
    zoom_stop: Optional[int] = None,
) -> int:
    """Supersede old warming and enqueue high-priority invalidation.

    ``times`` is the truncate set; ``warm_times`` is the optional seed set.
    When both are unset, all current granules are truncated and warmed.
    Returns the generation ID for tracking. This is async - returns immediately.
    """
    if Env.get("GEOSERVER_GWC_ENABLED", "1") != "1":
        return 0
    client = _redis()
    generation = int(client.incr(_key(GENERATION_PREFIX, workspace, layer_name)))
    celery.get_instance().celery_app.send_task(
        "invalidate_gwc_layer",
        kwargs={
            "layer_name": layer_name,
            "geoserver_url": geoserver_url,
            "username": username,
            "password": password,
            "workspace": workspace,
            "store_name": store_name,
            "times": list(times) if times is not None else None,
            "warm_times": list(warm_times) if warm_times is not None else None,
            "generation": generation,
            "zoom_start": zoom_start,
            "zoom_stop": zoom_stop,
        },
        queue=CACHE_CONTROL_QUEUE,
        routing_key=CACHE_CONTROL_QUEUE,
    )
    return generation


def schedule_cache_refresh_chord(
    requests: Iterable[dict[str, Any]],
    ready_file: str,
    ready_contents: str,
    obsolete_ready_files: Optional[Iterable[str]] = None,
    checked_files: Optional[Iterable[str]] = None,
    completion: Optional[dict[str, str]] = None,
) -> None:
    """Create a ready marker only after every GWC truncate has completed.

    Warming is deliberately scheduled by ``invalidate_gwc_layer`` outside the
    chord.  A marker therefore means all stale cache entries were removed, not
    that every replacement tile was eagerly generated.
    """
    callback = signature(
        "write_geoserver_ready",
        kwargs={
            "ready_file": ready_file,
            "ready_contents": ready_contents,
            "obsolete_ready_files": list(obsolete_ready_files or []),
            "checked_files": list(checked_files or []),
            "completion": completion or {},
        },
        queue="ingest",
        routing_key="ingest",
    )
    if Env.get("GEOSERVER_GWC_ENABLED", "1") != "1":
        callback.apply_async(args=[[]])
        return

    header = []
    for request in requests:
        layer_name = request["layer_name"]
        workspace = request["workspace"]
        generation = int(_redis().incr(_key(GENERATION_PREFIX, workspace, layer_name)))
        request = {**request, "generation": generation}
        header.append(
            signature(
                "invalidate_gwc_layer",
                kwargs=request,
                queue=CACHE_CONTROL_QUEUE,
                routing_key=CACHE_CONTROL_QUEUE,
            )
        )

    if not header:
        callback.apply_async(args=[[]])
        return
    chord(header)(callback)


@CeleryExt.task(idempotent=True)
def write_geoserver_ready(
    self,
    results: List[Any],
    ready_file: str,
    ready_contents: str,
    obsolete_ready_files: List[str],
    checked_files: List[str],
    completion: dict[str, str],
) -> None:
    """Write the marker after the cache-control chord succeeds."""
    del results
    directory = os.path.dirname(ready_file)
    os.makedirs(directory, exist_ok=True)
    with open(ready_file, "w", encoding="utf-8") as marker:
        marker.write(ready_contents)
    for path in obsolete_ready_files + checked_files:
        if path != ready_file:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
    if completion:
        from maps.datasets.discovery import _update_forcing_geoserver_ready_if_complete

        _update_forcing_geoserver_ready_if_complete(
            completion["forcing_dir"],
            completion["forcing_name"],
            completion["run_date"],
        )
    log.info("Created GeoServer ready marker after GWC invalidation: {}", ready_file)


def _invalidator(
    geoserver_url: str,
    username: str,
    password: str,
    workspace: str,
    zoom_start: Optional[int],
    zoom_stop: Optional[int],
) -> GWCInvalidator:
    return GWCInvalidator(
        geoserver_url,
        username,
        password,
        workspace,
        enabled=Env.get("GEOSERVER_GWC_ENABLED", "1") == "1",
        zoom_start=zoom_start,
        zoom_stop=zoom_stop,
    )


@CeleryExt.task(idempotent=True)
def invalidate_gwc_layer(
    self,
    layer_name: str,
    geoserver_url: str,
    username: str,
    password: str,
    workspace: str,
    generation: int,
    store_name: Optional[str] = None,
    times: Optional[List[str]] = None,
    warm_times: Optional[List[str]] = None,
    zoom_start: Optional[int] = None,
    zoom_stop: Optional[int] = None,
) -> None:
    """Cancel stale cache work, truncate, and schedule selected warming."""
    if not _is_current(workspace, layer_name, generation):
        raise RuntimeError(f"GWC invalidation superseded for {layer_name}")

    client = _redis()
    lock = client.lock(
        _key(LOCK_PREFIX, workspace, layer_name),
        timeout=LOCK_TIMEOUT_SECONDS,
        blocking_timeout=30,
    )
    if not lock.acquire():
        log.info("Deferring GWC invalidation for {} while its lock is held", layer_name)
        raise CeleryRetryTask(
            f"GWC invalidation lock is held for {layer_name}; retry shortly"
        )
    try:
        if not _is_current(workspace, layer_name, generation):
            raise RuntimeError(f"GWC invalidation superseded for {layer_name}")
        invalidator = _invalidator(
            geoserver_url, username, password, workspace, zoom_start, zoom_stop
        )
        if not invalidator.cancel_seed_tasks(layer_name):
            raise RuntimeError(f"could not cancel GWC work for {layer_name}")
        if not invalidator._wait_for_seed_completion(layer_name):
            raise RuntimeError(f"GWC did not stop work for {layer_name}")
        if not invalidator.ensure_time_parameter_filter(layer_name):
            raise RuntimeError(
                f"could not configure GWC TIME filtering for {layer_name}"
            )
        style_name = invalidator.get_default_style(layer_name)
        if not style_name:
            raise RuntimeError(f"could not resolve GWC style for {layer_name}")
        if times is None:
            if not invalidator.purge_layer_cache(layer_name):
                raise RuntimeError(f"could not purge GWC cache for {layer_name}")
            current_times = invalidator.get_granule_times(
                layer_name, store_name=store_name, all_times=True
            )
            truncate_times = current_times
            warm_times = current_times
        else:
            truncate_times = times
        if not truncate_times:
            raise RuntimeError(f"could not resolve GWC times for {layer_name}")
        if not invalidator.truncate(
            layer_name,
            times=truncate_times,
            style_name=style_name,
            wait_per_time=False,
        ):
            raise RuntimeError(f"could not truncate GWC cache for {layer_name}")

        if warm_times is None:
            warm_times = invalidator.get_granule_times(
                layer_name, store_name=store_name
            )
        log.info(
            f"Scheduling GWC warming for {layer_name}: {len(warm_times)} time(s) "
            f"across {min(WARM_CONCURRENCY, len(warm_times))} lane(s)"
        )
        for warm_lane in _warm_lanes(sorted(warm_times)):
            _schedule_warm_task(
                layer_name,
                geoserver_url,
                username,
                password,
                workspace,
                generation,
                warm_lane,
                zoom_start,
                zoom_stop,
            )
    finally:
        lock.release()


@CeleryExt.task(idempotent=True)
def warm_gwc_layer(
    self,
    layer_name: str,
    geoserver_url: str,
    username: str,
    password: str,
    workspace: str,
    generation: int,
    times: List[str],
    zoom_start: Optional[int] = None,
    zoom_stop: Optional[int] = None,
) -> None:
    """Warm exactly one cache key and reschedule the next current key."""
    if not times or not _is_current(workspace, layer_name, generation):
        return

    invalidator = _invalidator(
        geoserver_url, username, password, workspace, zoom_start, zoom_stop
    )
    time_value = times[0]
    style_name = invalidator.get_default_style(layer_name)
    if not style_name:
        raise RuntimeError(f"could not resolve GWC style for {layer_name}")
    client = _redis()
    lock = client.lock(
        _key(LOCK_PREFIX, workspace, layer_name),
        timeout=LOCK_TIMEOUT_SECONDS,
        blocking_timeout=30,
    )
    if not lock.acquire():
        log.info(
            "Deferring GWC warm submission for {} while its lock is held", layer_name
        )
        _schedule_warm_task(
            layer_name,
            geoserver_url,
            username,
            password,
            workspace,
            generation,
            times,
            zoom_start,
            zoom_stop,
        )
        return
    try:
        if not _is_current(workspace, layer_name, generation):
            return
        # Serialize only GWC submission against invalidate/cancel. Waiting is
        # deliberately outside the lock so all core seeder slots can warm.
        if not invalidator._seed_request(
            layer_name,
            "seed",
            time_value,
            thread_count=1,
            style_name=style_name,
        ):
            raise RuntimeError(
                f"could not submit GWC seed for {layer_name} at {time_value}"
            )
    finally:
        lock.release()

    if not invalidator._wait_for_seed_completion(layer_name):
        raise RuntimeError(f"could not seed GWC cache for {layer_name} at {time_value}")

    if len(times) > 1 and _is_current(workspace, layer_name, generation):
        _schedule_warm_task(
            layer_name,
            geoserver_url,
            username,
            password,
            workspace,
            generation,
            times[1:],
            zoom_start,
            zoom_stop,
        )
