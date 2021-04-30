import os
from functools import lru_cache
from typing import Dict, Optional, Type, Union

from flask import send_file
from restapi import decorators
from restapi.exceptions import NotFound, ServiceUnavailable
from restapi.models import Schema, fields, validate
from restapi.rest.definition import EndpointResource, Response
from restapi.utilities.logs import log

MEDIA_ROOT = "/meteo/"

RUNS = ["00", "12"]
RESOLUTIONS = ["lm2.2", "lm5"]
FIELDS = [
    "prec1",
    "prec3",
    "prec6",
    "prec12",
    "prec24",
    "t2m",
    "wind",
    "cloud",
    "pressure",
    "cloud_hml",
    "humidity",
    "snow3",
    "snow6",
    "percentile",
    "probability",
]
LEVELS_PE = ["1", "10", "25", "50", "70", "75", "80", "90", "95", "99"]
LEVELS_PR = ["5", "10", "20", "50"]
AREAS = ["Italia", "Nord_Italia", "Centro_Italia", "Sud_Italia", "Area_Mediterranea"]
PLATFORMS = ["GALILEO", "MEUCCI"]
ENVS = ["PROD", "DEV"]
DEFAULT_PLATFORM = os.environ.get("PLATFORM", "GALILEO")


def check_platform_availability(platform: str) -> bool:
    return os.access(os.path.join(MEDIA_ROOT, platform), os.X_OK)


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

    return Schema.from_dict(attributes, name="MapsSchema")


class MapEndpoint(EndpointResource):
    @staticmethod
    @lru_cache
    def get_base_path(field: str, platform: str, env: str, run: str, res: str) -> str:
        # flood fields have a different path
        if field == "percentile" or field == "probability":
            folder = f"PROB-{run}-iff.web"
        else:
            folder = f"Magics-{run}-{res}.web"

        base_path = os.path.join(
            MEDIA_ROOT,
            platform,
            env,
            folder,
        )
        log.debug(f"base_path: {base_path}")
        return base_path

    @staticmethod
    def get_ready_file(base_path: str, area: str) -> str:
        ready_path = os.path.join(base_path, area)
        log.debug(f"ready_path: {ready_path}")

        ready_files = []
        if os.path.exists(ready_path):
            ready_files = [
                f
                for f in os.listdir(ready_path)
                if os.path.isfile(os.path.join(ready_path, f)) and ".READY" in f
            ]

        # Check if .READY file exists (if not, images are not ready yet)
        log.debug(f"Looking for .READY files in: {ready_path}")
        if not ready_files:
            raise NotFound("no .READY files found")

        log.debug(f".READY files found: {ready_files}")
        return ready_files[0]


class MapImage(MapEndpoint):
    labels = ["map image"]

    @decorators.use_kwargs(get_schema(True), location="query")
    @decorators.endpoint(
        path="/maps/offset/<map_offset>",
        summary="Get a forecast map for a specific run.",
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
        env: str = "PROD",
    ) -> Response:
        """Get a forecast map for a specific run."""

        # flash flood offset is a bit more complicate
        if field == "percentile":
            map_offset = f"{map_offset}_{level_pe}"
        elif field == "probability":
            map_offset = f"{map_offset}_{level_pr}"

        log.debug(f"Retrieve map image by offset <{map_offset}>")

        base_path = self.get_base_path(field, platform, env, run, res)

        # Check if the images are ready: 2017112900.READY
        ready_file = self.get_ready_file(base_path, area)
        reftime = ready_file[:10]

        # get map image
        if field == "percentile":
            png_name = f"perc6.{reftime}.{map_offset}.png"
        elif field == "probability":
            png_name = f"prob6.{reftime}.{map_offset}.png"
        else:
            png_name = f"{field}.{reftime}.{map_offset}.png"

        map_image_file = os.path.join(base_path, area, field, png_name)

        log.debug(f"map_image_file: {map_image_file}")

        if not os.path.isfile(map_image_file):
            raise NotFound(f"Map image not found for offset {map_offset}")

        return send_file(map_image_file, mimetype="image/png")


class MapSet(MapEndpoint):
    labels = ["map set"]

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
    def get(
        self,
        run: str,
        res: str,
        field: str,
        area: str,
        platform: Optional[str] = None,
        level_pe: Optional[str] = None,
        level_pr: Optional[str] = None,
        env: str = "PROD",
    ) -> Response:
        """
        Get the last available map set for a specific run
        and return the reference time as well
        """

        log.debug(f"Retrieve map set for last run <{run}>")

        # only admin user can request for a specific platform
        if platform is not None and not self.verify_admin():
            platform = None

        if field == "percentile" or field == "probability":
            # force GALILEO as platform
            platform = "GALILEO"
            log.warning("Forcing platform to {} because field is {}", platform, field)

        # if PLATFORM is not provided, set as default the first available
        # in the order: DEFAULT_PLATFORM + others
        if not platform:
            log.debug(f"PLATFORMS: {PLATFORMS}")
            log.debug(f"DEFAULT PLATFORM: {DEFAULT_PLATFORM}")
            platforms_to_be_check = [DEFAULT_PLATFORM] + list(
                set(PLATFORMS) - {DEFAULT_PLATFORM}
            )
        else:
            platforms_to_be_check = [platform]

        for platform in platforms_to_be_check:
            if not check_platform_availability(platform):
                log.warning(f"platform {platform} not available")
                continue
            log.debug("Found available platform: {}", platform)
            break
        else:
            raise ServiceUnavailable("Map service is currently unavailable")

        base_path = self.get_base_path(field, platform, env, run, res)

        # Check if the images are ready: 2017112900.READY
        ready_file = self.get_ready_file(base_path, area)
        reftime = ready_file[:10]

        # load image offsets
        images_path = os.path.join(base_path, area, field)

        list_file = sorted(os.listdir(images_path))

        if field == "percentile" or field == "probability":
            offsets = []
            # flash flood offset is a bit more complicate
            for f in list_file:
                if os.path.isfile(os.path.join(images_path, f)):
                    offset = f.split(".")[-2]
                    # offset is like this now: 0006_10
                    offset, level = offset.split("_")
                    if field == "percentile" and level_pe == level:
                        offsets.append(offset)
                    elif field == "probability" and level_pr == level:
                        offsets.append(offset)
        else:
            offsets = [
                f.split(".")[-2]
                for f in list_file
                if os.path.isfile(os.path.join(images_path, f))
            ]

        log.debug("data offsets: {}", offsets)

        data = {"reftime": reftime, "offsets": offsets, "platform": platform}
        return self.response(data)


class MapLegend(MapEndpoint):
    labels = ["legend"]

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
        env: str = "PROD",
    ) -> Response:
        """Get a forecast legend for a specific run."""
        # NOTE: 'area' param is not strictly necessary here
        # although present among the parameters of the request
        log.debug("Retrieve legend for run <{}, {}, {}>", run, res, field)

        base_path = self.get_base_path(field, platform, env, run, res)

        # Get legend image
        legend_path = os.path.join(base_path, "legends")
        if field == "percentile":
            map_legend_file = os.path.join(legend_path, "perc6.png")
        elif field == "probability":
            map_legend_file = os.path.join(legend_path, "prob6.png")
        else:
            map_legend_file = os.path.join(legend_path, field + ".png")
        log.debug(map_legend_file)

        if not os.path.isfile(map_legend_file):
            raise NotFound(f"Map legend not found for field <{field}>")

        return send_file(map_legend_file, mimetype="image/png")
