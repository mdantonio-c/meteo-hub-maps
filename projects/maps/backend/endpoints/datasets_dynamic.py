"""Dynamic endpoint generation from datasets.yml manifest.

This module reads the dataset manifest at import time and generates
endpoint classes based on each dataset's `endpoint.operations` configuration.
This allows adding/removing API endpoints by editing YAML only.

The generated classes are discovered by RAPyDo's EndpointsLoader automatically.
"""

import re
from pathlib import Path
from typing import Any, Dict, Optional, Type

from maps.datasets.manifest import load_manifest
from maps.datasets.registry import DatasetRegistry
from maps.datasets.status import ingestion_status
from restapi import decorators
from restapi.env import Env
from restapi.exceptions import NotFound
from restapi.rest.definition import EndpointResource, Response
from restapi.utilities.logs import log

from .datasets import _metadata, _safe_file_path
from maps.utils.downloader import CustomDownloader as Downloader


def create_metadata_endpoint_class(dataset_id: str, route: str) -> Type[EndpointResource]:
    """Create a metadata endpoint class for a specific dataset.
    
    Standard response model for all metadata endpoints:
    {
        "id": str,              # Dataset identifier
        "kind": str,            # Dataset kind (forecast, observation, marine)
        "display_name": str,    # Human-readable name
        "adapter": str,         # Ingestion adapter type
        "capabilities": list,   # Available operations [metadata, file_download, status, stations]
        "discovery": {
            "area": str|null,
            "variables": list,
            "runs": list
        },
        "temporal": {
            "filename_regex": str,
            "filename_format": str,
            "timezone": str
        },
        "geoserver": {
            "workspace": str,
            "store_type": str,
            "layers": [{"variable": str, "layer": str}]
        }
    }
    """
    
    class _DynamicMetadataEndpoint(EndpointResource):
        labels = ["datasets", f"dataset-{dataset_id}"]
        
        def get(self) -> Response:
            """Get metadata for dataset."""
            registry = DatasetRegistry(load_manifest())
            config = registry.get(dataset_id)
            return self.response(_metadata(config))
    
    # Apply the endpoint decorator after class creation
    _DynamicMetadataEndpoint.get = decorators.endpoint(
        path=route,
        summary=f"Get metadata and capabilities for {dataset_id} dataset.",
        responses={200: "Dataset metadata", 404: "Dataset does not exist"},
    )(_DynamicMetadataEndpoint.get)
    
    # Set class name for better debugging
    _DynamicMetadataEndpoint.__name__ = f"{dataset_id.capitalize()}MetadataEndpoint"
    _DynamicMetadataEndpoint.__module__ = __name__
    
    return _DynamicMetadataEndpoint


def create_file_download_endpoint_class(dataset_id: str, route: str) -> Type[EndpointResource]:
    """Create a file download endpoint class for a specific dataset.
    
    Standard behavior for all file download endpoints:
    - Returns binary file content with appropriate Content-Type
    - Path traversal is prevented by _safe_file_path()
    - 404 if dataset or file doesn't exist
    """
    
    class _DynamicFileEndpoint(EndpointResource):
        labels = ["datasets", f"dataset-{dataset_id}"]
        
        def get(self, relative_path: str) -> Response:
            """Download a file from dataset."""
            registry = DatasetRegistry(load_manifest())
            config = registry.get(dataset_id)
            file_path = _safe_file_path(config, relative_path)
            return Downloader.send_file_content(
                file_path.name, file_path.parent, "application/octet-stream"
            )
    
    # Apply the endpoint decorator after class creation
    _DynamicFileEndpoint.get = decorators.endpoint(
        path=route,
        summary=f"Download a file from {dataset_id} dataset.",
        responses={200: "Dataset file", 404: "Dataset or file does not exist"},
    )(_DynamicFileEndpoint.get)
    
    # Set class name for better debugging
    _DynamicFileEndpoint.__name__ = f"{dataset_id.capitalize()}FileEndpoint"
    _DynamicFileEndpoint.__module__ = __name__
    
    return _DynamicFileEndpoint


def create_status_endpoint_class(dataset_id: str, route: str) -> Type[EndpointResource]:
    """Create a status endpoint class for a specific dataset.
    
    The route may contain path parameters like {radar_type}.
    These are extracted and passed to the get() method.
    
    Standard response model for all status endpoints:
    {
        "id": str,                  # Dataset identifier
        "kind": str,                # Dataset kind (forecast, observation, marine)
        "display_name": str,        # Human-readable name
        "ingestion": {
            "status": str,          # ready|pending|unknown
            "lastRun": str|null,    # Latest run identifier
            "lastUpdate": str|null, # ISO timestamp of last ingestion
            "pendingImport": {...}|null
        },
        "data": {
            "area": str|null,
            "variables": list,
            "runs": list
        }
    }
    """
    import re
    # Extract path parameters from route (e.g., {radar_type} -> radar_type)
    path_params = re.findall(r'<(\w+)(?::[^>]+)?>', route)
    
    class _DynamicStatusEndpoint(EndpointResource):
        labels = ["datasets", f"dataset-{dataset_id}"]
        
        def get(self, **kwargs) -> Response:
            """Get ingestion status for dataset."""
            registry = DatasetRegistry(load_manifest())
            config = registry.get(dataset_id)
            discovery = config.discovery
            
            # Build standard response model
            response_data: Dict[str, Any] = {
                "id": config.identifier,
                "kind": config.kind,
                "display_name": config.raw.get("display_name", config.identifier),
                "ingestion": ingestion_status(config, kwargs),
                "data": {
                    "area": discovery.get("area"),
                    "variables": discovery.get("variables", []),
                    "runs": discovery.get("runs", []),
                },
            }
            
            # Include path parameters in response if any (e.g., radar_type)
            if path_params:
                for param in path_params:
                    if param in kwargs:
                        response_data[param] = kwargs[param]
            
            return self.response(response_data)
    
    # Apply the endpoint decorator after class creation
    _DynamicStatusEndpoint.get = decorators.endpoint(
        path=route,
        summary=f"Get ingestion status for {dataset_id} dataset.",
        responses={200: "Dataset status", 404: "Dataset does not exist"},
    )(_DynamicStatusEndpoint.get)
    
    # Set class name for better debugging
    _DynamicStatusEndpoint.__name__ = f"{dataset_id.capitalize()}StatusEndpoint"
    _DynamicStatusEndpoint.__module__ = __name__
    
    return _DynamicStatusEndpoint


def create_stations_endpoint_class(dataset_id: str, route: str) -> Type[EndpointResource]:
    """Create a stations endpoint class for marine datasets.
    
    The route may contain path parameters.
    
    Standard response model for stations endpoints:
    {
        "id": str,              # Dataset identifier
        "kind": str,            # Always "marine"
        "display_name": str,    # Human-readable name
        "base_path": {
            "env": str,         # Environment variable for path
            "default": str      # Default path if env not set
        },
        "forcings": list        # Available forcing providers (if applicable)
    }
    """
    import re
    # Extract path parameters from route
    path_params = re.findall(r'<(\w+)(?::[^>]+)?>', route)
    
    class _DynamicStationsEndpoint(EndpointResource):
        labels = ["datasets", f"dataset-{dataset_id}", "marine"]
        
        def get(self, **kwargs) -> Response:
            """Get station list for marine dataset."""
            registry = DatasetRegistry(load_manifest())
            config = registry.get(dataset_id)
            
            if config.kind != "marine":
                raise NotFound("Stations endpoint only available for marine datasets")
            
            discovery = config.discovery
            base_path_env = discovery.get("base_path_env")
            base_path_default = discovery.get("base_path_default")
            forcings = discovery.get("forcings", [])
            
            # Build standard response model
            response_data: Dict[str, Any] = {
                "id": config.identifier,
                "kind": config.kind,
                "display_name": config.raw.get("display_name", config.identifier),
                "base_path": {
                    "env": base_path_env,
                    "default": base_path_default,
                },
            }
            
            # Include forcings if available
            if forcings:
                response_data["forcings"] = forcings
            
            # Include path parameters in response if any
            if path_params:
                for param in path_params:
                    if param in kwargs:
                        response_data[param] = kwargs[param]
            
            return self.response(response_data)
    
    # Apply the endpoint decorator after class creation
    _DynamicStationsEndpoint.get = decorators.endpoint(
        path=route,
        summary=f"Get station list for {dataset_id} marine dataset.",
        responses={200: "Station list", 404: "Dataset does not exist"},
    )(_DynamicStationsEndpoint.get)
    
    # Set class name for better debugging
    _DynamicStationsEndpoint.__name__ = f"{dataset_id.capitalize()}StationsEndpoint"
    _DynamicStationsEndpoint.__module__ = __name__
    
    return _DynamicStationsEndpoint


# Global registry to hold dynamically generated endpoint classes
_DYNAMIC_ENDPOINTS: Dict[str, Type[EndpointResource]] = {}


def generate_dataset_endpoints() -> Dict[str, Type[EndpointResource]]:
    """Generate endpoint classes for all datasets in the manifest.
    
    This function is called at module import time to dynamically
    create endpoint classes based on the datasets.yml configuration.
    
    Returns:
        Dictionary mapping endpoint names to generated classes
    """
    global _DYNAMIC_ENDPOINTS
    _DYNAMIC_ENDPOINTS = {}
    
    try:
        # Try multiple possible locations for datasets.yml
        possible_paths = [
            Path(__file__).parent.parent.parent / "datasets.yml",  # projects/maps/datasets.yml
            Path(__file__).parent.parent.parent.parent / "datasets.yml",  # projects/datasets.yml
            Path("/etc/meteohub/datasets.yml"),  # Configured path
        ]
        
        manifest_path = None
        for path in possible_paths:
            if path.exists():
                manifest_path = path
                break
        
        if manifest_path is None:
            log.warning("datasets.yml not found in any expected location")
            return _DYNAMIC_ENDPOINTS
        
        datasets = load_manifest(manifest_path)
        log.info("Generating dynamic endpoints for {} datasets", len(datasets))
        
        for dataset_config in datasets:
            endpoint_config = dataset_config.raw.get("endpoint", {})
            if not endpoint_config:
                log.debug("No endpoint config for dataset {}", dataset_config.identifier)
                continue
            
            operations = endpoint_config.get("operations", {})
            
            if not operations:
                log.warning("No operations for dataset {}", dataset_config.identifier)
                continue
            
            dataset_id = dataset_config.identifier
            
            # operations is now a dict: {operation_name: {route: ...}}
            for operation_name, operation_config in operations.items():
                if isinstance(operation_config, dict):
                    route = operation_config.get("route")
                    if not route:
                        log.warning(
                            "No route for operation {} in dataset {}",
                            operation_name, dataset_id
                        )
                        continue
                    # Substitute {dataset} placeholder with actual dataset_id
                    route = route.replace("{dataset}", dataset_id)
                    # Convert {param} style path parameters to Flask <param> syntax
                    route = re.sub(r'\{(\w+)\}', r'<\1>', route)
                else:
                    log.warning(
                        "Invalid operation config for {} in dataset {}",
                        operation_name, dataset_id
                    )
                    continue
                
                endpoint_class = _create_endpoint_for_operation(
                    dataset_id, operation_name, route
                )
                if endpoint_class:
                    endpoint_name = f"{dataset_id}_{operation_name}"
                    _DYNAMIC_ENDPOINTS[endpoint_name] = endpoint_class
                    
                    # IMPORTANT: Export the class as a module-level attribute
                    # so RAPyDo's EndpointsLoader can discover it via introspection
                    globals()[endpoint_class.__name__] = endpoint_class
                    
                    log.info(
                        "Created endpoint class {} for {} {}",
                        endpoint_class.__name__, dataset_id, operation_name
                    )
        
        log.info(
            "Generated {} dynamic endpoint classes",
            len(_DYNAMIC_ENDPOINTS)
        )
        
    except Exception as e:
        log.error("Failed to generate dynamic dataset endpoints: {}", e)
        import traceback
        log.error("Traceback: {}", traceback.format_exc())
    
    return _DYNAMIC_ENDPOINTS


def _create_endpoint_for_operation(
    dataset_id: str,
    operation: str,
    route: str,
) -> Optional[Type[EndpointResource]]:
    """Create an endpoint class for a specific dataset operation."""
    
    if operation == "metadata":
        return create_metadata_endpoint_class(dataset_id, route)
    elif operation == "file_download":
        return create_file_download_endpoint_class(dataset_id, route)
    elif operation == "status":
        return create_status_endpoint_class(dataset_id, route)
    elif operation == "stations":
        return create_stations_endpoint_class(dataset_id, route)
    else:
        log.warning("Unknown operation: {} for dataset {}", operation, dataset_id)
        return None


# Generate endpoints at module import time
# This ensures RAPyDo's EndpointsLoader will discover them
generate_dataset_endpoints()
