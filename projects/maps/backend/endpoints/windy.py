from typing import List, Optional

from maps.endpoints.config import (
    DATASETS,
    DEFAULT_PLATFORM,
    RUNS,
    DatasetType,
    get_base_path,
    get_ready_file,
)
from restapi import decorators
from restapi.exceptions import NotFound
from restapi.models import fields, validate
from restapi.rest.definition import EndpointResource, Response
from restapi.utilities.logs import log
from restapi.services.download import Downloader

class WindyEndpoint(EndpointResource):
    labels = ["windy"]

    @decorators.use_kwargs(
        {
            "dataset": fields.Str(
                required=True, validate=validate.OneOf(DATASETS.keys())
            ),
            "run": fields.Str(validate=validate.OneOf(RUNS)),
            "foldername":fields.Str(required=False),
            "filename": fields.Str(required=False),
        },
        location="query",
    )
    @decorators.endpoint(
        path="/windy",
        summary="Get the last available windy map set as a reference time or download its data.",
        responses={
            200: "Windy map successfully retrieved",
            400: "Invalid parameters",
            404: "Windy map does not exists",
        },
    )
    def get(self, dataset: str, run: Optional[str] = None, foldername: Optional[str] = None, filename: Optional[str] = None, stream: Optional[bool] = False) -> Response:

        info: Optional[DatasetType] = DATASETS.get(dataset)
        if not info:
            raise NotFound(f"Dataset {dataset} is not available")

        area: str = info.get("area", "")

        if not area:
            raise NotFound(f"Dataset area not available for {dataset}")

        ready_file: Optional[str] = None
        # check for run param: if not provided get the "last" run available
        if not run:
            log.debug("No run param provided: look for the last run available")
            ready_files: List[str] = []
            latest_x = None

            for r in ["00", "12"]:
                base_path = get_base_path("windy", DEFAULT_PLATFORM, "DEV", r, dataset)
                x = get_ready_file(base_path, area)
                # add walrus here
                if x:
                    ready_files.append(x.name)
                    latest_x = x
            try:
                ready_file = max(ready_files)
            except ValueError:
                log.warning("No Run is available: .READY file not found")
        else:
            base_path = get_base_path("windy", DEFAULT_PLATFORM, "DEV", run, dataset)
            tmp_ready_file = get_ready_file(base_path, area)
            if tmp_ready_file:
                ready_file = tmp_ready_file.name

        if not ready_file:
            raise NotFound("No .READY file found")

        if not foldername:
            response = {
                "dataset": dataset,
                "area": info["area"],
                "start_offset": info["start_offset"],
                "end_offset": info["end_offset"],
                "step": info["step"],
                "boundaries": info["boundaries"],
                "reftime": ready_file[:10],
                "platform": None,
            }
            return self.response(response)

        filepath = latest_x.parent.joinpath(foldername).joinpath(filename)
        if not filepath.exists() or not filepath.is_file():
            raise NotFound(f"File {filepath} does not exist")
        if not stream:
            return Downloader.send_file_content(filepath.name, filepath.parent, 'image/tif')
        else:
            return Downloader.send_file_streamed(filepath.name, filepath.parent, 'image/tif')
