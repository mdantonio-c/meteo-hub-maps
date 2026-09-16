from restapi.connectors import celery
from maps.tasks import ww3  # noqa: F401

instance = celery.get_instance()
app = instance.celery_app

app.conf.update(
    task_annotations={
        "*": {
            "soft_time_limit": 600,
        }
    }
)
