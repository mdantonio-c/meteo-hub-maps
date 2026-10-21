import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from restapi import decorators
from restapi.env import Env
from restapi.rest.definition import EndpointResource, Response
from restapi.utilities.logs import log

STATUS_FILE_PATH = Env.get("STATUS_FILE_PATH", "/var/lib/meteohub/status.json")


class MaintenanceStatusSchema:
    """Schema for maintenance status response."""

    def __init__(
        self,
        status: str = "operational",
        message: Optional[str] = None,
        scheduled_start: Optional[str] = None,
        scheduled_end: Optional[str] = None,
        affected_services: Optional[list] = None,
        updated_at: Optional[str] = None,
    ):
        self.status = status
        self.message = message
        self.scheduled_start = scheduled_start
        self.scheduled_end = scheduled_end
        self.affected_services = affected_services or []
        self.updated_at = updated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "message": self.message,
            "scheduled_start": self.scheduled_start,
            "scheduled_end": self.scheduled_end,
            "affected_services": self.affected_services,
            "updated_at": self.updated_at,
        }


class SystemStatusEndpoint(EndpointResource):
    """Get and update system status and maintenance information."""

    labels = ["status"]

    @decorators.endpoint(
        path="/service/status",
        summary="Get system status and maintenance information",
        description="Returns current system status including any scheduled maintenance, ongoing issues, or operational state. This endpoint can be used by clients to check if the system is available or if maintenance is planned.",
        responses={
            200: "System status successfully retrieved",
            500: "Unable to retrieve system status",
        },
    )
    def get(self) -> Response:
        """Get current system status."""
        try:
            status_data = self._read_status_file()
            return self.response(status_data)
        except Exception as e:
            log.error(f"Error reading status file: {e}")
            if os.path.exists(STATUS_FILE_PATH):
                return self.response(
                    {
                        "status": "unknown",
                        "message": "Unable to read status file",
                        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    }
                )
            status_data = MaintenanceStatusSchema(status="operational").to_dict()
            self._write_status_file(status_data)
            return self.response(status_data)

    # @decorators.endpoint(
    #     path="/service/status",
    #     summary="Update system status and maintenance information",
    #     description="Updates the system status to signal maintenance windows, outages, or operational state changes.",
    #     responses={
    #         200: "System status successfully updated",
    #         400: "Invalid status data provided",
    #         500: "Unable to update system status",
    #     },
    # )
    # def post(self) -> Response:
    #     """Update system status."""
    #     try:
    #         from flask import request

    #         data = request.get_json()

    #         if not data:
    #             return self.response(
    #                 {"error": "No JSON data provided"}, status_code=400
    #             )

    #         status = data.get("status", "operational")
    #         valid_statuses = ["operational", "maintenance", "degraded", "outage"]
    #         if status not in valid_statuses:
    #             return self.response(
    #                 {
    #                     "error": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
    #                 },
    #                 status_code=400,
    #             )

    #         status_data = MaintenanceStatusSchema(
    #             status=status,
    #             message=data.get("message"),
    #             scheduled_start=data.get("scheduled_start"),
    #             scheduled_end=data.get("scheduled_end"),
    #             affected_services=data.get("affected_services", []),
    #         ).to_dict()

    #         self._write_status_file(status_data)
    #         log.info(f"System status updated: {status}")
    #         return self.response(
    #             {"success": True, "status": status_data}, status_code=200
    #         )

    #     except Exception as e:
    #         log.error(f"Error updating status file: {e}")
    #         return self.response(
    #             {"error": "Unable to update system status", "details": str(e)},
    #             status_code=500,
    #         )

    def _read_status_file(self) -> dict:
        """Read status from file."""
        if not os.path.exists(STATUS_FILE_PATH):
            return MaintenanceStatusSchema(status="operational").to_dict()

        try:
            with open(STATUS_FILE_PATH, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            log.error(f"Error reading status file: {e}")
            return MaintenanceStatusSchema(status="operational").to_dict()

    def _write_status_file(self, data: dict) -> None:
        """Write status to file."""
        status_path = Path(STATUS_FILE_PATH)
        status_path.parent.mkdir(parents=True, exist_ok=True)

        with open(status_path, "w") as f:
            json.dump(data, f, indent=2)

        log.debug(f"Status written to {STATUS_FILE_PATH}")
