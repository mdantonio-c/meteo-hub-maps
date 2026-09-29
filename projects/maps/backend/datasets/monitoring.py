"""Periodic discovery task names shared by startup and monitoring controls."""

from .registry import load_registry


def discovery_tasks() -> tuple[str, ...]:
    tasks = {
        "windy_image_mosaic": "check_latest_data_and_trigger_geoserver_import_windy",
        "seasonal_mosaic": "check_latest_data_and_trigger_geoserver_import_seasonal",
        "radar_stream": "check_latest_data_and_trigger_geoserver_import_radar",
        "sub_seasonal_mosaic": "check_latest_data_and_trigger_geoserver_import_sub_seasonal",
        "ww3_mosaic": "check_latest_data_and_trigger_geoserver_import_ww3",
        "marine_mosaic": "check_latest_data_and_trigger_geoserver_import_mer_bolam",
    }
    return tuple(dict.fromkeys(tasks[config.adapter] for config in load_registry().list()))


def start_monitoring(celery_instance) -> None:
    for name in discovery_tasks():
        celery_instance.create_crontab_task(
            name=name,
            hour="*",
            minute="*",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
            task=name,
            args=[],
        )


def stop_monitoring(celery_instance) -> bool:
    active = False
    for name in discovery_tasks():
        if celery_instance.get_periodic_task(name):
            celery_instance.delete_periodic_task(name)
            active = True
    return active
