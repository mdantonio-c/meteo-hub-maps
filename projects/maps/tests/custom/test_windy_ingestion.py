"""Regression tests for repeat Windy ImageMosaic ingestion."""

import sys
import types
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import MagicMock, patch


celery_module = types.ModuleType("restapi.connectors.celery")
celery_module.CeleryExt = types.SimpleNamespace(task=lambda **_: lambda function: function)
sys.modules.setdefault("restapi.connectors.celery", celery_module)

env_module = types.ModuleType("restapi.env")
env_module.Env = types.SimpleNamespace(get=lambda _name, default=None: default)
sys.modules.setdefault("restapi.env", env_module)

logs_module = types.ModuleType("restapi.utilities.logs")
logs_module.log = MagicMock()
sys.modules.setdefault("restapi.utilities.logs", logs_module)

maps_module = types.ModuleType("maps")
maps_module.__path__ = []
sys.modules.setdefault("maps", maps_module)

tasks_module = types.ModuleType("maps.tasks")
tasks_module.__path__ = []
sys.modules.setdefault("maps.tasks", tasks_module)

geoserver_utils_module = types.ModuleType("maps.tasks.geoserver_utils")
geoserver_utils_module.create_ready_file_generic = MagicMock()
geoserver_utils_module.create_workspace_generic = MagicMock()
geoserver_utils_module.upload_sld_generic = MagicMock()
geoserver_utils_module.process_sld_files = MagicMock()
geoserver_utils_module.check_coverage_exists = MagicMock()
sys.modules.setdefault("maps.tasks.geoserver_utils", geoserver_utils_module)

datasets_module = types.ModuleType("maps.datasets")
datasets_module.__path__ = []
sys.modules.setdefault("maps.datasets", datasets_module)

cache_module = types.ModuleType("maps.datasets.cache")
cache_module.GWCInvalidator = MagicMock()
cache_module.TemporalCacheLayer = MagicMock()
sys.modules.setdefault("maps.datasets.cache", cache_module)

module_path = Path("/code/maps/tasks/upload_image_mosaic.py")
spec = spec_from_file_location("maps.tasks.upload_image_mosaic", module_path)
windy_task = module_from_spec(spec)
sys.modules[spec.name] = windy_task
spec.loader.exec_module(windy_task)


@patch.object(windy_task.requests, "post")
def test_publish_layer_accepts_existing_mosaic_coverage(mock_post):
    """A repeat run must refresh GWC even when GeoServer returns 409."""
    mock_post.return_value = MagicMock(status_code=409, text="Coverage already exists")

    assert windy_task.publish_layer("t2m-t2m", "t2m-t2m", "http://geoserver") is True
