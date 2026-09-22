"""Load and validate the application dataset manifest.

The manifest is deliberately kept behind this module. Callers receive validated
dataset definitions and do not need to know whether the source is YAML or how
validation errors are formatted.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple, Union
import os
import re

import yaml


class ManifestError(ValueError):
    """Raised when the dataset manifest cannot be loaded or validated."""


@dataclass(frozen=True)
class DatasetConfig:
    """Validated dataset configuration with the original nested values retained."""

    identifier: str
    kind: str
    adapter: str
    endpoint: Mapping[str, Any]
    discovery: Mapping[str, Any]
    ingestion: Mapping[str, Any]
    temporal: Mapping[str, Any]
    geoserver: Mapping[str, Any]
    raw: Mapping[str, Any]

    @property
    def route(self) -> str:
        return str(self.endpoint.get("route", ""))

    def resolve_sld(
        self,
        variable: str = "",
        layer_name: str = "",
        **kwargs: Any,
    ) -> Optional[str]:
        """Return the SLD style name for the given variable.

        Resolution order:
        1. Variable-level ``style_name`` (if declared in geoserver.variables)
        2. Dataset-level ``sld.style_name`` (template resolved with available keys)
        3. None (no SLD)
        """
        sld_section: Mapping[str, Any] = self.geoserver.get("sld", {})
        default_template: Optional[str] = sld_section.get("style_name")
        variables_section: Mapping[str, Any] = self.geoserver.get("variables", {})
        variable_config: Mapping[str, Any] = variables_section.get(variable, {})

        # 1. Variable-level override
        var_style = variable_config.get("style_name")
        if var_style:
            return str(var_style)

        # 2. Dataset-level template
        if default_template:
            context = {
                "variable": variable,
                "layer_name": layer_name or variable,
                **kwargs,
            }
            return default_template.format(**context)

        return None


_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]*$")
_ADAPTERS = {
    "windy_image_mosaic",
    "radar_stream",
    "ww3_mosaic",
    "seasonal_mosaic",
    "sub_seasonal_mosaic",
    "marine_mosaic",
}
_REQUIRED_SECTIONS = ("discovery", "ingestion", "temporal", "geoserver", "endpoint")


def _require_mapping(value: Any, path: str, errors: List[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        errors.append(f"{path} must be a mapping")
        return {}
    return value


def _require_string(section: Mapping[str, Any], key: str, path: str, errors: List[str]) -> str:
    value = section.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path}.{key} must be a non-empty string")
        return ""
    return value


def _validate_dataset(raw: Any, index: int, errors: List[str]) -> Optional[DatasetConfig]:
    path = f"datasets[{index}]"
    if not isinstance(raw, Mapping):
        errors.append(f"{path} must be a mapping")
        return None

    identifier = _require_string(raw, "id", path, errors)
    if identifier and not _IDENTIFIER.fullmatch(identifier):
        errors.append(f"{path}.id must match {_IDENTIFIER.pattern!r}")

    kind = _require_string(raw, "kind", path, errors)
    sections: Dict[str, Mapping[str, Any]] = {}
    for section_name in _REQUIRED_SECTIONS:
        sections[section_name] = _require_mapping(raw.get(section_name), f"{path}.{section_name}", errors)

    adapter = _require_string(sections["ingestion"], "adapter", f"{path}.ingestion", errors)
    if adapter and adapter not in _ADAPTERS:
        errors.append(f"{path}.ingestion.adapter {adapter!r} is not supported")

    route = _require_string(sections["endpoint"], "route", f"{path}.endpoint", errors)
    if route and not route.startswith("/"):
        errors.append(f"{path}.endpoint.route must start with '/'")

    for field in ("filename_regex", "filename_format", "timezone"):
        _require_string(sections["temporal"], field, f"{path}.temporal", errors)

    regex = sections["temporal"].get("filename_regex")
    if isinstance(regex, str):
        try:
            re.compile(regex)
        except re.error as exc:
            errors.append(f"{path}.temporal.filename_regex is invalid: {exc}")

    for field in ("workspace", "store_type"):
        _require_string(sections["geoserver"], field, f"{path}.geoserver", errors)

    return DatasetConfig(
        identifier=identifier,
        kind=kind,
        adapter=adapter,
        endpoint=sections["endpoint"],
        discovery=sections["discovery"],
        ingestion=sections["ingestion"],
        temporal=sections["temporal"],
        geoserver=sections["geoserver"],
        raw=raw,
    )


def _validate_unique(values: Iterable[Tuple[str, str]], errors: List[str], label: str) -> None:
    seen: Dict[str, str] = {}
    for value, identifier in values:
        previous = seen.get(value)
        if previous:
            errors.append(f"{label} {value!r} is duplicated by {previous!r} and {identifier!r}")
        else:
            seen[value] = identifier


def validate_manifest(document: Any) -> Tuple[DatasetConfig, ...]:
    """Validate a parsed manifest and return immutable dataset definitions."""

    errors: List[str] = []
    if not isinstance(document, Mapping):
        raise ManifestError("manifest root must be a mapping")

    version = document.get("version")
    if version != 1:
        errors.append("version must be 1")

    default_geoserver = document.get("geoserver", {})
    if not isinstance(default_geoserver, Mapping):
        errors.append("geoserver must be a mapping")
        default_geoserver = {}
    default_cache = default_geoserver.get("cache", {})
    if not isinstance(default_cache, Mapping):
        errors.append("geoserver.cache must be a mapping")
        default_cache = {}
    for key in ("zoom_start", "zoom_stop"):
        value = default_cache.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            errors.append(f"geoserver.cache.{key} must be an integer")

    raw_datasets = document.get("datasets")
    if not isinstance(raw_datasets, list) or not raw_datasets:
        errors.append("datasets must be a non-empty list")
        raw_datasets = []

    configs_list = []
    for index, raw in enumerate(raw_datasets):
        config = _validate_dataset(raw, index, errors)
        if config is None:
            continue
        dataset_cache = config.geoserver.get("cache", {})
        if not isinstance(dataset_cache, Mapping):
            errors.append(f"datasets[{index}].geoserver.cache must be a mapping")
            dataset_cache = {}
        merged_cache = dict(default_cache)
        merged_cache.update(dataset_cache)
        for key in ("zoom_start", "zoom_stop"):
            value = merged_cache.get(key)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                errors.append(f"datasets[{index}].geoserver.cache.{key} must be an integer")
        geoserver = dict(config.geoserver)
        geoserver["cache"] = merged_cache
        configs_list.append(
            DatasetConfig(
                identifier=config.identifier,
                kind=config.kind,
                adapter=config.adapter,
                endpoint=config.endpoint,
                discovery=config.discovery,
                ingestion=config.ingestion,
                temporal=config.temporal,
                geoserver=geoserver,
                raw=config.raw,
            )
        )
    configs = tuple(configs_list)
    _validate_unique(((config.identifier, config.identifier) for config in configs), errors, "dataset id")

    if errors:
        raise ManifestError("Invalid dataset manifest:\n- " + "\n- ".join(errors))
    return configs


def load_manifest(path: Optional[Union[str, os.PathLike]] = None) -> Tuple[DatasetConfig, ...]:
    """Load and validate a manifest from an explicit path or environment variable."""

    configured_path = path or os.environ.get("DATASET_CONFIG_PATH")
    if not configured_path:
        raise ManifestError("DATASET_CONFIG_PATH is not configured")
    manifest_path = Path(configured_path)
    if not manifest_path.is_file():
        raise ManifestError(f"dataset manifest does not exist: {manifest_path}")

    try:
        with manifest_path.open("r", encoding="utf-8") as manifest_file:
            document = yaml.safe_load(manifest_file)
    except OSError as exc:
        raise ManifestError(f"cannot read dataset manifest {manifest_path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ManifestError(f"cannot parse dataset manifest {manifest_path}: {exc}") from exc

    return validate_manifest(document)
