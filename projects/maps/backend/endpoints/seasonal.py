import glob
import json
import os
from datetime import datetime
from pathlib import Path

from maps.datasets.registry import load_registry
from maps.endpoints.datasets import _dataset_base_path
from restapi import decorators
from restapi.env import Env
from restapi.exceptions import NotFound
from restapi.rest.definition import EndpointResource, Response
from restapi.utilities.logs import log

SEASONAL_PATH = Env.get("SEASONAL_DATA_PATH", "/seasonal-aim")
BOXPLOT_FOLDER_NAME = "boxplot"


def _boxplot_path() -> Path:
    if Env.get_bool("ACTIVATE_DYNAMIC_DATASETS"):
        config = load_registry().get("seasonal")
        return (_dataset_base_path(config) / BOXPLOT_FOLDER_NAME).resolve()
    return (Path(SEASONAL_PATH) / BOXPLOT_FOLDER_NAME).resolve()


class SeasonalEndpoint(EndpointResource):
    labels = ["seasonal"]

    @decorators.endpoint(
        path="/seasonal/latest",
        summary="Get the last available seasonal data.",
        responses={
            200: "Seasonal data successfully retrieved",
            400: "Invalid parameters",
            404: "Seasonal data does not exist",
        },
    )
    def get(self) -> Response:
        last = None
        status = None
        if not os.path.exists(SEASONAL_PATH):
            raise NotFound("Seasonal data directory not found")

        # Find all files in the seasonal directory
        files = glob.glob(os.path.join(SEASONAL_PATH, "*"))
        # Filter files ending with .CHECKED and .READY
        filtered_files = [f for f in files if f.endswith(('.CHECKED', '.READY'))]
        if filtered_files:
            # Check for files ending with GEOSERVER.READY
            geoserver_ready_files = [f for f in filtered_files if f.endswith('.GEOSERVER.READY')]
            checked_ready_files = [f for f in filtered_files if f.endswith('.CELERY.CHECKED')]
            if geoserver_ready_files:
                geoserver_ready_files.sort(key=os.path.getmtime, reverse=True)
                latest_file = os.path.basename(geoserver_ready_files[0])
                date = latest_file.split('.')[0]
                try:
                    parsed_date = datetime.strptime(date, '%Y%m%d')
                    last = parsed_date.strftime('%Y-%m-%d')
                except ValueError:
                    last = None  # fallback if parsing fails
                status = "ingested"
            elif checked_ready_files:
                checked_ready_files.sort(key=os.path.getmtime, reverse=True)
                latest_file = os.path.basename(checked_ready_files[0])
                date = latest_file.split('.')[0]
                try:
                    parsed_date = datetime.strptime(date, '%Y%m%d')
                    last = parsed_date.strftime('%Y-%m-%d')
                except ValueError:
                    last = None  # fallback if parsing fails
                status = "ingesting"
        else:
            last = None
            status = None
            
        
        folders = []
        if os.path.exists(SEASONAL_PATH):
            items = os.listdir(SEASONAL_PATH)
            folders = [item for item in items if os.path.isdir(os.path.join(SEASONAL_PATH, item))]

        return self.response(
            {
                "folders": folders,
                "ingestion": {
                    "last": last,
                    "status": status
                }
            }
                )

class SeasonalBoxplotListEndpoint(EndpointResource):
    # These dataset-specific routes have no generated replacement in dynamic mode.
    labels = ["seasonal"]

    @decorators.endpoint(
        path="/seasonal/json",
        summary="List all files in the boxplot folder",
        responses={
            200: "List of files successfully retrieved",
            404: "Boxplot folder not found",
        },
    )
    def get(self) -> Response:
        folder_path = _boxplot_path()
        if not folder_path.is_dir():
            raise NotFound("Boxplot folder not found")

        files = []
        for item in folder_path.iterdir():
            if item.is_file():
                try:
                    item.resolve().relative_to(folder_path)
                except ValueError:
                    continue
                files.append(item.name)
        files.sort()
        return self.response(files)

class SeasonalFileEndpoint(EndpointResource):
    labels = ["seasonal"]

    @decorators.endpoint(
        path="/seasonal/json/<filename>",
        summary="Get a specific seasonal file",
        responses={
            200: "File content",
            404: "File not found",
        },
    )
    def get(self, filename: str) -> Response:
        folder_path = _boxplot_path()
        if Path(filename).is_absolute():
            raise NotFound("Invalid file path")
        file_path = (folder_path / filename).resolve()
        try:
            file_path.relative_to(folder_path)
        except ValueError as e:
            raise NotFound("Invalid file path") from e
        if not file_path.is_file():
            raise NotFound("File not found")
        try:
            with file_path.open(encoding="utf-8") as f:
                content = json.load(f)
        except (OSError, ValueError) as e:
            log.error(f"Error reading seasonal json file {filename}: {e}")
            raise NotFound(f"Error reading file {filename}") from e
        return self.response(content)
