"""Seasonal boxplot routes work in both legacy and dynamic dataset modes."""

import json
from pathlib import Path

import pytest
from flask import Flask
from maps.endpoints import seasonal
from restapi.env import Env
from restapi.exceptions import NotFound
from restapi.rest.loader import EndpointsLoader


@pytest.fixture(params=[False, True], ids=["legacy", "dynamic"])
def boxplot(tmp_path, monkeypatch, request):
    manifest = Path(Env.get("DATASET_CONFIG_PATH", "/etc/meteohub/datasets.yml"))
    monkeypatch.setenv("DATASET_CONFIG_PATH", str(manifest))
    monkeypatch.setenv("ACTIVATE_DYNAMIC_DATASETS", str(int(request.param)))
    monkeypatch.setenv("SEASONAL_DATA_PATH", str(tmp_path))
    # Dynamic mode must resolve the manifest's path, not the import-time constant.
    legacy_path = tmp_path / "unused" if request.param else tmp_path
    monkeypatch.setattr(seasonal, "SEASONAL_PATH", str(legacy_path))
    Env.get.cache_clear()
    Env.get_bool.cache_clear()
    root = tmp_path / "boxplot"
    root.mkdir()
    try:
        yield root
    finally:
        Env.get.cache_clear()
        Env.get_bool.cache_clear()


@pytest.fixture
def seasonal_client(boxplot):
    app = Flask(__name__)
    for endpoint in (
        seasonal.SeasonalBoxplotListEndpoint,
        seasonal.SeasonalFileEndpoint,
    ):
        skip, _ = EndpointsLoader.skip_endpoint(endpoint.depends_on)
        if not skip:
            app.add_url_rule(
                endpoint.get.uri,
                view_func=endpoint.as_view(endpoint.__name__),
            )

    @app.errorhandler(NotFound)
    def not_found(error):
        return {"error": str(error)}, 404

    return app.test_client()


def test_lists_sorted_files_without_recursing(boxplot, seasonal_client):
    (boxplot / "Roma.json").write_text("{}")
    (boxplot / "Bologna.json").write_text("{}")
    (boxplot / "nested").mkdir()
    (boxplot / "nested" / "hidden.json").write_text("{}")

    response = seasonal_client.get("/api/seasonal/json")

    assert response.status_code == 200
    assert response.json == ["Bologna.json", "Roma.json"]


def test_returns_json_content(boxplot, seasonal_client):
    content = {"city": "Forlì", "values": [1, 2, 3]}
    (boxplot / "Forli.json").write_text(
        json.dumps(content, ensure_ascii=False), encoding="utf-8"
    )

    response = seasonal_client.get("/api/seasonal/json/Forli.json")

    assert response.status_code == 200
    assert response.json == content


def test_empty_directory(seasonal_client):
    response = seasonal_client.get("/api/seasonal/json")
    assert response.status_code == 200
    assert response.json == []


def test_missing_directory(boxplot, seasonal_client):
    boxplot.rmdir()
    assert seasonal_client.get("/api/seasonal/json").status_code == 404


@pytest.mark.parametrize("filename", ["missing.json", "invalid.json", "folder.json"])
def test_missing_invalid_or_directory_returns_404(boxplot, seasonal_client, filename):
    (boxplot / "invalid.json").write_text("invalid JSON")
    (boxplot / "folder.json").mkdir()
    response = seasonal_client.get(f"/api/seasonal/json/{filename}")
    assert response.status_code == 404


def test_path_traversal_and_symlinks_are_blocked(boxplot, seasonal_client):
    outside = boxplot.parent / "boxplot_private"
    outside.mkdir()
    secret = outside / "secret.json"
    secret.write_text('{"secret": true}')
    (boxplot / "escape.json").symlink_to(secret)

    response = seasonal_client.get("/api/seasonal/json")
    assert response.status_code == 200
    assert response.json == []
    assert seasonal_client.get("/api/seasonal/json/escape.json").status_code == 404
    with seasonal_client.application.test_request_context():
        for filename in ("../boxplot_private/secret.json", str(secret)):
            with pytest.raises(NotFound):
                seasonal.SeasonalFileEndpoint().get(filename)
