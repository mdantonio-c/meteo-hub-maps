import json
from datetime import datetime
from pathlib import Path

from maps.datasets.registry import load_registry
from maps.endpoints.datasets import _dataset_base_path
from restapi import decorators
from restapi.env import Env
from restapi.exceptions import NotFound
from restapi.rest.definition import EndpointResource, Response
from restapi.utilities.logs import log

DATA_PATH = Path(Env.get("SUB_SEASONAL_AIM_PATH", "/sub-seasonal-aim"))
JSONS_PATH = DATA_PATH / "json_weekly"


def _jsons_path() -> Path:
    if Env.get_bool("ACTIVATE_DYNAMIC_DATASETS"):
        config = load_registry().get("sub-seasonal")
        return (_dataset_base_path(config) / "json_weekly").resolve()
    return JSONS_PATH.resolve()


class SubSeasonalEndpoint(EndpointResource):
    labels = ["sub-seasonal"]
    depends_on = ["not ACTIVATE_DYNAMIC_DATASETS"]

    @decorators.endpoint(
        path="/sub-seasonal/status",
        summary="Get metadata about the last ingested sub-seasonal data",
        responses={
            200: "Sub-seasonal status successfully retrieved",
            404: "Sub-seasonal data does not exist",
        },
    )
    def get(self) -> Response:
        if not DATA_PATH.exists():
            raise NotFound(f"Sub-seasonal path {DATA_PATH} does not exist")

        # Look for GEOSERVER.READY files
        ready_files = [
            f for f in DATA_PATH.iterdir() 
            if f.is_file() and ".GEOSERVER.READY" in f.name
        ]
        
        # Look for CELERY.CHECKED files
        celery_files = [
            f for f in DATA_PATH.iterdir() 
            if f.is_file() and ".CELERY.CHECKED" in f.name
        ]
        
        pending_import = None
        if celery_files:
            celery_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            latest_celery = celery_files[0]
            
            # Parse range from filename: YYYYMMDD-YYYYMMDD.CELERY.CHECKED
            try:
                range_part = latest_celery.name.split(".CELERY.CHECKED")[0]
                if "-" in range_part:
                    start_str, end_str = range_part.split("-")
                    pending_import = {
                        "status": "pending",
                        "from": datetime.strptime(start_str, "%Y%m%d").isoformat(),
                        "to": datetime.strptime(end_str, "%Y%m%d").isoformat(),
                        "detectedAt": datetime.fromtimestamp(latest_celery.stat().st_mtime).isoformat()
                    }
            except Exception as e:
                log.warning(f"Failed to parse pending file {latest_celery}: {e}")

        if not ready_files:
            if pending_import:
                return self.response({
                    "from": None,
                    "to": None,
                    "meta": {
                        "lastUpdate": None,
                        "pendingImport": pending_import
                    }
                })
            raise NotFound("No sub-seasonal data available")

        # Get latest ready file
        ready_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        latest_ready = ready_files[0]
        
        try:
            content = latest_ready.read_text()
            lines = content.strip().split("\n")
            processed_at = None
            run_date = None
            range_str = None
            
            for line in lines:
                if line.startswith("Processed by GeoServer at"):
                    processed_at = line.split("at ")[1].strip()
                elif line.startswith("Run:"):
                    run_date = line.split("Run: ")[1].strip()
                elif line.startswith("Range:"):
                    range_str = line.split("Range: ")[1].strip()
            
            if not range_str:
                # Fallback to filename parsing
                range_str = latest_ready.name.split(".GEOSERVER.READY")[0]
            
            start_str, end_str = range_str.split("-")
            
            response = {
                "from": datetime.strptime(start_str, "%Y%m%d").isoformat(),
                "to": datetime.strptime(end_str, "%Y%m%d").isoformat(),
                "run": run_date,
                "meta": {
                    "lastUpdate": processed_at,
                    "pendingImport": pending_import
                }
            }
            
            return self.response(response)
            
        except Exception as e:
            log.error(f"Error parsing GEOSERVER.READY file: {e}")
            raise NotFound(f"Unable to parse sub-seasonal data metadata: {e}")


class SubSeasonalJSONsEndpoint(EndpointResource):
    # These dataset-specific routes have no generated replacement in dynamic mode.
    labels = ["sub-seasonal"]

    @decorators.endpoint(
        path="/sub-seasonal/data/cities",
        summary="List available sub-seasonal weekly json files",
        responses={
            200: "List of files successfully retrieved",
            404: "json_weekly folder not found",
        },
    )
    def get(self) -> Response:
        base_path = _jsons_path()
        if not base_path.is_dir():
            raise NotFound(f"Sub-seasonal jsons path {base_path} does not exist")

        files = []
        for item in base_path.rglob("*"):
            if item.is_file() and item.suffix.lower() == ".json":
                try:
                    item.resolve().relative_to(base_path)
                except ValueError:
                    continue
                files.append(str(item.relative_to(base_path)))
        files.sort()

        return self.response(files)


class SubSeasonalJSONFileEndpoint(EndpointResource):
    labels = ["sub-seasonal"]

    @decorators.endpoint(
        path="/sub-seasonal/data/cities/<path:filename>",
        summary="Get a specific sub-seasonal weekly json file",
        responses={
            200: "File content",
            404: "File not found",
        },
    )
    def get(self, filename: str) -> Response:
        base_path = _jsons_path()
        if Path(filename).is_absolute():
            raise NotFound(f"Invalid file path: {filename}")
        file_path = (base_path / filename).resolve()

        try:
            file_path.relative_to(base_path)
        except ValueError as e:
            raise NotFound(f"Invalid file path: {filename}") from e

        if not file_path.is_file() or file_path.suffix.lower() != ".json":
            raise NotFound(f"File {filename} not found")

        try:
            with file_path.open(encoding="utf-8") as f:
                content = json.load(f)
        except (OSError, ValueError) as e:
            log.error(f"Error reading sub-seasonal json file {filename}: {e}")
            raise NotFound(f"Error reading file {filename}") from e
        return self.response(content)
