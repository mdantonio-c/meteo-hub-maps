from restapi import decorators
from restapi.exceptions import NotFound
from restapi.rest.definition import EndpointResource, Response
import os
import glob
from datetime import datetime

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
        seasonal_path = "/seasonal-aim"
        last = None
        status = None
        if not os.path.exists(seasonal_path):
            raise NotFound("Seasonal data directory not found")

        # Find all files in the seasonal directory
        files = glob.glob(os.path.join(seasonal_path, "*"))
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
        if os.path.exists(seasonal_path):
            items = os.listdir(seasonal_path)
            folders = [item for item in items if os.path.isdir(os.path.join(seasonal_path, item))]

        return self.response(
            {
                "folders": folders,
                "ingestion": {
                    "last": last,
                    "status": status
                }
            }
                )