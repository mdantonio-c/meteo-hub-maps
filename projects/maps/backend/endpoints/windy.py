from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from maps.endpoints.config import (
    DATASETS,
    DEFAULT_PLATFORM,
    RUNS,
    DatasetType,
    get_multilayer_maps_base_path,
    get_ready_file,
    get_geoserver_ready_file
)
from restapi.env import Env
from restapi import decorators
from restapi.exceptions import NotFound
from restapi.models import fields, validate
from restapi.rest.definition import EndpointResource, Response
from restapi.utilities.logs import log
from maps.utils.downloader import CustomDownloader as Downloader

WRF_AREA = Env.get("WINDY_INGEST_AREA", "Italia")
WINDY_INGEST_BASE_PATH = Path(Env.get("WINDY_INGEST_BASE_PATH", "/windy"))


def _wrf_run_candidates(run: str) -> List[Path]:
    # Support both historical and current folder layouts used across environments.
    return [
        get_multilayer_maps_base_path("windy", "", "", run, "WRF").joinpath(WRF_AREA),
        get_multilayer_maps_base_path("windy", DEFAULT_PLATFORM, "PROD", run, "WRF").joinpath(WRF_AREA),
        WINDY_INGEST_BASE_PATH.joinpath(f"Windy-{run}-WRF.web", WRF_AREA),
    ]


def _resolve_wrf_run_path(run: str) -> Optional[Path]:
    for candidate in _wrf_run_candidates(run):
        if candidate.exists():
            return candidate
    return None


def _parse_wrf_latest_reftime() -> Optional[str]:
    latest_marker: Optional[Path] = None
    resolved_paths = 0

    for run in RUNS:
        run_path = _resolve_wrf_run_path(run)
        if run_path is None:
            continue
        resolved_paths += 1

        geoserver_files = sorted(
            [f for f in run_path.iterdir() if f.is_file() and f.name.endswith(".GEOSERVER.READY")],
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        celery_files = sorted(
            [f for f in run_path.iterdir() if f.is_file() and f.name.endswith(".CELERY.CHECKED")],
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )

        marker_file: Optional[Path] = None
        if geoserver_files:
            marker_file = geoserver_files[0]
        elif celery_files:
            marker_file = celery_files[0]

        if marker_file is None:
            continue

        if latest_marker is None or marker_file.stat().st_mtime > latest_marker.stat().st_mtime:
            latest_marker = marker_file

    if resolved_paths == 0:
        raise NotFound("WRF data paths not found")

    reftime = None
    if latest_marker is not None:
        reftime_str = latest_marker.name.split(".")[0]
        try:
            reftime = datetime.strptime(reftime_str, "%Y%m%d%H").strftime("%Y%m%d%H")
        except ValueError:
            reftime = None

    return reftime

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
                base_path = get_multilayer_maps_base_path("windy", '', '', r, dataset)
                log.info(base_path)
                # x = get_ready_file(base_path, area)
                x = get_geoserver_ready_file(base_path, area)
                # add walrus here
                if x:
                    ready_files.append(x)
                    latest_x = x
            try:
                ready_files.sort(key=lambda f: f.name[:10], reverse=True)
                ready_file = ready_files[0].name
                latest_x = ready_files[0]
                
            except ValueError:
                log.warning("No Run is available: .READY file not found")
        else:
            base_path = get_multilayer_maps_base_path("windy", DEFAULT_PLATFORM, "PROD", run, dataset)
            # tmp_ready_file = get_ready_file(base_path, area)
            tmp_ready_file = get_geoserver_ready_file(base_path, area)
            if tmp_ready_file:
                ready_file = tmp_ready_file.name

        if not ready_file:
            raise NotFound("No .READY file found")
        log.info(f"Ready file: {ready_file}")
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

class MapStaticWindyList(EndpointResource):
    labels = ["maps"]

    @decorators.endpoint(
        path="/maps/wind-direction/list/files",
        summary="List available static wind direction tiff files for the latest run.",
        responses={200: "List of files successfully retrieved"},
    )
    def get(self) -> Response:
        """
        List available static wind direction tiff files.
        It searches for the latest available run by checking both '00' and '12' runs
        and identifies the most recent one using the .READY files.
        """
        
        ready_files = []
        for r in ["00", "12"]:
            path = get_multilayer_maps_base_path("windy", "", "", r, "icon")
            log.info(path)
            x = get_geoserver_ready_file(path, "Italia")
            if x:
                ready_files.append(x)

        if not ready_files:
            raise NotFound("No .READY file found")
        ready_files.sort(key=lambda f: f.name[:10], reverse=True)
        latest_path = ready_files[0].parent.joinpath("wind-direction")
        files = sorted([f.name for f in latest_path.iterdir() if f.is_file()])
        return self.response(files)


class MapStaticWindyFile(EndpointResource):
    labels = ["maps"]

    @decorators.endpoint(
        path="/maps/wind-direction/files/<filename>",
        summary="Get a specific static wind direction tiff file from the latest run.",
        responses={
            200: "File successfully retrieved",
            404: "File not found",
        },
    )
    def get(self, filename: str) -> Response:
        """
        Get a specific static wind direction tiff file.
        The file is retrieved from the 'wind-direction' subfolder of the latest
        available run.
        """
        ready_files = []
        for r in ["00", "12"]:
            path = get_multilayer_maps_base_path("windy", "", "", r, "icon")
            log.info(path)
            x = get_geoserver_ready_file(path, "Italia")
            if x:
                ready_files.append(x)

        if not ready_files:
            raise NotFound("No .READY file found")
        ready_files.sort(key=lambda f: f.name[:10], reverse=True)
        latest_path = ready_files[0].parent.joinpath("wind-direction")
        filepath = latest_path.joinpath(filename)
        if not filepath.exists() or not filepath.is_file():
            raise NotFound(f"File {filepath} does not exist")
        return Downloader.send_file_content(filepath.name, filepath.parent, 'image/tif')


class WRFIngestionStatusEndpoint(EndpointResource):
    labels = ["windy"]

    @decorators.endpoint(
        path="/WRF/status",
        summary="Get latest WRF metadata in windy response format",
        responses={
            200: "WRF metadata successfully retrieved",
            404: "WRF folders not found",
        },
    )
    def get(self) -> Response:
        reftime = _parse_wrf_latest_reftime()
        if not reftime:
            raise NotFound("No WRF ingestion marker found")

        info: Optional[DatasetType] = DATASETS.get("icon")
        if not info:
            raise NotFound("Dataset icon is not available")

        return self.response(
            {
                "dataset": "wrf",
                "area": WRF_AREA,
                "start_offset": info["start_offset"],
                "end_offset": info["end_offset"],
                "step": info["step"],
                "boundaries": info["boundaries"],
                "reftime": reftime,
                "platform": None,
            }
        )
