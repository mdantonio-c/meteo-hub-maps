"""Shared helpers for dataset endpoints.

This module provides utility functions used by both static and dynamic
dataset endpoints. The actual endpoint classes are now generated
dynamically from datasets.yml by datasets_dynamic.py.
"""

from pathlib import Path
from typing import Any, Dict

from maps.datasets.registry import load_registry
from maps.datasets.paths import dataset_base_path, safe_dataset_file_path
from restapi.env import Env
from restapi.exceptions import NotFound


def _dataset_base_path(config) -> Path:
    """Get the base path for a dataset, with proper error handling."""
    try:
        return dataset_base_path(config, Env.get)
    except ValueError as exc:
        raise NotFound(str(exc)) from exc


def _metadata(config) -> Dict[str, Any]:
    """Build metadata response for a dataset.
    
    Args:
        config: Dataset configuration from manifest
        
    Returns:
        Dictionary with dataset metadata and capabilities
    """
    geoserver = config.geoserver
    variables = geoserver.get("variables", {})
    layers = []
    if isinstance(variables, dict):
        for variable, details in variables.items():
            if isinstance(details, dict):
                layer_name = details.get("layer_name")
                if isinstance(layer_name, str):
                    layers.append({"variable": variable, "layer": layer_name})

    endpoint_config = config.endpoint.get("operations", {})
    capabilities = list(endpoint_config.keys())

    return {
        "id": config.identifier,
        "kind": config.kind,
        "display_name": config.raw.get("display_name", config.identifier),
        "adapter": config.adapter,
        "capabilities": capabilities,
        "discovery": {
            "area": config.discovery.get("area"),
            "variables": config.discovery.get("variables", []),
            "runs": config.discovery.get("runs", []),
        },
        "temporal": dict(config.temporal),
        "geoserver": {
            "workspace": geoserver.get("workspace"),
            "store_type": geoserver.get("store_type"),
            "layers": layers,
        },
    }


def _safe_file_path(config, relative_path: str) -> Path:
    """Get a safe file path for dataset file download.
    
    Args:
        config: Dataset configuration from manifest
        relative_path: Relative path to the file within dataset
        
    Returns:
        Resolved absolute path to the file
        
    Raises:
        NotFound: If file access is not enabled or path is invalid
    """
    try:
        return safe_dataset_file_path(config, relative_path, Env.get)
    except ValueError as exc:
        raise NotFound(str(exc)) from exc
