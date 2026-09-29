"""Load and validate the application dataset manifest.

The manifest is deliberately kept behind this module. Callers receive validated
dataset definitions and do not need to know whether the source is YAML or how
validation errors are formatted.
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple, Union

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
    "bulk_override",
    "fifo_granules",
}
_SPECIALIZED_BEHAVIOURS = {
    "icon": "bulk_override",
    "wrf": "bulk_override",
    "radar": "fifo_granules",
    "ww3": "bulk_override",
    "seasonal": "bulk_override",
    "sub-seasonal": "bulk_override",
    "marine": "bulk_override",
}
_REQUIRED_SECTIONS = ("discovery", "ingestion", "temporal", "geoserver", "endpoint")


def _require_mapping(value: Any, path: str, errors: List[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        errors.append(f"{path} must be a mapping")
        return {}
    return value


def _require_string(
    section: Mapping[str, Any], key: str, path: str, errors: List[str]
) -> str:
    value = section.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path}.{key} must be a non-empty string")
        return ""
    return value


def _validate_default_layout(
    sections: Mapping[str, Mapping[str, Any]], path: str, errors: List[str]
) -> None:
    markers = _require_mapping(
        sections["discovery"].get("markers", {}), f"{path}.discovery.markers", errors
    )
    for field in ("ready_suffix", "completed_suffix"):
        _require_string(markers, field, f"{path}.discovery.markers", errors)
    if markers.get("checked_suffix", ".CELERY.CHECKED") != ".CELERY.CHECKED":
        errors.append(
            f"{path}.discovery.markers.checked_suffix must be .CELERY.CHECKED"
        )
    date_format = sections["temporal"].get("filename_format")
    if date_format not in (
        "yyyyMMddHHmm",
        "yyyyMMddHH",
        "yyyyMMdd",
        "yyyy-MM-dd",
        "dd-MM-yyyy-HH-mm",
        "yyyyMMdd'T'HHmmss",
    ):
        errors.append(
            f"{path}.temporal.filename_format is not supported by the default implementation"
        )
    regex = sections["temporal"].get("filename_regex")
    if isinstance(regex, str):
        try:
            if re.compile(regex).groups < 1:
                errors.append(
                    f"{path}.temporal.filename_regex must capture a timestamp"
                )
        except re.error:
            pass
    variables = sections["discovery"].get("variables")
    if variables is not None and (
        not isinstance(variables, list)
        or any(
            not isinstance(value, str) or not _IDENTIFIER.fullmatch(value)
            for value in variables
        )
    ):
        errors.append(f"{path}.discovery.variables must contain safe folder names")
    source_template = sections["discovery"].get("source_files_path")
    if source_template is not None and (
        not isinstance(source_template, str)
        or "{base_path}" not in source_template
        or "{variable}" not in source_template
        or set(re.findall(r"\{([^{}]+)\}", source_template)) - {"base_path", "variable"}
    ):
        errors.append(
            f"{path}.discovery.source_files_path must use base_path and variable only"
        )


def _validate_retention(
    ingestion: Mapping[str, Any], path: str, errors: List[str]
) -> None:
    retention = _require_mapping(
        ingestion.get("retention"), f"{path}.ingestion.retention", errors
    )
    if not any(retention.get(key) is not None for key in ("hours", "max_granules")):
        errors.append(f"{path}.ingestion.retention needs hours or max_granules")
    for key in ("hours", "max_granules"):
        value = retention.get(key)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
        ):
            errors.append(
                f"{path}.ingestion.retention.{key} must be a positive integer"
            )


def _validate_ingestion_behaviour(
    identifier: str,
    sections: Mapping[str, Mapping[str, Any]],
    path: str,
    errors: List[str],
) -> str:
    ingestion = sections["ingestion"]
    adapter = ingestion.get("behaviour")
    if not isinstance(adapter, str) or not adapter.strip():
        errors.append(f"{path}.ingestion.behaviour must be a non-empty string")
        return ""
    if adapter not in _ADAPTERS:
        errors.append(f"{path}.ingestion.behaviour {adapter!r} is not supported")
    if "behaviour" in ingestion and "adapter" in ingestion:
        errors.append(f"{path}.ingestion.adapter cannot accompany behaviour")
    for section in ("discovery", "ingestion"):
        task = sections[section].get("task")
        if task is not None and (not isinstance(task, str) or not task.strip()):
            errors.append(f"{path}.{section}.task must be a non-empty string")
    if adapter in _ADAPTERS:
        specialized = _SPECIALIZED_BEHAVIOURS.get(identifier) == adapter
        for section, fields in (
            ("ingestion", ("task",)),
            ("discovery", ("task", "base_path_default")),
        ):
            for field in fields:
                if (not specialized or field == "task") and (
                    not isinstance(sections[section].get(field), str)
                    or not sections[section][field].strip()
                ):
                    errors.append(
                        f"{path}.{section}.{field} must be a non-empty string"
                    )
        if not specialized:
            _validate_default_layout(sections, path, errors)
            env_name = sections["discovery"].get("base_path_env")
            if env_name is not None and (
                not isinstance(env_name, str) or not env_name.strip()
            ):
                errors.append(
                    f"{path}.discovery.base_path_env must be a non-empty string"
                )
        if "implementation" in sections["ingestion"]:
            errors.append(f"{path}.ingestion.implementation is selected by dataset id")
        if adapter == "fifo_granules":
            _validate_retention(sections["ingestion"], path, errors)
        suffix = sections["discovery"].get("path_suffix", "")
        if (
            not isinstance(suffix, str)
            or Path(suffix).is_absolute()
            or ".." in Path(suffix).parts
        ):
            errors.append(f"{path}.discovery.path_suffix must be a relative path")
    return adapter


def _validate_dataset(
    raw: Any, index: int, errors: List[str]
) -> Optional[DatasetConfig]:
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
        sections[section_name] = _require_mapping(
            raw.get(section_name), f"{path}.{section_name}", errors
        )

    for section, default_task in (
        ("discovery", "discover_dataset"),
        ("ingestion", "ingest_dataset"),
    ):
        if "task" not in sections[section]:
            sections[section] = {**sections[section], "task": default_task}

    adapter = _validate_ingestion_behaviour(identifier, sections, path, errors)

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


def _validate_unique(
    values: Iterable[Tuple[str, str]], errors: List[str], label: str
) -> None:
    seen: Dict[str, str] = {}
    for value, identifier in values:
        previous = seen.get(value)
        if previous:
            errors.append(
                f"{label} {value!r} is duplicated by {previous!r} and {identifier!r}"
            )
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
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int)
        ):
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
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int)
            ):
                errors.append(
                    f"datasets[{index}].geoserver.cache.{key} must be an integer"
                )
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
    _validate_unique(
        ((config.identifier, config.identifier) for config in configs),
        errors,
        "dataset id",
    )

    if errors:
        raise ManifestError("Invalid dataset manifest:\n- " + "\n- ".join(errors))
    return configs


def load_manifest(
    path: Optional[Union[str, os.PathLike]] = None,
) -> Tuple[DatasetConfig, ...]:
    """Load and validate a manifest from an explicit path or environment variable."""

    document = _load_document(path)
    return validate_manifest(document)


def load_cache_defaults(
    path: Optional[Union[str, os.PathLike]] = None,
) -> Dict[str, Any]:
    """Return the manifest-wide GeoServer cache defaults after validation."""

    document = _load_document(path)
    validate_manifest(document)
    geoserver = document.get("geoserver", {})
    cache = geoserver.get("cache", {}) if isinstance(geoserver, Mapping) else {}
    return dict(cache)


def _load_document(path: Optional[Union[str, os.PathLike]] = None) -> Any:
    """Read the raw manifest document from a path or DATASET_CONFIG_PATH."""
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
        raise ManifestError(
            f"cannot read dataset manifest {manifest_path}: {exc}"
        ) from exc
    except yaml.YAMLError as exc:
        raise ManifestError(
            f"cannot parse dataset manifest {manifest_path}: {exc}"
        ) from exc

    return document
