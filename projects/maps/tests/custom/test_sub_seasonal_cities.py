"""City JSON routes remain available with dynamic dataset status enabled."""

import json
from pathlib import Path

import pytest
from flask import Flask
from maps.endpoints import sub_seasonal
from restapi.env import Env
from restapi.exceptions import NotFound
from restapi.rest.loader import EndpointsLoader


@pytest.fixture(params=[False, True], ids=["legacy", "dynamic"])
def cities(tmp_path, monkeypatch, request):
    manifest = Path(Env.get("DATASET_CONFIG_PATH", "/etc/meteohub/datasets.yml"))
    monkeypatch.setenv("DATASET_CONFIG_PATH", str(manifest))
    monkeypatch.setenv("ACTIVATE_DYNAMIC_DATASETS", str(int(request.param)))
    monkeypatch.setenv("SUB_SEASONAL_DATA_PATH", str(tmp_path))
    monkeypatch.setattr(sub_seasonal, "JSONS_PATH", tmp_path / "json_weekly")
    Env.get.cache_clear()
    Env.get_bool.cache_clear()
    root = tmp_path / "json_weekly"
    root.mkdir()
    try:
        yield root
    finally:
        Env.get.cache_clear()
        Env.get_bool.cache_clear()


@pytest.fixture
def cities_client(cities):
    app = Flask(__name__)
    for endpoint in (
        sub_seasonal.SubSeasonalJSONsEndpoint,
        sub_seasonal.SubSeasonalJSONFileEndpoint,
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


def test_lists_sorted_json_paths(cities, cities_client):
    (cities / "week1").mkdir()
    (cities / "week1" / "Roma.json").write_text("{}")
    (cities / "Bologna.JSON").write_text("{}")
    (cities / "notes.txt").write_text("not a JSON file")
    (cities / "directory.json").mkdir()

    response = cities_client.get("/api/sub-seasonal/data/cities")

    assert response.status_code == 200
    assert response.json == ["Bologna.JSON", "week1/Roma.json"]


def test_returns_nested_json_content(cities, cities_client):
    (cities / "week1").mkdir()
    content = {"city": "Forlì", "values": [1, 2, 3]}
    (cities / "week1" / "Forli.json").write_text(
        json.dumps(content, ensure_ascii=False), encoding="utf-8"
    )

    response = cities_client.get("/api/sub-seasonal/data/cities/week1/Forli.json")

    assert response.status_code == 200
    assert response.json == content


def test_empty_city_directory(cities_client):
    response = cities_client.get("/api/sub-seasonal/data/cities")
    assert response.status_code == 200
    assert response.json == []


def test_missing_city_directory(cities, cities_client):
    cities.rmdir()
    assert cities_client.get("/api/sub-seasonal/data/cities").status_code == 404


@pytest.mark.parametrize("filename", ["missing.json", "invalid.json", "folder.json"])
def test_missing_invalid_or_directory_returns_404(cities, cities_client, filename):
    (cities / "invalid.json").write_text("invalid JSON")
    (cities / "folder.json").mkdir()
    response = cities_client.get(f"/api/sub-seasonal/data/cities/{filename}")
    assert response.status_code == 404


def test_path_traversal_and_symlinks_are_blocked(cities, cities_client):
    outside = cities.parent / "json_weekly_private"
    outside.mkdir()
    secret = outside / "secret.json"
    secret.write_text('{"secret": true}')
    (cities / "escape.json").symlink_to(secret)

    response = cities_client.get("/api/sub-seasonal/data/cities")
    assert response.status_code == 200
    assert response.json == []
    for filename in ("../json_weekly_private/secret.json", "escape.json"):
        response = cities_client.get(f"/api/sub-seasonal/data/cities/{filename}")
        assert response.status_code == 404
    with cities_client.application.test_request_context():
        with pytest.raises(NotFound):
            sub_seasonal.SubSeasonalJSONFileEndpoint().get(str(secret))
