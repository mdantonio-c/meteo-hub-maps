"""Generic manifest-driven dataset endpoints."""

from pathlib import Path
from typing import Any, Dict

from maps.datasets.registry import load_registry
from maps.datasets.paths import dataset_base_path, safe_dataset_file_path
from maps.utils.downloader import CustomDownloader as Downloader
from restapi import decorators
from restapi.env import Env
from restapi.exceptions import NotFound
from restapi.rest.definition import EndpointResource, Response


def _dataset_base_path(config) -> Path:
    try:
        return dataset_base_path(config, Env.get)
    except ValueError as exc:
        raise NotFound(str(exc)) from exc


def _metadata(config) -> Dict[str, Any]:
    geoserver = config.geoserver
    variables = geoserver.get("variables", {})
    layers = []
    if isinstance(variables, dict):
        for variable, details in variables.items():
            if isinstance(details, dict):
                layer_name = details.get("layer_name")
                if isinstance(layer_name, str):
                    layers.append({"variable": variable, "layer": layer_name})

    return {
        "id": config.identifier,
        "kind": config.kind,
        "display_name": config.raw.get("display_name", config.identifier),
        "adapter": config.adapter,
        "capabilities": config.endpoint.get("operations", []),
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
    try:
        return safe_dataset_file_path(config, relative_path, Env.get)
    except ValueError as exc:
        raise NotFound(str(exc)) from exc


class DatasetMetadataEndpoint(EndpointResource):
    labels = ["datasets"]

    @decorators.endpoint(
        path="/datasets/<dataset>",
        summary="Get metadata and capabilities for a configured dataset.",
        responses={200: "Dataset metadata", 404: "Dataset does not exist"},
    )
    def get(self, dataset: str) -> Response:
        config = load_registry().get(dataset)
        return self.response(_metadata(config))


class DatasetFileEndpoint(EndpointResource):
    labels = ["datasets"]

    @decorators.endpoint(
        path="/datasets/<dataset>/files/<path:relative_path>",
        summary="Download an explicitly configured dataset file.",
        responses={200: "Dataset file", 404: "Dataset or file does not exist"},
    )
    def get(self, dataset: str, relative_path: str) -> Response:
        config = load_registry().get(dataset)
        file_path = _safe_file_path(config, relative_path)
        return Downloader.send_file_content(
            file_path.name, file_path.parent, "application/octet-stream"
        )
