from restapi import decorators
from restapi.exceptions import NotFound
from restapi.rest.definition import EndpointResource, Response
from restapi.services.download import Downloader
from restapi.env import Env
import os
import glob
from datetime import datetime

SEASONAL_PATH = Env.get("SEASONAL_DATA_PATH", "/seasonal-aim")
BOXPLOT_FOLDER_NAME = "boxplot"
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
        folder_path = os.path.join(SEASONAL_PATH, BOXPLOT_FOLDER_NAME)
        if not os.path.exists(folder_path):
            raise NotFound("Boxplot folder not found")
            
        files = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
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
        
        folder_path = os.path.join(SEASONAL_PATH, BOXPLOT_FOLDER_NAME)
        file_path = os.path.join(folder_path, filename)

        if not os.path.exists(file_path):
            raise NotFound("File not found")
            
        return Downloader.send_file_content(filename, folder_path, 'application/octet-stream')