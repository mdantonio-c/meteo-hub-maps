from datetime import datetime
from typing import Dict, Optional, Type, Union

from maps.auth.authz import check_ip_access
from maps.endpoints.config import (
    AREAS,
    DEFAULT_PLATFORM,
    ENVS,
    FIELDS,
    LEVELS_PE,
    LEVELS_PR,
    PLATFORMS,
    RESOLUTIONS,
    RUNS,
    WEEKDAYS,
    check_platform_availability,
    get_base_path,
    get_ready_file,
)
from maps.utils.env import Env
from restapi import decorators
from restapi.exceptions import NotFound, ServiceUnavailable
from restapi.models import Schema, fields, validate
from restapi.rest.definition import EndpointResource, Response
from restapi.services.download import Downloader
from restapi.utilities.logs import log

ALLOWED_IPS = Env.get_set("ALLOWED_IPS", frozenset())

def get_schema(set_required: bool) -> Type[Schema]:
    attributes: Dict[str, Union[fields.Field, type]] = {}
    attributes["run"] = fields.Str(validate=validate.OneOf(RUNS), required=True)
    attributes["res"] = fields.Str(validate=validate.OneOf(RESOLUTIONS), required=True)
    attributes["field"] = fields.Str(validate=validate.OneOf(FIELDS), required=True)
    attributes["area"] = fields.Str(validate=validate.OneOf(AREAS), required=True)
    attributes["platform"] = fields.Str(
        validate=validate.OneOf(PLATFORMS), required=set_required
    )
    attributes["level_pe"] = fields.Str(
        validate=validate.OneOf(LEVELS_PE), required=False
    )
    attributes["level_pr"] = fields.Str(
        validate=validate.OneOf(LEVELS_PR), required=False
    )
    attributes["env"] = fields.Str(validate=validate.OneOf(ENVS), required=False)
    attributes["weekday"] = fields.Str(
        validate=validate.OneOf(WEEKDAYS), required=False
    )

    return Schema.from_dict(attributes, name="MapsSchema")


class MapReadyOutputSchema(Schema):
    reftime = fields.Str(required=True)
    offsets = fields.List(fields.Str(), required=True)
    platform = fields.Str(required=True)
    weekday = fields.Str(required=True)


class MapImage(EndpointResource):
    labels = ["maps"]

    # @decorators.cache(timeout=900)
    @decorators.use_kwargs(get_schema(True), location="query")
    @decorators.endpoint(
        path="/maps/offset/<map_offset>",
        summary="Get a forecast map for a specific run and weekday, if provided.",
        responses={
            200: "Map successfully retrieved",
            400: "Invalid parameters",
            404: "Map does not exists",
        },
    )
    def get(
        self,
        map_offset: str,
        run: str,
        res: str,
        field: str,
        area: str,
        platform: str,
        level_pe: Optional[str] = None,
        level_pr: Optional[str] = None,
        weekday: Optional[str] = None,
        env: str = "PROD",
    ) -> Response:
        """Get a forecast map for a specific run."""

        # flash flood offset is a bit more complicate
        if field == "percentile":
            map_offset = f"{map_offset}_{level_pe}"
        elif field == "probability":
            map_offset = f"{map_offset}_{level_pr}"

        log.debug(f"Retrieve map image by offset <{map_offset}>")

        base_path = get_base_path(field, platform, env, run, res, weekday)

        # Check if the images are ready: 2017112900.READY
        ready_file = get_ready_file(base_path, area)
        if not ready_file:
            raise NotFound("no .READY files found")
        reftime = ready_file.name[:10]

        # get map image
        if field == "percentile":
            image_name = f"perc6.{reftime}.{map_offset}.png"
        elif field == "probability":
            image_name = f"prob6.{reftime}.{map_offset}.png"
        else:
            image_name = f"{field}.{reftime}.{map_offset}.png"

        image_path = base_path.joinpath(area, field)
        map_image_file = image_path.joinpath(image_name)

        log.debug(f"map_image_file: {map_image_file}")

        if not map_image_file.is_file():
            raise NotFound(f"Map image not found for offset {map_offset}")

        return Downloader.send_file_content(
            image_name, subfolder=image_path, mime="image/png"
        )


class MapSet(EndpointResource):
    labels = ["maps"]

    # @decorators.cache(timeout=900)
    @decorators.use_kwargs(get_schema(False), location="query")
    @decorators.endpoint(
        path="/maps/ready",
        summary="Get the last available map set for a specific run "
        "returning the reference time as well",
        responses={
            200: "Map set successfully retrieved",
            400: "Invalid parameters",
            404: "Map set does not exists",
        },
    )
    @decorators.marshal_with(MapReadyOutputSchema, code=200)
    def get(
        self,
        run: str,
        res: str,
        field: str,
        area: str,
        platform: Optional[str] = None,
        level_pe: Optional[str] = None,
        level_pr: Optional[str] = None,
        weekday: Optional[str] = None,
        env: str = "PROD",
    ) -> Response:
        """
        Get the last available map set for a specific run
        and return the reference time as well as the corresponding weekday.
        If a weekday is provided, get the last available map set for
        that weekday.
        """

        log.debug(f"Retrieve map set for last run <{run}>")

        if field == "percentile" or field == "probability":
            platform = "G100"
            log.warning("Forcing platform to {} because field is {}", platform, field)

        # if PLATFORM is not provided, set as default the first available
        # in the order: DEFAULT_PLATFORM + others
        if not platform:
            log.debug(f"PLATFORMS: {PLATFORMS}")
            log.debug(f"DEFAULT PLATFORM: {DEFAULT_PLATFORM}")
            platforms_to_be_check = [DEFAULT_PLATFORM] + list(
                set(PLATFORMS) - {DEFAULT_PLATFORM}
            )

            # check platform availability
            platforms_available = []
            for check_pl in platforms_to_be_check:
                if not check_platform_availability(check_pl):
                    log.warning(f"platform {check_pl} not available")
                    continue
                platforms_available.append(check_pl)
            if not platforms_available:
                raise ServiceUnavailable("Map service is currently unavailable")

            # check if maps are ready and which platform has the latest one
            base_path = None
            reftime = None
            for pl in platforms_available:
                # Check if the images are ready: 2017112900.READY
                temp_base_path = get_base_path(field, pl, env, run, res, weekday)
                ready_file = get_ready_file(temp_base_path, area)
                if not ready_file:
                    continue

                dt_reftime = datetime.strptime(ready_file.name[:10], "%Y%m%d%H")
                if not reftime or dt_reftime > reftime:  # type: ignore
                    reftime = dt_reftime
                    base_path = get_base_path(field, pl, env, run, res, weekday)
                    platform = pl
                    last_reftime = reftime.strftime("%Y%m%d%H")
                    last_weekday = str(
                        datetime.strptime(ready_file.name[:8], "%Y%m%d").weekday()
                    )

            if not base_path:
                raise NotFound("no .READY files found")

        else:
            # check platform availability
            if not check_platform_availability(platform):
                raise ServiceUnavailable(
                    f"Map service is currently unavailable for {platform} platform"
                )
            # check if there is a ready file
            base_path = get_base_path(field, platform, env, run, res, weekday)
            ready_file = get_ready_file(base_path, area)
            if not ready_file:
                raise NotFound("no .READY files found")
            last_reftime = ready_file.name[:10]
            last_weekday = str(
                datetime.strptime(ready_file.name[:8], "%Y%m%d").weekday()
            )
        # load image offsets
        images_path = base_path.joinpath(area, field)
        list_file = sorted(images_path.iterdir())
        if field == "percentile" or field == "probability":
            offsets = []
            # flash flood offset is a bit more complicate
            for f in list_file:
                if f.is_file():
                    offset = f.name.split(".")[-2]
                    # offset is like this now: 0006_10
                    offset, level = offset.split("_")
                    if field == "percentile" and level_pe == level:
                        offsets.append(offset)
                    elif field == "probability" and level_pr == level:
                        offsets.append(offset)
        else:
            offsets = [f.name.split(".")[-2] for f in list_file if f.is_file()]

        log.debug("data offsets: {}", offsets)
        log.info(f"But just before printing {weekday}")
        data = {
            "reftime": last_reftime,
            "offsets": offsets,
            "platform": platform,
            "weekday": last_weekday,
        }
        return self.response(data)


class MapLegend(EndpointResource):
    labels = ["maps"]

    # @decorators.cache(timeout=900)
    @decorators.use_kwargs(get_schema(True), location="query")
    @decorators.endpoint(
        path="/maps/legend",
        summary="Get a specific forecast map legend.",
        responses={
            200: "Legend successfully retrieved",
            400: "Invalid parameters",
            404: "Legend does not exists",
        },
    )
    def get(
        self,
        run: str,
        res: str,
        field: str,
        area: str,
        platform: str,
        level_pe: Optional[str] = None,
        level_pr: Optional[str] = None,
        weekday: Optional[str] = None,
        env: str = "PROD",
    ) -> Response:
        """Get a forecast legend for a specific run."""
        # NOTE: 'area' param is not strictly necessary here
        # although present among the parameters of the request
        log.debug("Retrieve legend for run <{}, {}, {}>", run, res, field)

        base_path = get_base_path(field, platform, env, run, res, weekday)

        # Get legend image
        legend_path = base_path.joinpath("legends")
        if field == "percentile":
            map_legend_file = "perc6.png"
        elif field == "probability":
            map_legend_file = "prob6.png"
        else:
            map_legend_file = field + ".png"

        map_legend_path = legend_path.joinpath(map_legend_file)
        log.debug(map_legend_path)

        if not map_legend_path.is_file():
            raise NotFound(f"Map legend not found for field <{field}>")

        return Downloader.send_file_content(
            map_legend_file, subfolder=legend_path, mime="image/png"
        )


class MapSensitiveData(EndpointResource):
    labels = ["maps"]

    @decorators.use_kwargs(get_schema(True), location="query")
    @decorators.endpoint(
        path="/maps/sensitive",
        summary="Get asensitive data.",
        responses={
            200: "Data successfully retrieved",
            400: "Invalid request",
            404: "Data not found",
        },
    )
    @check_ip_access(ALLOWED_IPS)
    def get(
        self,
    ) -> Response:
        pass
