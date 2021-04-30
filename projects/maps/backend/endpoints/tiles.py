from functools import lru_cache
from typing import Optional

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


class TilesEndpoint(EndpointResource):
    labels = ["tiles"]

    @decorators.use_kwargs(
        {
            "dataset": fields.Str(
                required=True, validate=validate.OneOf(DATASETS.keys())
            ),
            "run": fields.Str(validate=validate.OneOf(RUNS)),
        },
        location="query",
    )
    @decorators.endpoint(
        path="/tiles",
        summary="Get the last available tiled map set as a reference time.",
        responses={
            200: "Tiled map successfully retrieved",
            400: "Invalid parameters",
            404: "Tiled map does not exists",
        },
    )
    def get(self, dataset: str, run: Optional[str] = None) -> Response:

        info: Optional[DatasetType] = DATASETS.get(dataset)
        if not info:
            raise NotFound(f"Dataset {dataset} is not available")

        area: str = info.get("area")

        ready_file: Optional[str] = None
        # check for run param: if not provided get the "last" run available
        if not run:
            log.debug("No run param provided: look for the last run available")
            ready_files = [
                x
                for x in (self._get_ready_file(area, r, dataset) for r in ["00", "12"])
                if x is not None
            ]
            try:
                ready_file = max(ready_files)
            except ValueError:
                log.warning("No Run is available: .READY file not found")
        else:
            base_path = get_base_path("tiles", DEFAULT_PLATFORM, "PROD", run, dataset)
            ready_file = get_ready_file(base_path, area)

        if not ready_file:
            raise NotFound("No .READY file found")

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

    @lru_cache
    def _get_ready_file(self, area: str, run: str, dataset: str) -> Optional[str]:
        base_path = get_base_path("tiles", DEFAULT_PLATFORM, "PROD", run, dataset)
        try:
            return get_ready_file(base_path, area)
        except NotFound:
            return None
