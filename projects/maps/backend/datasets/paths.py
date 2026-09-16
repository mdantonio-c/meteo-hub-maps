"""Safe filesystem path resolution for configured dataset roots."""

from pathlib import Path

from .manifest import DatasetConfig, ManifestError


def dataset_base_path(config: DatasetConfig, env_get) -> Path:
    discovery = config.discovery
    env_name = discovery.get("base_path_env")
    default = discovery.get("base_path_default")
    if not isinstance(default, str) or not default:
        raise ManifestError(f"dataset {config.identifier} has no configured data path")
    value = env_get(env_name, default) if isinstance(env_name, str) else default
    return Path(value).resolve()


def safe_dataset_file_path(config: DatasetConfig, relative_path: str, env_get) -> Path:
    if "file_download" not in config.endpoint.get("operations", []):
        raise ManifestError(f"file access is not enabled for {config.identifier}")
    if not relative_path or Path(relative_path).is_absolute():
        raise ManifestError("invalid dataset file path")

    root = dataset_base_path(config, env_get)
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ManifestError("invalid dataset file path") from exc
    if not candidate.is_file():
        raise ManifestError(f"dataset file does not exist: {relative_path}")
    return candidate
