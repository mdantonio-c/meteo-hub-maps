"""Default ingestion lifecycles; dataset-id implementations override these when needed."""

import os
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from restapi.env import Env

from .geoserver import GeoServerPublisher, atomic_copy_to_mosaic, finalize_atomic_copy
from .manifest import DatasetConfig
from .temporal import write_temporal_config
from .watcher import DataWatcher

_DATE_FORMATS = {
    "yyyyMMddHHmm": "%Y%m%d%H%M",
    "yyyyMMddHH": "%Y%m%d%H",
    "yyyyMMdd": "%Y%m%d",
    "yyyy-MM-dd": "%Y-%m-%d",
    "dd-MM-yyyy-HH-mm": "%d-%m-%Y-%H-%M",
    "yyyyMMdd'T'HHmmss": "%Y%m%dT%H%M%S",
}


class BulkOverrideAdapter:
    """Replace each mosaic with the latest READY run and refresh its cache."""

    def __init__(self, config: DatasetConfig) -> None:
        self.config = config

    def root(self) -> Path:
        discovery = self.config.discovery
        env_name = discovery.get("base_path_env")
        root = Path(
            Env.get(env_name, discovery["base_path_default"])
            if env_name
            else discovery["base_path_default"]
        )
        suffix = discovery.get("path_suffix", "")
        path = (root / suffix).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError(f"dataset source path outside {root}: {suffix}")
        return path

    def discover(self, path=None) -> None:
        markers = self.config.discovery["markers"]
        DataWatcher(
            paths=str(path or self.root()),
            ready_suffix=markers["ready_suffix"],
            processed_suffix=markers["completed_suffix"],
        ).check_and_trigger(
            task_name=self.config.ingestion["task"],
            task_args=lambda identifier, filename, folder: (
                (identifier, self.config.identifier)
                if self.config.ingestion["task"] == "ingest_dataset"
                else (identifier,)
            ),
        )

    def _source(self, variable: str) -> Path:
        root = self.root()
        template = self.config.discovery.get("source_files_path")
        if template:
            source = Path(template.format(base_path=root, variable=variable))
        else:
            source = root / variable
        if not source.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"source path outside dataset root: {source}")
        return source

    def _variables(self) -> list[str]:
        configured = self.config.discovery.get("variables")
        if configured:
            return list(configured)
        return sorted(p.name for p in self.root().iterdir() if p.is_dir())

    def _granules(self, variable: str) -> list[tuple[datetime, Path]]:
        source = self._source(variable)
        if not source.is_dir():
            return []
        pattern = re.compile(self.config.temporal["filename_regex"])
        granules = []
        for file in source.iterdir():
            if file.suffix.lower() not in (".tif", ".tiff"):
                continue
            timestamp = self._timestamp(file.name, pattern)
            if timestamp is not None:
                granules.append((timestamp, file))
        return sorted(granules, key=lambda item: (item[0], item[1].name))

    def _timestamp(self, filename, pattern=None):
        match = (pattern or re.compile(self.config.temporal["filename_regex"])).search(
            filename
        )
        if match:
            try:
                return datetime.strptime(
                    match.group(1),
                    _DATE_FORMATS[self.config.temporal["filename_format"]],
                ).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        return None

    def _select(
        self, granules: list[tuple[datetime, Path]]
    ) -> list[tuple[datetime, Path]]:
        return granules

    def _incoming(self, variable):
        return BulkOverrideAdapter._granules(self, variable)

    def _cache_times(self, target, incoming, selected):
        """Bulk replacements invalidate all current times."""
        return {}

    def _target(self, layer_name: str) -> Path:
        return Path("/geoserver_data/copies") / layer_name

    def ingest(self, run: str, **kwargs) -> None:
        from maps.tasks.cache_control import schedule_cache_refresh_chord

        if not re.fullmatch(r"[A-Za-z0-9_-]+", run):
            raise ValueError(f"invalid dataset run identifier: {run}")
        config = self.config
        root = self.root()
        if not root.is_dir():
            raise FileNotFoundError(f"dataset source directory not found: {root}")
        url = kwargs.get("geoserver_url") or Env.get(
            "GEOSERVER_URL", "http://geoserver.dockerized.io:8080/geoserver"
        )
        username = kwargs.get("username") or Env.get("GEOSERVER_ADMIN_USER", None)
        password = kwargs.get("password") or Env.get("GEOSERVER_ADMIN_PASSWORD", None)
        workspace = config.geoserver["workspace"]
        publisher = GeoServerPublisher(url, username, password, workspace)
        if not publisher.ensure_workspace():
            raise RuntimeError(f"could not create workspace {workspace}")
        requests = []
        for variable in self._variables():
            incoming = self._incoming(variable)
            granules = self._granules(variable)
            selected = self._select(granules)
            if not selected:
                continue
            layer = config.geoserver.get("variables", {}).get(variable, {})
            layer_name = layer.get("layer_name", f"{config.identifier}-{variable}")
            store_name = f"mosaic_{layer_name}"
            target = str(self._target(layer_name))
            cache_times = self._cache_times(target, incoming, selected)
            staging = atomic_copy_to_mosaic(target, [str(file) for _, file in selected])
            try:
                write_temporal_config(
                    Path(staging),
                    config.temporal["filename_regex"],
                    config.temporal["filename_format"],
                )
                finalize_atomic_copy(staging, target)
            except Exception:
                shutil.rmtree(staging, ignore_errors=True)
                raise
            if not publisher.publish_mosaic(
                target, store_name, layer_name, config.resolve_sld(variable, layer_name)
            ) or not publisher.enable_time_dimension(store_name, layer_name):
                raise RuntimeError(f"could not publish {layer_name}")
            requests.append(
                {
                    **self._cache_request(
                        layer_name, store_name, url, username, password
                    ),
                    **cache_times,
                }
            )

        if not requests:
            raise RuntimeError(
                f"no publishable granules found for dataset {config.identifier}"
            )
        markers = config.discovery["markers"]
        ready_file = root / f"{run}{markers['completed_suffix']}"
        schedule_cache_refresh_chord(
            requests,
            ready_file=str(ready_file),
            ready_contents=f"Run: {run}\nProcessed: {datetime.now().isoformat()}\n",
            obsolete_ready_files=[
                str(path)
                for path in root.glob(f"*{markers['completed_suffix']}")
                if path != ready_file
            ],
            checked_files=[str(root / f"{run}.CELERY.CHECKED")],
        )

    def _cache_request(self, layer, store, url, username, password):
        cache = self.config.geoserver.get("cache", {})
        return {
            "layer_name": layer,
            "store_name": store,
            "geoserver_url": url,
            "username": username,
            "password": password,
            "workspace": self.config.geoserver["workspace"],
            "zoom_start": cache.get("zoom_start"),
            "zoom_stop": cache.get("zoom_stop"),
        }


class FifoGranulesAdapter(BulkOverrideAdapter):
    """Keep newest granules by timestamp, applying age and count limits together."""

    def _granules(self, variable: str) -> list[tuple[datetime, Path]]:
        """Merge incoming granules with the currently published rolling window."""
        incoming = self._incoming(variable)
        layer = self.config.geoserver.get("variables", {}).get(variable, {})
        name = layer.get("layer_name", f"{self.config.identifier}-{variable}")
        target = self._target(name)
        existing = []
        if target.is_dir():
            for file in target.iterdir():
                if file.suffix.lower() in (".tif", ".tiff"):
                    timestamp = self._timestamp(file.name)
                    if timestamp is not None:
                        existing.append((timestamp, file))
        # Incoming files win on matching filenames (replacement granules).
        by_name = {file.name: (timestamp, file) for timestamp, file in existing}
        by_name.update({file.name: (timestamp, file) for timestamp, file in incoming})
        return sorted(by_name.values(), key=lambda entry: (entry[0], entry[1].name))

    def _select(
        self, granules: list[tuple[datetime, Path]]
    ) -> list[tuple[datetime, Path]]:
        retention = self.config.ingestion["retention"]
        if granules and retention.get("hours"):
            cutoff = max(timestamp for timestamp, _ in granules) - timedelta(
                hours=retention["hours"]
            )
            granules = [entry for entry in granules if entry[0] >= cutoff]
        granules = sorted(granules, key=lambda entry: (entry[0], entry[1].name))
        if retention.get("max_granules"):
            granules = granules[-retention["max_granules"] :]
        return granules

    def _cache_times(self, target, incoming, selected):
        target_path = Path(target)
        previous = {}
        if target_path.is_dir():
            for file in target_path.iterdir():
                if file.suffix.lower() in (".tif", ".tiff"):
                    timestamp = self._timestamp(file.name)
                    if timestamp is not None:
                        previous[file.name] = timestamp
        current = {file.name: timestamp for timestamp, file in selected}
        # A producer may replace an existing timestamp; include the selected
        # input times even when filenames are unchanged.
        selected_names = set(current)
        changed = {
            timestamp for timestamp, file in incoming if file.name in selected_names
        }
        removed = {
            timestamp for name, timestamp in previous.items() if name not in current
        }
        affected = sorted(changed | removed)
        if not affected:
            return {"times": [], "warm_times": []}
        return {
            "times": [stamp.isoformat().replace("+00:00", "Z") for stamp in affected],
            "warm_times": [
                stamp.isoformat().replace("+00:00", "Z")
                for name, stamp in current.items()
                if name not in previous
            ],
        }
