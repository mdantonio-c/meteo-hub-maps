import os
from functools import lru_cache
from typing import Optional

from maps.endpoints.config import (
    DATASETS,
    MEDIA_ROOT,
    RUNS,
    DatasetType,
    get_ready_file,
)
from restapi import decorators
from restapi.exceptions import NotFound
from restapi.models import fields, validate
from restapi.rest.definition import EndpointResource, Response
from restapi.utilities.logs import log


class TilesEndpoint(EndpointResource):
    labels = ["tiles"]

    @staticmethod
    @lru_cache
    def get_base_path(run: str, dataset: str) -> str:
        # e.g. Tiles-00-lm2.2.web
        return os.path.join(MEDIA_ROOT, "PROD", f"Tiles-{run}-{dataset}.web")

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
        ready_file: Optional[str] = None
        info: DatasetType = DATASETS.get(dataset, {})
        area: str = info.get("area")

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
            base_path = self.get_base_path(run, dataset)
            ready_file = get_ready_file(base_path, area)

        if not ready_file:
            raise NotFound("No .READY file found")

        info["dataset"] = dataset
        info["reftime"] = ready_file[:10]
        info["platform"] = None
        return self.response(info)

    @lru_cache
    def _get_ready_file(self, area: str, run: str, dataset: str) -> Optional[str]:
        base_path = self.get_base_path(run, dataset)
        try:
            return get_ready_file(base_path, area)
        except NotFound:
            return None
