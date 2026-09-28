from restapi.connectors import celery
from kombu import Exchange, Queue
from maps.tasks import cache_control  # noqa: F401
from maps.tasks import ww3  # noqa: F401
from maps.tasks import startup  # noqa: F401

instance = celery.get_instance()
app = instance.celery_app

app.conf.update(
    task_default_queue="ingest",
    task_default_exchange="ingest",
    task_default_routing_key="ingest",
    task_queues=(
        Queue("ingest", Exchange("ingest"), routing_key="ingest"),
        Queue(
            "cache-control",
            Exchange("cache-control"),
            routing_key="cache-control",
        ),
        Queue("cache-warm", Exchange("cache-warm"), routing_key="cache-warm"),
    ),
    task_annotations={
        "*": {
            "soft_time_limit": 600,
        },
        # Leave a margin above GWC's 30-minute wait timeout so a synchronous
        # task can return a deterministic timeout instead of being interrupted.
        "warm_gwc_layer": {"soft_time_limit": 1860},
        "invalidate_gwc_layer": {"soft_time_limit": 1860},
    },
)
