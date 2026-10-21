import json
import shutil
from pathlib import Path

import pytest
from restapi.env import Env
from restapi.tests import API_URI, BaseTests, FlaskClient


def ww3_path() -> Path:
    return Path(Env.get("WW3_DATA_PATH", "/ww3"))


@pytest.fixture(autouse=True)
def setup_ww3_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WW3_DATA_PATH", "/tmp/ww3_test")
    shutil.rmtree("/tmp/ww3_test", ignore_errors=True)
    yield
    shutil.rmtree("/tmp/ww3_test", ignore_errors=True)


class TestWW3Vectors(BaseTests):
    def test_vector_file_uses_mediterraneo_directory(
        self, client: FlaskClient
    ) -> None:
        vectors_path = ww3_path() / "Mediterraneo" / "dir-dir" / "5"
        vectors_path.mkdir(parents=True)
        vector_file = vectors_path / "14-09-2026-01-00.geojson"
        vector_file.write_text(json.dumps({"type": "FeatureCollection", "features": []}))

        response = client.get(
            f"{API_URI}/ww3/vectors/5/14-09-2026-01-00.geojson"
        )

        assert response.status_code == 200
        assert self.get_content(response) == {
            "type": "FeatureCollection",
            "features": [],
        }

    def test_list_vectors_includes_zoom_directory(self, client: FlaskClient) -> None:
        vectors_path = ww3_path() / "Mediterraneo" / "dir-dir" / "5"
        vectors_path.mkdir(parents=True)
        (vectors_path / "14-09-2026-01-00.geojson").write_text("{}")

        response = client.get(f"{API_URI}/ww3/vectors")

        assert response.status_code == 200
        assert self.get_content(response) == ["5/14-09-2026-01-00.geojson"]
