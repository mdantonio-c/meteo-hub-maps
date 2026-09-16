"""Configuration-driven dataset modules."""

from .manifest import DatasetConfig, ManifestError, load_manifest
from .registry import DatasetRegistry, load_registry
from .markers import MarkerStore
from .temporal import write_temporal_config
from .geoserver import GeoServerPublisher
from .windy import WindyIngestionAdapter
from .radar import RadarIngestionAdapter
from .locking import DatasetLock
from .cache import GWCInvalidator
from .ww3 import WW3IngestionAdapter
from .seasonal import SeasonalIngestionAdapter
from .sub_seasonal import SubSeasonalIngestionAdapter
from .marine import MarineIngestionAdapter
from .paths import dataset_base_path, safe_dataset_file_path

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
    "WW3IngestionAdapter",
    "SeasonalIngestionAdapter",
    "SubSeasonalIngestionAdapter",
    "MarineIngestionAdapter",
    "dataset_base_path",
    "safe_dataset_file_path",
]
