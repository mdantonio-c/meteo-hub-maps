from datetime import datetime
from typing import Dict, Optional, Type, Union

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
from restapi import decorators
from restapi.exceptions import NotFound, ServiceUnavailable
from restapi.models import Schema, fields, validate
from restapi.rest.definition import EndpointResource, Response
from restapi.services.download import Downloader
from restapi.utilities.logs import log
from restapi.connectors import celery
from restapi.env import Env
from maps.utils.env import Env as utils_env
from maps.auth.authz import check_ip_access

ALLOWED_IPS = utils_env.get_set("ALLOWED_IPS", frozenset())

class DataReady(EndpointResource):
    labels = ["maps"]

    # @decorators.cache(timeout=900)
    @decorators.endpoint(
        path="/data/ready/<date>/<run>",
        summary="Notify that a dataset is ready",
        responses={202: "Notification received"},

    )
    @check_ip_access(ALLOWED_IPS)
    def post(
        self, run, date, **kwargs
    ) -> Response:
        # base_directory = "/path/to/directory/Italia"
        # sld_directory = "/path/to/sld/dir/mount"  # TODO: get from env
        GEOSERVER_URL = "http://geoserver.dockerized.io:8080/geoserver" # TODO: get from env
        USERNAME = Env.get("GEOSERVER_ADMIN_USER", None)
        PASSWORD = Env.get("GEOSERVER_ADMIN_PASSWORD", None)

        available_runs = ["00", "12"]
        
        if USERNAME is None or PASSWORD is None:
            raise ServiceUnavailable("Geoserver credentials not set")
        if run not in available_runs:
            raise NotFound("Run hour not in admitted values ('00', '12')")
        c = celery.get_instance()
        c.celery_app.send_task(
                    "update_geoserver_layers",
                    args=(
                        # base_directory,
                        # sld_directory,
                        GEOSERVER_URL,
                        USERNAME,
                        PASSWORD,
                        run,
                        date
                    ),
                )
        return self.response("Notification received", code=202)