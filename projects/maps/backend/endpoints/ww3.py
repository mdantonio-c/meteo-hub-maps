from restapi import decorators
from restapi.exceptions import NotFound
from restapi.rest.definition import EndpointResource, Response
from restapi.utilities.logs import log
from pathlib import Path
import json
from datetime import datetime

from restapi.env import Env

WW3_PATH = Path(Env.get("WW3_DATA_PATH", "/ww3"))

class WW3Endpoint(EndpointResource):
    labels = ["ww3"]

    @decorators.endpoint(
        path="/ww3/vectors",
        summary="List available WW3 vectors files",
        responses={
            200: "List of files successfully retrieved",
            404: "Vectors folder not found",
        },
    )
    def get(self) -> Response:
        vectors_path = WW3_PATH / "dir-dir"
        if not vectors_path.exists():
            raise NotFound(f"WW3 vectors path {vectors_path} does not exist")

        files = [f.name for f in vectors_path.iterdir() if f.is_file()]
        files.sort()
        
        return self.response(files)

class WW3FileEndpoint(EndpointResource):
    labels = ["ww3"]
    
    @decorators.endpoint(
        path="/ww3/vectors/<filename>",
        summary="Get a specific WW3 vector file",
        responses={
            200: "File content",
            404: "File not found",
        },
    )
    def get(self, filename: str) -> Response:
        gradients_path = WW3_PATH / "dir-dir"
        file_path = gradients_path / filename
        
        if not file_path.exists():
            raise NotFound(f"File {filename} not found")
            
        try:
            with open(file_path, 'r') as f:
                content = json.load(f)
            return self.response(content)
        except Exception as e:
            log.error(f"Error reading file {filename}: {e}")
            raise NotFound(f"Error reading file {filename}")

class WW3StatusEndpoint(EndpointResource):
    labels = ["ww3"]

    @decorators.endpoint(
        path="/ww3/status",
        summary="Get the status of a specific WW3 variable: hs, t01, vector",
        responses={
            200: "Status information",
            404: "Variable or run not found",
        },
    )
    def get(self) -> Response:
        # Find latest run from .READY files
        ready_files = sorted([f for f in WW3_PATH.glob("*.READY") if not f.name.endswith(".GEOSERVER.READY")], reverse=True)
        if not ready_files:
            raise NotFound("No READY files found")
        
        latest_ready = ready_files[0]
        run_date_str = latest_ready.name.split('.READY')[0]
        
        try:
            if len(run_date_str) == 8:
                run_date = datetime.strptime(run_date_str, "%Y%m%d")
            elif len(run_date_str) == 10:
                run_date = datetime.strptime(run_date_str, "%Y%m%d%H")
            else:
                raise ValueError("Unknown format")
        except ValueError:
             raise NotFound(f"Invalid date format in READY file: {latest_ready.name}")

        start_offset = 0
        end_offset = 0
        step = 1
        
        # Find GEOSERVER.READY file to get offsets
        gs_ready_files = sorted(WW3_PATH.glob("*.GEOSERVER.READY"), reverse=True)
        
        if gs_ready_files:
            latest_gs_ready = gs_ready_files[0]
            filename = latest_gs_ready.name
            name_part = filename.split('.GEOSERVER.READY')[0]
            
            if '-' in name_part:
                start_str, end_str = name_part.split('-')
                try:
                    start_dt = datetime.strptime(start_str, "%Y%m%d%H")
                    end_dt = datetime.strptime(end_str, "%Y%m%d%H")
                    
                    start_offset = int((start_dt - run_date).total_seconds() / 3600)
                    end_offset = int((end_dt - run_date).total_seconds() / 3600)
                except ValueError:
                    log.warning(f"Could not parse range from {filename}")

        response = {
            "reftime": run_date.strftime("%Y%m%d%H"),
            "start_offset": start_offset,
            "end_offset": end_offset,
            "step": step,
            "dataset": "ww3"
        }
        
        return self.response(response)
