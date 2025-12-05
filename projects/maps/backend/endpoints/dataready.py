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
        path="/data/ready/<date>/<run>/<model>",
        summary="Notify that a dataset is ready",
        responses={202: "Notification received"},

    )
    @check_ip_access(ALLOWED_IPS)
    def post(
        self, run, date, model, **kwargs
    ) -> Response:
        return self.response("Not implemented", 501)
        # base_directory = "/path/to/directory/Italia"
        # sld_directory = "/path/to/sld/dir/mount"  # TODO: get from env
        GEOSERVER_URL = "http://geoserver.dockerized.io:8080/geoserver" # TODO: get from env
        USERNAME = Env.get("GEOSERVER_ADMIN_USER", None)
        PASSWORD = Env.get("GEOSERVER_ADMIN_PASSWORD", None)
        dataset = "icon"
        area = "Italia"

        available_runs = ["00", "12"]
        
        if USERNAME is None or PASSWORD is None:
            raise ServiceUnavailable("Geoserver credentials not set")
        if run not in available_runs:
            raise NotFound("Run hour not in admitted values ('00', '12')")
        c = celery.get_instance()
        base_path = get_base_path("windy", DEFAULT_PLATFORM, "PROD", run, dataset)
        log.info(base_path)
        x = get_ready_file(base_path, area)
        if x is not None:
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
        else:
            raise NotFound("Dataset not ready yet")
        
class StartMonitoring(EndpointResource):
    labels = ["maps"]
    # @decorators.cache(timeout=900)
    @decorators.endpoint(
        path="/data/monitoring",
        summary="Start monitoring a dataset",
        responses={202: "Monitoring started"},
    )
    # @check_ip_access(ALLOWED_IPS)
    def post(self):
        c = celery.get_instance()
        # Create a periodic task to check for the latest data and trigger Geoserver import
        task = c.create_crontab_task(
            name="check_latest_data_and_trigger_geoserver_import_windy",
            hour="*",
            minute="*",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
            task="check_latest_data_and_trigger_geoserver_import_windy",
            args=[],
        )            
        task = c.create_crontab_task(
            name="check_latest_data_and_trigger_geoserver_import_seasonal",
            hour="*",
            minute="*",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
            task="check_latest_data_and_trigger_geoserver_import_seasonal",
            args=[]
            )
        task = c.create_crontab_task(
            name="check_latest_data_and_trigger_geoserver_import_radar",
            hour="*",
            minute="*",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
            task="check_latest_data_and_trigger_geoserver_import_radar",
            args=[]
            )
        task = c.create_crontab_task(
            name="check_latest_data_and_trigger_geoserver_import_sub_seasonal",
            hour="*",
            minute="*",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
            task="check_latest_data_and_trigger_geoserver_import_sub_seasonal",
            args=[],
        )
        task = c.create_crontab_task(
            name="check_latest_data_and_trigger_geoserver_import_ww3",
            hour="*",
            minute="*",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
            task="check_latest_data_and_trigger_geoserver_import_ww3",
            args=[],
        )
        return self.response("Monitoring started", code=202)
    
    @decorators.endpoint(
        path="/data/monitoring",
        summary="Delete monitoring",
        responses={202: "Monitoring ended"},
    )
    # @check_ip_access(ALLOWED_IPS)
    def delete(self):
        c = celery.get_instance()
        res = None
        if c.get_periodic_task("check_latest_data_and_trigger_geoserver_import_windy"):
            res = c.delete_periodic_task("check_latest_data_and_trigger_geoserver_import_windy")
        if c.get_periodic_task("check_latest_data_and_trigger_geoserver_import_seasonal"):
            res = c.delete_periodic_task("check_latest_data_and_trigger_geoserver_import_seasonal")
            log.info(f"Deleted periodic task: {res}")
        if c.get_periodic_task("check_latest_data_and_trigger_geoserver_import_radar"):
            res = c.delete_periodic_task("check_latest_data_and_trigger_geoserver_import_radar")
            log.info(f"Deleted periodic task: {res}")
        if c.get_periodic_task("check_latest_data_and_trigger_geoserver_import_sub_seasonal"):
            res = c.delete_periodic_task("check_latest_data_and_trigger_geoserver_import_sub_seasonal")
            log.info(f"Deleted periodic task: {res}")
        if c.get_periodic_task("check_latest_data_and_trigger_geoserver_import_ww3"):
            res = c.delete_periodic_task("check_latest_data_and_trigger_geoserver_import_ww3")
            log.info(f"Deleted periodic task: {res}")
        if res:
            return self.response("Monitoring has been disabled", code=202)
        # Create a periodic task to check for the latest data and trigger Geoserver import
        return self.response("Monitoring is not active", code=202)