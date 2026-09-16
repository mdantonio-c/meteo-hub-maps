"""Dataset registry used by endpoint and ingestion adapters."""

from dataclasses import dataclass
from typing import Optional, Tuple

from .manifest import DatasetConfig, ManifestError, load_manifest


_ADAPTERS = {
    "windy_image_mosaic": "maps.datasets.windy.WindyIngestionAdapter",
    "radar_stream": "maps.datasets.radar.RadarIngestionAdapter",
    "ww3_mosaic": "maps.datasets.ww3.WW3IngestionAdapter",
    "seasonal_mosaic": "maps.datasets.seasonal.SeasonalIngestionAdapter",
    "sub_seasonal_mosaic": "maps.datasets.sub_seasonal.SubSeasonalIngestionAdapter",
    "marine_mosaic": "maps.datasets.marine.MarineIngestionAdapter",
}


@dataclass(frozen=True)
class DatasetRegistry:
    """Immutable lookup of validated dataset definitions."""

    datasets: Tuple[DatasetConfig, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "_by_id", {dataset.identifier: dataset for dataset in self.datasets})

    def get(self, identifier: str) -> DatasetConfig:
        try:
            return self._by_id[identifier]
        except KeyError as exc:
            raise ManifestError(f"unknown dataset: {identifier}") from exc

    def list(self) -> Tuple[DatasetConfig, ...]:
        return self.datasets

    def adapter_path(self, identifier: str) -> str:
        adapter = self.get(identifier).adapter
        try:
            return _ADAPTERS[adapter]
        except KeyError as exc:
            raise ManifestError(f"no adapter registered for {adapter!r}") from exc


def load_registry(path: Optional[str] = None) -> DatasetRegistry:
    return DatasetRegistry(load_manifest(path))
