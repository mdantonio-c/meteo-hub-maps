import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

import pytest
from faker import Faker
from restapi.env import Env
from restapi.tests import API_URI, BaseTests, FlaskClient
from restapi.utilities.logs import log


# Helper functions for test setup
def create_shyfem_directories() -> Path:
    """Create base SHYFEM directory structure."""
    shyfem_path = Path(Env.get("MER_DATA_PATH", "/shyfem"))
    shyfem_path.mkdir(parents=True, exist_ok=True)
    return shyfem_path


def create_ready_files(forcing: str, dates: list) -> None:
    """Create READY files for a specific forcing.

    Args:
        forcing: Forcing name (BOLAM, ECMWF, ICON)
        dates: List of date strings in YYYYMMDD format
    """
    shyfem_path = Path(Env.get("MER_DATA_PATH", "/shyfem"))
    forcing_path = shyfem_path.joinpath(forcing)
    forcing_path.mkdir(parents=True, exist_ok=True)

    # Assign mtimes based on date order so later dates have more recent mtimes
    base_time = time.time()

    for i, date_str in enumerate(dates):
        ready_file = forcing_path.joinpath(f"{date_str}.GEOSERVER.READY")
        ready_file.touch()
        # Set mtime: later dates get more recent times
        file_mtime = base_time + i
        os.utime(ready_file, (file_mtime, file_mtime))


def create_station_file(forcing: str, filename: str, data: dict) -> None:
    """Create a station JSON file for a specific forcing.

    Args:
        forcing: Forcing name (BOLAM, ECMWF, ICON)
        filename: Station file name (e.g., "20260701_station_timeseries.json")
        data: Dictionary to serialize as JSON
    """
    shyfem_path = Path(Env.get("MER_DATA_PATH", "/shyfem"))
    forcing_path = shyfem_path.joinpath(forcing)
    forcing_path.mkdir(parents=True, exist_ok=True)
    json_path = forcing_path.joinpath("json")
    json_path.mkdir(parents=True, exist_ok=True)

    station_file = json_path.joinpath(filename)
    station_file.write_text(json.dumps(data))


def cleanup_shyfem_data() -> None:
    """Remove all SHYFEM test data."""
    shyfem_path = Path(Env.get("MER_DATA_PATH", "/shyfem"))
    if shyfem_path.exists():
        shutil.rmtree(shyfem_path)


@pytest.fixture(autouse=True)
def setup_shyfem_env(monkeypatch):
    """Set up SHYFEM environment variables for tests."""
    # Use a temporary test path that the test has permission to delete
    test_data_path = "/tmp/shyfem_test"
    monkeypatch.setenv("MER_DATA_PATH", test_data_path)

    # Cleanup before test
    cleanup_shyfem_data()

    yield

    # Cleanup after test
    cleanup_shyfem_data()


class TestMarineShyfem(BaseTests):
    """Tests for SHYFEM marine endpoints."""

    def test_shyfem_status_no_data(self, client: FlaskClient) -> None:
        """Test status endpoint when SHYFEM data does not exist."""
        endpoint = API_URI + "/marine/shyfem/status"
        r = client.get(endpoint)
        assert r.status_code == 404
        content = self.get_content(r)
        assert isinstance(content, str) and (
            "does not exist" in content or "No SHYFEM data available" in content
        )

    def test_shyfem_status_success(self, client: FlaskClient, faker: Faker) -> None:
        """Test status endpoint with valid SHYFEM data."""
        forcings = ["BOLAM", "ECMWF", "ICON"]
        dates = ["20260629", "20260630", "20260701"]

        # Create READY files for each forcing
        for forcing in forcings:
            create_ready_files(forcing, dates)

        # Test status endpoint
        endpoint = API_URI + "/marine/shyfem/status"
        r = client.get(endpoint)
        assert r.status_code == 200

        response = self.get_content(r)
        assert isinstance(response, dict)
        assert "latestRun" in response
        assert "availableForcings" in response
        assert "allForcings" in response
        assert "meta" in response

        # Latest run should be the lexicographically maximum date
        assert response["latestRun"] == "20260701"

        # Only forcings with the latest date should be in availableForcings
        assert sorted(response["availableForcings"]) == sorted(forcings)

        # allForcings should have all forcings with their dates
        assert len(response["allForcings"]) == 3
        for forcing, date in response["allForcings"].items():
            assert forcing in forcings
            assert len(date) == 8  # YYYYMMDD format

    def test_shyfem_status_mixed_dates(self, client: FlaskClient, faker: Faker) -> None:
        """Test status endpoint when forcings have different latest dates."""
        # BOLAM and ICON have 20260701, ECMWF has 20260630
        forcings_data = {
            "BOLAM": ["20260630", "20260701"],
            "ECMWF": ["20260628", "20260629", "20260630"],
            "ICON": ["20260629", "20260701"],
        }

        for forcing, dates in forcings_data.items():
            create_ready_files(forcing, dates)

        endpoint = API_URI + "/marine/shyfem/status"
        r = client.get(endpoint)
        assert r.status_code == 200

        response = self.get_content(r)

        # Latest run is 20260701 (max of all latest dates per forcing)
        assert response["latestRun"] == "20260701"

        # Only BOLAM and ICON have 20260701
        assert sorted(response["availableForcings"]) == ["BOLAM", "ICON"]

        # All forcings should be in allForcings with their latest dates
        assert response["allForcings"]["BOLAM"] == "20260701"
        assert response["allForcings"]["ECMWF"] == "20260630"
        assert response["allForcings"]["ICON"] == "20260701"

    def test_shyfem_status_no_ready_files(
        self, client: FlaskClient, faker: Faker
    ) -> None:
        """Test status endpoint when directories exist but have no READY files."""
        # Create empty directories without READY files
        for forcing in ["BOLAM", "ECMWF", "ICON"]:
            create_shyfem_directories()
            forcing_path = Path(Env.get("MER_DATA_PATH", "/shyfem")).joinpath(forcing)
            forcing_path.mkdir(parents=True, exist_ok=True)

        endpoint = API_URI + "/marine/shyfem/status"
        r = client.get(endpoint)
        assert r.status_code == 404
        content = self.get_content(r)
        assert isinstance(content, str) and "No SHYFEM data available" in content

    def test_shyfem_status_invalid_ready_filename(
        self, client: FlaskClient, faker: Faker
    ) -> None:
        """Test status endpoint ignores READY files with invalid date format."""
        # Create READY file with invalid date (not 8 chars)
        shyfem_path = create_shyfem_directories()
        bolam_path = shyfem_path.joinpath("BOLAM")
        bolam_path.mkdir(parents=True, exist_ok=True)
        invalid_file = bolam_path.joinpath("202607.GEOSERVER.READY")
        invalid_file.touch()

        endpoint = API_URI + "/marine/shyfem/status"
        r = client.get(endpoint)
        assert r.status_code == 404

    def test_shyfem_stations_no_data(self, client: FlaskClient) -> None:
        """Test stations list endpoint when no data exists."""
        endpoint = API_URI + "/marine/shyfem/data/stations"
        r = client.get(endpoint)
        assert r.status_code == 404
        content = self.get_content(r)
        assert isinstance(content, str) and (
            "does not exist" in content or "No station data files found" in content
        )

    def test_shyfem_stations_success(self, client: FlaskClient, faker: Faker) -> None:
        """Test stations list endpoint with valid data."""
        forcings_files = {
            "BOLAM": [
                "BOLAM_20260701_assim_station_timeseries.json",
                "BOLAM_20260701_noassim_station_timeseries.json",
                "BOLAM_20260630_assim_station_timeseries.json",
            ],
            "ECMWF": ["ECMWF_20260630_assim_station_timeseries.json"],
            "ICON": [
                "ICON_20260701_noassim_station_timeseries.json",
                "ICON_20260628_assim_station_timeseries.json",
            ],
        }

        for forcing, filenames in forcings_files.items():
            for filename in filenames:
                create_station_file(forcing, filename, {"stations": []})

        endpoint = API_URI + "/marine/shyfem/data/stations"
        r = client.get(endpoint)
        assert r.status_code == 200

        response = self.get_content(r)
        assert isinstance(response, dict)

        # Check structure
        for forcing, filenames in forcings_files.items():
            assert forcing in response
            assert isinstance(response[forcing], list)
            # Files should be sorted in reverse (latest first)
            expected_sorted = sorted(filenames, reverse=True)
            assert response[forcing] == expected_sorted

    def test_shyfem_stations_no_files(self, client: FlaskClient, faker: Faker) -> None:
        """Test stations endpoint when directories exist but have no station files."""
        # Create empty directories without station files
        for forcing in ["BOLAM", "ECMWF", "ICON"]:
            create_shyfem_directories()
            forcing_path = Path(Env.get("MER_DATA_PATH", "/shyfem")).joinpath(forcing)
            forcing_path.mkdir(parents=True, exist_ok=True)

        endpoint = API_URI + "/marine/shyfem/data/stations"
        r = client.get(endpoint)
        assert r.status_code == 404
        content = self.get_content(r)
        assert isinstance(content, str) and "No station data files found" in content

    def test_shyfem_stations_only_some_forcings(
        self, client: FlaskClient, faker: Faker
    ) -> None:
        """Test stations endpoint when only some forcings have data."""
        # Only create files for BOLAM and ICON
        for forcing in ["BOLAM", "ICON"]:
            create_station_file(
                forcing,
                f"{forcing}_20260701_assim_station_timeseries.json",
                {"stations": []},
            )
            create_station_file(
                forcing,
                f"{forcing}_20260701_noassim_station_timeseries.json",
                {"stations": []},
            )

        # ECMWF has directory but no files
        shyfem_path = create_shyfem_directories()
        ecmwf_path = shyfem_path.joinpath("ECMWF")
        ecmwf_path.mkdir(parents=True, exist_ok=True)

        endpoint = API_URI + "/marine/shyfem/data/stations"
        r = client.get(endpoint)
        assert r.status_code == 200

        response = self.get_content(r)
        assert "BOLAM" in response
        assert "ICON" in response
        assert "ECMWF" not in response

    def test_shyfem_station_file_success(
        self, client: FlaskClient, faker: Faker
    ) -> None:
        """Test station file endpoint retrieves file successfully."""
        # Create station file with test data
        station_data = {
            "stations": [
                {
                    "code": "ANC",
                    "lat": 45.5,
                    "lon": 12.5,
                    "offset": {"dx": 0.1, "dy": 0.2},
                },
                {
                    "code": "VEN",
                    "lat": 45.6,
                    "lon": 12.6,
                    "offset": {"dx": 0.15, "dy": 0.25},
                },
            ]
        }
        create_station_file(
            "BOLAM", "BOLAM_20260701_assim_station_timeseries.json", station_data
        )

        endpoint = (
            API_URI
            + "/marine/shyfem/data/stations/BOLAM/BOLAM_20260701_assim_station_timeseries.json"
        )
        r = client.get(endpoint)
        assert r.status_code == 200

        response = self.get_content(r)
        assert isinstance(response, dict)
        assert "stations" in response
        assert len(response["stations"]) == 2
        assert response["stations"][0]["code"] == "ANC"

    def test_shyfem_station_file_case_insensitive_forcing(
        self, client: FlaskClient, faker: Faker
    ) -> None:
        """Test station file endpoint with lowercase forcing name."""
        create_station_file(
            "BOLAM", "BOLAM_20260701_assim_station_timeseries.json", {"stations": []}
        )

        # Request with lowercase forcing
        endpoint = (
            API_URI
            + "/marine/shyfem/data/stations/bolam/BOLAM_20260701_assim_station_timeseries.json"
        )
        r = client.get(endpoint)
        assert r.status_code == 200

    def test_shyfem_station_file_not_found(
        self, client: FlaskClient, faker: Faker
    ) -> None:
        """Test station file endpoint when file does not exist."""
        # Create directory structure but no files
        shyfem_path = create_shyfem_directories()
        bolam_path = shyfem_path.joinpath("BOLAM")
        bolam_path.mkdir(parents=True, exist_ok=True)

        endpoint = (
            API_URI
            + "/marine/shyfem/data/stations/BOLAM/20260701_station_timeseries.json"
        )
        r = client.get(endpoint)
        assert r.status_code == 404
        content = self.get_content(r)
        assert isinstance(content, str) and "not found" in content.lower()

    def test_shyfem_station_file_invalid_forcing(
        self, client: FlaskClient, faker: Faker
    ) -> None:
        """Test station file endpoint with invalid forcing name."""
        endpoint = (
            API_URI
            + "/marine/shyfem/data/stations/INVALID/20260701_station_timeseries.json"
        )
        r = client.get(endpoint)
        assert r.status_code == 404
        content = self.get_content(r)
        assert isinstance(content, str) and "Unknown forcing" in content

    def test_shyfem_station_file_directory_traversal_attempt(
        self, client: FlaskClient, faker: Faker
    ) -> None:
        """Test station file endpoint prevents directory traversal attacks."""
        # Create a legitimate station file
        create_station_file(
            "BOLAM", "BOLAM_20260701_assim_station_timeseries.json", {"stations": []}
        )

        # Create a file outside the BOLAM directory
        shyfem_path = Path(Env.get("MER_DATA_PATH", "/shyfem"))
        secret_file = shyfem_path.joinpath("secret.json")
        secret_file.write_text('{"secret": "data"}')

        # Try directory traversal
        endpoint = API_URI + "/marine/shyfem/data/stations/BOLAM/../secret.json"
        r = client.get(endpoint)
        assert r.status_code == 404

    def test_shyfem_station_file_double_dot_traversal(
        self, client: FlaskClient, faker: Faker
    ) -> None:
        """Test station file endpoint with encoded directory traversal."""
        create_station_file(
            "BOLAM", "BOLAM_20260701_assim_station_timeseries.json", {"stations": []}
        )

        # Try various traversal patterns
        traversal_patterns = [
            "..%2F..%2Fsecret.json",
            "../../secret.json",
        ]

        for pattern in traversal_patterns:
            endpoint = API_URI + f"/marine/shyfem/data/stations/BOLAM/{pattern}"
            r = client.get(endpoint)
            assert r.status_code == 404

    def test_shyfem_station_file_malformed_json(
        self, client: FlaskClient, faker: Faker
    ) -> None:
        """Test station file endpoint with malformed JSON file."""
        # Create file with invalid JSON
        shyfem_path = create_shyfem_directories()
        bolam_path = shyfem_path.joinpath("BOLAM")
        bolam_path.mkdir(parents=True, exist_ok=True)
        json_path = bolam_path.joinpath("json")
        json_path.mkdir(parents=True, exist_ok=True)
        station_file = json_path.joinpath("20260701_station_timeseries.json")
        station_file.write_text("not valid json {")

        endpoint = (
            API_URI
            + "/marine/shyfem/data/stations/BOLAM/20260701_station_timeseries.json"
        )
        r = client.get(endpoint)
        assert r.status_code == 404
        content = self.get_content(r)
        assert isinstance(content, str) and "Error reading file" in content

    def test_shyfem_station_file_empty_json(
        self, client: FlaskClient, faker: Faker
    ) -> None:
        """Test station file endpoint with empty JSON object."""
        # Create file with empty object
        shyfem_path = create_shyfem_directories()
        bolam_path = shyfem_path.joinpath("BOLAM")
        bolam_path.mkdir(parents=True, exist_ok=True)
        json_path = bolam_path.joinpath("json")
        json_path.mkdir(parents=True, exist_ok=True)
        station_file = json_path.joinpath("20260701_station_timeseries.json")
        station_file.write_text("{}")

        endpoint = (
            API_URI
            + "/marine/shyfem/data/stations/BOLAM/20260701_station_timeseries.json"
        )
        r = client.get(endpoint)
        assert r.status_code == 200
        response = self.get_content(r)
        assert response == {}

    def test_shyfem_station_file_special_characters_in_filename(
        self, client: FlaskClient, faker: Faker
    ) -> None:
        """Test station file endpoint with special characters in filename."""
        # Create file with valid name pattern
        create_station_file(
            "BOLAM", "BOLAM_20260701_assim_station_timeseries.json", {"stations": []}
        )

        # Try to request file with special characters
        endpoint = (
            API_URI
            + "/marine/shyfem/data/stations/BOLAM/BOLAM_20260701_assim_station_timeseries<script>.json"
        )
        r = client.get(endpoint)
        assert r.status_code == 404

    def test_shyfem_integration_status_to_file(
        self, client: FlaskClient, faker: Faker
    ) -> None:
        """Integration test: get status, then fetch file from available forcing."""
        # Setup SHYFEM data
        station_data = {"stations": [{"code": "TEST", "name": "Test Station"}]}

        for forcing in ["BOLAM", "ECMWF", "ICON"]:
            # Create READY file
            create_ready_files(forcing, ["20260701"])

            # Create station files (both assim and noassim)
            create_station_file(
                forcing,
                f"{forcing}_20260701_assim_station_timeseries.json",
                station_data,
            )
            create_station_file(
                forcing,
                f"{forcing}_20260701_noassim_station_timeseries.json",
                station_data,
            )

        # Get status
        status_endpoint = API_URI + "/marine/shyfem/status"
        r = client.get(status_endpoint)
        assert r.status_code == 200
        status = self.get_content(r)

        latest_run = status["latestRun"]
        available_forcings = status["availableForcings"]

        # Fetch file from first available forcing (assim variant)
        if available_forcings:
            forcing = available_forcings[0]
            file_endpoint = (
                API_URI
                + f"/marine/shyfem/data/stations/{forcing}/{forcing}_{latest_run}_assim_station_timeseries.json"
            )
            r = client.get(file_endpoint)
            assert r.status_code == 200
            file_content = self.get_content(r)
            assert file_content["stations"][0]["code"] == "TEST"
