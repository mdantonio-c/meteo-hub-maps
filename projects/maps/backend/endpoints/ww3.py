from restapi import decorators
from restapi.exceptions import NotFound
from restapi.rest.definition import EndpointResource, Response
from restapi.utilities.logs import log
from pathlib import Path
import json

from restapi.env import Env

WW3_PATH = Path(Env.get("WW3_DATA_PATH", "/ww3"))

class WW3Endpoint(EndpointResource):
    labels = ["ww3"]

    @decorators.endpoint(
        path="/ww3/gradients",
        summary="List available WW3 gradient files",
        responses={
            200: "List of files successfully retrieved",
            404: "Gradients folder not found",
        },
    )
    def get(self) -> Response:
        gradients_path = WW3_PATH / "gradients"
        if not gradients_path.exists():
            raise NotFound(f"WW3 gradients path {gradients_path} does not exist")

        files = [f.name for f in gradients_path.iterdir() if f.is_file()]
        files.sort()
        
        return self.response(files)

class WW3FileEndpoint(EndpointResource):
    labels = ["ww3"]
    
    @decorators.endpoint(
        path="/ww3/gradients/<filename>",
        summary="Get a specific WW3 gradient file",
        responses={
            200: "File content",
            404: "File not found",
        },
    )
    def get(self, filename: str) -> Response:
        gradients_path = WW3_PATH / "gradients"
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
