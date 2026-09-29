"""Configuration-driven dataset modules."""

from .cache import GWCInvalidator
from .geoserver import GeoServerPublisher
from .locking import DatasetLock
from .manifest import DatasetConfig, ManifestError, load_manifest
from .markers import MarkerStore
from .paths import dataset_base_path, safe_dataset_file_path
from .registry import DatasetRegistry, load_registry
from .temporal import write_temporal_config


def __getattr__(name):
    """Avoid initializing Celery when only the manifest or cache is needed."""
    adapters = {
        "WindyIngestionAdapter": ("windy", "WindyIngestionAdapter"),
        "RadarIngestionAdapter": ("radar", "RadarIngestionAdapter"),
        "SubSeasonalIngestionAdapter": ("sub_seasonal", "SubSeasonalIngestionAdapter"),
        "MarineIngestionAdapter": ("marine", "MarineIngestionAdapter"),
    }
    if name not in adapters:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    module, attribute = adapters[name]
    return getattr(import_module(f".{module}", __name__), attribute)


__all__ = [
    "DatasetConfig",
    "DatasetRegistry",
    "ManifestError",
    "load_manifest",
    "load_registry",
    "MarkerStore",
    "write_temporal_config",
    "GeoServerPublisher",
    "WindyIngestionAdapter",
    "RadarIngestionAdapter",
    "DatasetLock",
    "GWCInvalidator",
    "SubSeasonalIngestionAdapter",
    "MarineIngestionAdapter",
    "dataset_base_path",
    "safe_dataset_file_path",
]
