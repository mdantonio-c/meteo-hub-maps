import json
import re
from datetime import datetime
from pathlib import Path

from restapi import decorators
from restapi.env import Env
from restapi.exceptions import NotFound
from restapi.rest.definition import EndpointResource, Response
from restapi.utilities.logs import log

FORCINGS = ["BOLAM", "ECMWF", "ICON"]


def get_data_path() -> Path:
    """Get SHYFEM data path, reading from environment variable dynamically."""
    return Path(Env.get("MER_DATA_PATH", "/shyfem"))


class ShyfemStatusEndpoint(EndpointResource):
    """Get metadata about the latest ingested SHYFEM data for each forcing provider."""

    labels = ["marine"]

    @decorators.endpoint(
        path="/marine/shyfem/status",
        summary="Get metadata about the last ingested SHYFEM data",
        description="Return status info for the latest SHYFEM runs with available forcings",
        responses={
            200: "SHYFEM status successfully retrieved",
            404: "SHYFEM data does not exist",
        },
    )
    def get(self) -> Response:
        """Get latest SHYFEM run information."""
        data_path = get_data_path()
        if not data_path.exists():
            raise NotFound(f"SHYFEM path {data_path} does not exist")

        forcing_latest_files = {}
        latest_ready_mtime = None

        for forcing_name in FORCINGS:
            forcing_path = Path(data_path, forcing_name)
            if not forcing_path.exists():
                continue

            # Find forcing-level READY files: YYYYMMDD.GEOSERVER.READY
            ready_files = [
                f
                for f in forcing_path.iterdir()
                if f.is_file() and re.match(r"^\d{8}\.GEOSERVER\.READY$", f.name)
            ]

            if ready_files:
                # Get the latest READY file for this forcing by run date.
                latest = max(ready_files, key=lambda f: f.name)
                latest_forcing_mtime = max(f.stat().st_mtime for f in ready_files)
                if latest_ready_mtime is None or latest_forcing_mtime > latest_ready_mtime:
                    latest_ready_mtime = latest_forcing_mtime
                try:
                    date_str = latest.name.split(".GEOSERVER.READY")[0]
                    if len(date_str) == 8:  # YYYYMMDD
                        forcing_latest_files[forcing_name] = date_str
                except Exception as e:
                    log.warning(f"Failed to parse {latest.name}: {e}")

        if not forcing_latest_files:
            raise NotFound("No SHYFEM data available")

        # Among the latest dates from each forcing, get the one nearest to now
        latest_date_str = max(forcing_latest_files.values())

        available_forcings = sorted(
            [
                name
                for name, date in forcing_latest_files.items()
                if date == latest_date_str
            ]
        )

        forcings = [
            {
                "name": forcing_name,
                "latestRun": run_date,
                "isLatestRun": run_date == latest_date_str,
            }
            for forcing_name, run_date in sorted(forcing_latest_files.items())
        ]

        last_update = (
            datetime.fromtimestamp(latest_ready_mtime).isoformat()
            if latest_ready_mtime is not None
            else datetime.now().isoformat()
        )

        response = {
            "latestRun": latest_date_str,
            "availableForcings": available_forcings,
            "forcings": forcings,
            "meta": {
                "lastUpdate": last_update,
            },
        }

        return self.response(response)


class ShyfemStationsEndpoint(EndpointResource):
    """List available SHYFEM station JSON files."""

    labels = ["marine"]

    @decorators.endpoint(
        path="/marine/shyfem/data/stations",
        summary="List available SHYFEM station JSON files",
        description="Return list of all available station data organized by forcing",
        responses={
            200: "List of files successfully retrieved",
            404: "Stations data not found",
        },
    )
    def get(self) -> Response:
        """List all station JSON files by forcing provider."""
        data_path = get_data_path()
        if not data_path.exists():
            raise NotFound(f"SHYFEM path {data_path} does not exist")

        files_by_forcing = {}
        for forcing_name in FORCINGS:
            json_folder_path = Path(data_path, forcing_name, "json")
            if not json_folder_path.exists():
                continue

            # Look for <MODEL>>_YYYYMMDD_assim_station_timeseries.json files
            station_files = sorted(
                [
                    f.name
                    for f in json_folder_path.iterdir()
                    if f.is_file() and f.name.endswith("_station_timeseries.json")
                ],
                reverse=True,
            )  # Sort in reverse to get latest first

            if station_files:
                files_by_forcing[forcing_name] = station_files

        if not files_by_forcing:
            raise NotFound("No station data files found")

        return self.response(files_by_forcing)


class ShyfemStationFileEndpoint(EndpointResource):
    """Get a specific SHYFEM station JSON file for a given forcing provider."""

    labels = ["marine"]

    @decorators.endpoint(
        path="/marine/shyfem/data/stations/<forcing>/<filename>",
        summary="Get SHYFEM station data for a specific forcing",
        description="Return station timeseries data for the specified forcing provider",
        responses={
            200: "File content",
            404: "File or forcing not found",
        },
    )
    def get(self, forcing: str, filename: str) -> Response:
        """Get specific station JSON file for a forcing provider."""
        # Normalize forcing name to match directory structure
        forcing_upper = forcing.upper()
        if forcing_upper not in FORCINGS:
            raise NotFound(
                f"Unknown forcing: {forcing}. Available: {', '.join(FORCINGS)}"
            )

        data_path = get_data_path()
        base_path = Path(data_path, forcing_upper, "json")
        file_path = Path(base_path, filename)

        if not file_path.exists():
            raise NotFound(f"File {filename} not found for forcing {forcing}")

        try:
            with open(file_path) as f:
                content = json.load(f)
            return self.response(content)
        except Exception as e:
            log.error(f"Error reading SHYFEM station file {forcing}/{filename}: {e}")
            raise NotFound(f"Error reading file {filename}")
