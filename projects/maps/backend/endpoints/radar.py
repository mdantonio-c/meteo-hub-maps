from datetime import datetime
from math import ceil
from pathlib import Path
from typing import Optional

from restapi import decorators
from restapi.env import Env
from restapi.exceptions import NotFound
from restapi.models import fields, validate
from restapi.rest.definition import EndpointResource, Response
from restapi.utilities.logs import log
import math

DATA_PATH = Path(Env.get("RADAR_DATA_PATH", "/radar"))


def parse_celery_checked_file(celery_file: Path) -> Optional[dict]:
    """
    Parse a CELERY.CHECKED file and extract metadata.
    Returns a dictionary with pending import information or None if parsing fails.
    """
    try:
        celery_filename = celery_file.name
        if "-" not in celery_filename:
            return None
            
        time_range_part = celery_filename.split(".CELERY.CHECKED")[0]
        parts = time_range_part.split("-")
        
        if len(parts) != 2:
            return None
            
        from_date_str = parts[0]  # YYYYMMDDHHMM
        to_date_str = parts[1]    # YYYYMMDDHHMM
        
        # Parse dates
        from_date = datetime.strptime(from_date_str, "%Y%m%d%H%M")
        to_date = datetime.strptime(to_date_str, "%Y%m%d%H%M")
        
        detected_timestamp = celery_file.stat().st_mtime
        
        return {
            "status": "pending",
            "file": celery_filename,
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
            "detectedAt": datetime.fromtimestamp(detected_timestamp).isoformat(),
            "_detected_timestamp": detected_timestamp
        }
    except Exception as e:
        log.warning(f"Error processing CELERY.CHECKED file: {e}")
        return None


def calculate_estimated_finish(from_time: str, to_time: str, detected_timestamp: float) -> Optional[str]:
    """
    Calculate estimated finish time in seconds based on time range.
    Uses logarithmic scaling: 6 seconds at 1 interval, 14 seconds at 2000 intervals.
    """
    try:
        time_from = datetime.fromisoformat(from_time)
        time_to = datetime.fromisoformat(to_time)
        
        time_diff = (time_to - time_from).total_seconds()
        num_intervals = time_diff / 300  # 300 seconds = 5 minutes
        
        # Logarithmic scaling
        if num_intervals <= 1:
            estimated_processing_time = 6.0
        else:
            estimated_processing_time = 6.0 + (14.0 - 6.0) * (math.log(num_intervals) / math.log(2000))
        
        elapsed_time = datetime.now().timestamp() - detected_timestamp
        remaining_time = max(1, int(ceil(estimated_processing_time)) - int(elapsed_time))
        
        return str(remaining_time)
    except Exception as e:
        log.warning(f"Error calculating estimated finish: {e}")
        return None


class RadarStatusEndpoint(EndpointResource):
    labels = ["radar"]

    @decorators.endpoint(
        path="/radar/<radar_type>/status",
        summary="Get metadata about the last ingested radar data chunk",
        responses={
            200: "Radar status successfully retrieved",
            400: "Invalid parameters",
            404: "Radar data does not exist",
        },
    )
    def get(self, radar_type: str) -> Response:
        """
        Get status information about the last ingested radar data chunk.
        Returns the time range, interval, and last update timestamp.
        """
        # Validate radar_type
        if radar_type not in ["sri", "srt"]:
            raise NotFound(f"Invalid radar type: {radar_type}. Must be 'sri' or 'srt'")
        
        radar_path = DATA_PATH.joinpath(radar_type)
        
        if not radar_path.exists():
            raise NotFound(f"Radar path {radar_path} does not exist")

        # Look for GEOSERVER.READY files
        ready_files = [
            f for f in radar_path.iterdir() 
            if f.is_file() and ".GEOSERVER.READY" in f.name
        ]

        # Check for CELERY.CHECKED files (pending import)
        celery_files = [
            f for f in radar_path.iterdir() 
            if f.is_file() and ".CELERY.CHECKED" in f.name
        ]
        
        pending_import = None
        latest_celery_file = None
        if celery_files:
            celery_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            latest_celery_file = celery_files[0]
            pending_import = parse_celery_checked_file(latest_celery_file)

        # If no GEOSERVER.READY file exists but we have CELERY.CHECKED, return pending status
        if not ready_files:
            if pending_import:
                detected_timestamp = pending_import.pop("_detected_timestamp")
                estimated_finish = calculate_estimated_finish(
                    pending_import["from"],
                    pending_import["to"],
                    detected_timestamp
                )
                if estimated_finish:
                    pending_import["estimatedFinishSeconds"] = estimated_finish
            
            response = {
                "from": None,
                "to": None,
                "interval": "5m",
                "meta": {
                    "lastUpdate": None,
                    "pendingImport": pending_import
                }
            }
            return self.response(response)

        # Get the most recent GEOSERVER.READY file
        try:
            ready_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            latest_ready_file = ready_files[0]
        except Exception as e:
            log.error(f"Error sorting ready files: {e}")
            raise NotFound("Unable to determine latest radar data")

        # Parse the GEOSERVER.READY file content
        try:
            content = latest_ready_file.read_text()
            lines = content.strip().split("\n")
            
            processed_at = None
            time_range = None
            
            for line in lines:
                if line.startswith("Processed by GeoServer at"):
                    processed_at = line.split("at ")[1].strip()
                elif line.startswith("Time range:"):
                    time_range = line.split("Time range: ")[1].strip()
            
            if not time_range:
                raise NotFound("Time range not found in GEOSERVER.READY file")
            
            # Parse time range: "2025-11-22T11:35:00 to 2025-11-25T11:35:00"
            time_parts = time_range.split(" to ")
            from_time = time_parts[0]
            to_time = time_parts[1]
            
            # Determine interval based on radar type (5 minutes for both)
            interval = "5m"
            
            response = {
                "from": f"{from_time}Z",
                "to": f"{to_time}Z",
                "interval": interval,
                "meta": {
                    "lastUpdate": f"{processed_at}Z" if processed_at else None
                }
            }
            
            # Add pending import information if CELERY.CHECKED file exists
            if pending_import:
                detected_timestamp = pending_import.pop("_detected_timestamp")
                # Use general "to" time as baseline, fallback to pending "from" if not available
                baseline_time = to_time if to_time else pending_import["from"]
                estimated_finish = calculate_estimated_finish(
                    baseline_time,
                    pending_import["to"],
                    detected_timestamp
                )
                if estimated_finish:
                    pending_import["estimatedFinishSeconds"] = estimated_finish
                
            response["meta"]["pendingImport"] = pending_import
            return self.response(response)
            
        except Exception as e:
            log.error(f"Error parsing GEOSERVER.READY file: {e}")
            raise NotFound(f"Unable to parse radar data metadata: {e}")
