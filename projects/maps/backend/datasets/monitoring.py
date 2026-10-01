"""Periodic discovery schedules shared by startup and monitoring controls."""

from .manifest import ManifestError
from .registry import load_registry


def discovery_schedules() -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    configs = load_registry().list()
    if any(not config.discovery.get("task") for config in configs):
        raise ManifestError("each scheduled dataset needs a discovery.task")
    schedules = {}
    for config in configs:
        task = config.discovery["task"]
        name = f"discover-{config.identifier}" if task == "discover_dataset" else task
        schedules[name] = (
            name,
            task,
            (config.identifier,) if task == "discover_dataset" else (),
        )
    return tuple(schedules.values())


def discovery_tasks() -> tuple[str, ...]:
    return tuple(name for name, _, _ in discovery_schedules())


def start_cache_maintenance(celery_instance) -> None:
    """Schedule hourly metadata cleanup independently of ingestion monitoring."""
    celery_instance.create_crontab_task(
        name="cleanup_gwc_parameters",
        hour="*",
        minute="0",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        task="cleanup_gwc_parameters",
        args=[],
    )


def start_monitoring(celery_instance) -> None:
    for name, task, args in discovery_schedules():
        celery_instance.create_crontab_task(
            name=name,
            hour="*",
            minute="*",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
            task=task,
            args=list(args),
        )


def stop_monitoring(celery_instance) -> bool:
    active = False
    for name in discovery_tasks():
        if celery_instance.get_periodic_task(name):
            celery_instance.delete_periodic_task(name)
            active = True
    return active
