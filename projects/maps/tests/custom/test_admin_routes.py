"""Regression checks for production admin service routing and startup."""

import base64
import os
import re
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
import yaml

PROJECT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("name", ["host_nginx.config", "host_nginx_dev.config"])
@pytest.mark.parametrize("service", ["geoserver", "flower"])
def test_host_admin_redirects_are_explicit_and_not_cached(name, service):
    text = (PROJECT / "builds" / name).read_text()
    match = re.search(rf"location = /{service}\s*\{{([^}}]+)\}}", text)
    assert match is not None
    assert f"return 302 /{service}/;" in match[1]
    assert 'add_header Cache-Control "no-store" always;' in match[1]


def test_docker_geoserver_redirect_does_not_reach_api_fallback():
    text = (PROJECT / "confs/public_geoserver.service").read_text()
    assert "location = /geoserver {" in text
    assert "return 302 /geoserver/;" in text
    assert 'add_header Cache-Control "no-store" always;' in text


def test_flower_uses_project_dependencies_and_prefixed_healthcheck():
    services = yaml.safe_load((PROJECT / "confs/production.yml").read_text())["services"]
    flower = services["flower"]
    assert flower["image"] == "maps/backend:${RAPYDO_VERSION}"
    assert flower["build"] == "${PROJECT_DIR}/builds/backend"
    assert "--url_prefix=flower" in flower["command"]
    assert "--basic_auth=${FLOWER_USER}:${FLOWER_PASSWORD}" in flower["command"]
    assert isinstance(flower["healthcheck"]["test"], str)
    assert "/flower/" in flower["healthcheck"]["test"]


def test_flower_healthcheck_authenticates_on_the_prefixed_route():
    credentials = "monitor:p@ss:word/#"
    authorization = "Basic " + base64.b64encode(credentials.encode()).decode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            authorized = self.headers.get("Authorization") == authorization
            self.send_response(200 if authorized and self.path == "/flower/" else 401)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        services = yaml.safe_load((PROJECT / "confs/production.yml").read_text())["services"]
        command = services["flower"]["healthcheck"]["test"]
        assert isinstance(command, str)
        subprocess.run(
            command,
            shell=True,
            env={
                **os.environ,
                "FLOWER_USER": "monitor",
                "FLOWER_PASSWORD": "p@ss:word/#",
                "FLOWER_PORT": str(server.server_port),
            },
            check=True,
            timeout=10,
            capture_output=True,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
