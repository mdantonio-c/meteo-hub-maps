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
        path="/ww3/<var>/status",
        summary="Get the status of a specific WW3 variable: hs, t01, vector",
        responses={
            200: "Status information",
            404: "Variable or run not found",
        },
    )
    def get(self, var: str) -> Response:
        if var not in ['hs', 't01', 'vector']:
            raise NotFound(f"Variable {var} not found")
        var = 'dir-dir' if var == 'vector' else var + '-' + var

        # Find latest run
        ready_files = sorted(WW3_PATH.glob("*.GEOSERVER.READY"), reverse=True)
        if not ready_files:
            raise NotFound("No ready files found")
        
        latest_ready = ready_files[0]
        # Extract date: 20251203.GEOSERVER.READY -> 20251203
        run_date_str = latest_ready.name.split('.')[0]
        
        try:
            run_date = datetime.strptime(run_date_str, "%Y%m%d")
        except ValueError:
            raise NotFound(f"Invalid run date format in {latest_ready.name}")

        var_path = WW3_PATH / var
        if not var_path.exists():
             raise NotFound(f"Variable folder {var} not found")

        files = []
        if var == 'dir-dir':
            for f in var_path.glob("*.json"):
                try:
                    dt = datetime.strptime(f.stem, "%Y%m%d_%H")
                    if dt >= run_date:
                        files.append(dt)
                except ValueError:
                    continue
        else:
            for f in var_path.glob("*.tif"):
                try:
                    dt = datetime.strptime(f.stem, "%d-%m-%Y-%H")
                    if dt >= run_date:
                        files.append(dt)
                except ValueError:
                    continue
        
        files = sorted(list(set(files)))
        
        start_offset = 0
        end_offset = 0
        step = 1
        
        if files:
            start_offset = int((files[0] - run_date).total_seconds() / 3600)
            end_offset = int((files[-1] - run_date).total_seconds() / 3600)
            if len(files) > 1:
                step = int((files[1] - files[0]).total_seconds() / 3600)
        
        response = {
            "reftime": run_date.strftime("%Y%m%d%H"),
            "start_offset": start_offset,
            "end_offset": end_offset,
            "step": step,
            "dataset": var
        }
        
        return self.response(response)
