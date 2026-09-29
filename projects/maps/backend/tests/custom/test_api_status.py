"""Tests for system status and maintenance endpoint."""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

import pytest
from restapi.env import Env


class TestSystemStatusEndpoint:
    """Test system status and maintenance signaling endpoint."""

    @pytest.fixture
    def temp_status_file(self):
        """Create a temporary status file for testing."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            temp_path = f.name
            json.dump({"status": "operational", "message": None}, f)
        
        original_path = Env.get("STATUS_FILE_PATH", "/etc/meteohub/status.json")
        os.environ["STATUS_FILE_PATH"] = temp_path
        
        yield temp_path
        
        os.environ["STATUS_FILE_PATH"] = original_path
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    def test_status_endpoint_returns_operational_by_default(self, client):
        """Should return operational status when no status file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            status_file = os.path.join(tmpdir, "status.json")
            os.environ["STATUS_FILE_PATH"] = status_file
            
            try:
                response = client.get("/api/status")
                assert response.status_code == 200
                data = response.get_json()
                
                assert data["status"] == "operational"
                assert "updated_at" in data
                assert "message" in data
                assert "affected_services" in data
            finally:
                if "STATUS_FILE_PATH" in os.environ:
                    del os.environ["STATUS_FILE_PATH"]

    def test_status_endpoint_reads_existing_status(self, client, temp_status_file):
        """Should read and return existing status from file."""
        status_data = {
            "status": "maintenance",
            "message": "Scheduled maintenance",
            "scheduled_start": "2025-01-15T02:00:00Z",
            "scheduled_end": "2025-01-15T06:00:00Z",
            "affected_services": ["maps", "windy"],
            "updated_at": "2025-01-14T10:00:00Z",
        }
        
        with open(temp_status_file, "w") as f:
            json.dump(status_data, f)
        
        response = client.get("/api/status")
        assert response.status_code == 200
        data = response.get_json()
        
        assert data["status"] == "maintenance"
        assert data["message"] == "Scheduled maintenance"
        assert data["scheduled_start"] == "2025-01-15T02:00:00Z"
        assert data["scheduled_end"] == "2025-01-15T06:00:00Z"
        assert data["affected_services"] == ["maps", "windy"]

    def test_status_update_endpoint_sets_maintenance(self, client, temp_status_file):
        """Should update status to maintenance via POST."""
        update_data = {
            "status": "maintenance",
            "message": "Database upgrade in progress",
            "scheduled_start": "2025-01-15T02:00:00Z",
            "scheduled_end": "2025-01-15T06:00:00Z",
            "affected_services": ["all"],
        }
        
        response = client.post(
            "/api/status",
            json=update_data,
            content_type="application/json",
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["status"]["status"] == "maintenance"
        assert data["status"]["message"] == "Database upgrade in progress"
        
        with open(temp_status_file, "r") as f:
            saved_status = json.load(f)
        
        assert saved_status["status"] == "maintenance"
        assert saved_status["message"] == "Database upgrade in progress"

    def test_status_update_endpoint_validates_status_values(self, client, temp_status_file):
        """Should reject invalid status values."""
        invalid_data = {"status": "invalid_status"}
        
        response = client.post(
            "/api/status",
            json=invalid_data,
            content_type="application/json",
        )
        
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "Invalid status" in data["error"]

    def test_status_update_endpoint_accepts_all_valid_statuses(self, client, temp_status_file):
        """Should accept all valid status values."""
        valid_statuses = ["operational", "maintenance", "degraded", "outage"]
        
        for status in valid_statuses:
            response = client.post(
                "/api/status",
                json={"status": status},
                content_type="application/json",
            )
            assert response.status_code == 200
            
            with open(temp_status_file, "r") as f:
                saved = json.load(f)
            assert saved["status"] == status

    def test_status_update_requires_json(self, client, temp_status_file):
        """Should reject requests without JSON body."""
        response = client.post("/api/status")
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data

    def test_status_update_with_partial_data(self, client, temp_status_file):
        """Should handle partial status updates."""
        update_data = {"status": "degraded", "message": "High latency detected"}
        
        response = client.post(
            "/api/status",
            json=update_data,
            content_type="application/json",
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"]["status"] == "degraded"
        assert data["status"]["message"] == "High latency detected"
        assert data["status"]["affected_services"] == []

    def test_status_endpoint_structure(self, client, temp_status_file):
        """Should return status with expected structure."""
        response = client.get("/api/status")
        assert response.status_code == 200
        data = response.get_json()
        
        required_fields = [
            "status",
            "message",
            "scheduled_start",
            "scheduled_end",
            "affected_services",
            "updated_at",
        ]
        
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
