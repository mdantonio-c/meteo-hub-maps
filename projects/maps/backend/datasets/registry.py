"""Dataset registry used by endpoint and ingestion adapters."""

from dataclasses import dataclass
from importlib import import_module
from typing import Optional, Tuple

from .manifest import (
    DatasetConfig,
    ManifestError,
    _SPECIALIZED_BEHAVIOURS,
    load_manifest,
)

_ADAPTERS = {
    "bulk_override": "maps.datasets.behaviours.BulkOverrideAdapter",
    "fifo_granules": "maps.datasets.behaviours.FifoGranulesAdapter",
}

_SPECIALIZATIONS = {
    "icon": "maps.datasets.windy.WindyIngestionAdapter",
    "wrf": "maps.datasets.windy.WindyIngestionAdapter",
    "radar": "maps.datasets.radar.RadarIngestionAdapter",
    "ww3": "maps.datasets.specialized.WW3Adapter",
    "seasonal": "maps.datasets.specialized.SeasonalAdapter",
    "sub-seasonal": "maps.datasets.sub_seasonal.SubSeasonalIngestionAdapter",
    "marine": "maps.datasets.marine.MarineIngestionAdapter",
}


@dataclass(frozen=True)
class DatasetRegistry:
    """Immutable lookup of validated dataset definitions."""

    datasets: Tuple[DatasetConfig, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "_by_id", {dataset.identifier: dataset for dataset in self.datasets}
        )

    def get(self, identifier: str) -> DatasetConfig:
        try:
            return self._by_id[identifier]
        except KeyError as exc:
            raise ManifestError(f"unknown dataset: {identifier}") from exc

    def list(self) -> Tuple[DatasetConfig, ...]:
        return self.datasets

    def adapter_path(self, identifier: str) -> str:
        config = self.get(identifier)
        adapter = config.adapter
        try:
            default = _ADAPTERS[adapter]
            specialized = _SPECIALIZATIONS.get(identifier)
            return (
                specialized
                if _SPECIALIZED_BEHAVIOURS.get(identifier) == adapter
                else default
            )
        except KeyError as exc:
            raise ManifestError(f"no adapter registered for {adapter!r}") from exc

    def adapter(self, identifier: str):
        """Build the configured ingestion adapter for a dataset."""
        module_name, class_name = self.adapter_path(identifier).rsplit(".", 1)
        return getattr(import_module(module_name), class_name)(self.get(identifier))

    def ingestion_task(self, identifier: str) -> str:
        task = self.get(identifier).ingestion.get("task")
        if not task:
            raise ManifestError(f"no ingestion task configured for {identifier!r}")
        return task


def load_registry(path: Optional[str] = None) -> DatasetRegistry:
    return DatasetRegistry(load_manifest(path))


def load_adapter(identifier: str):
    """Resolve the dataset and its ingestion implementation at task execution time."""
    return load_registry().adapter(identifier)
