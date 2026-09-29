"""Initialize dataset monitoring when the backend starts."""

from restapi.connectors import celery

from maps.datasets.monitoring import start_monitoring
from maps.datasets.registry import load_registry


class Initializer:
    def __init__(self) -> None:
        # Validate the manifest before scheduling ingestion.
        self.dataset_registry = load_registry()
        instance = celery.get_instance()
        start_monitoring(instance)
        instance.celery_app.send_task(name="initialize_geoserver", args=[])

    def initialize_testing_environment(self) -> None:
        pass
