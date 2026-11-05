"""Regression coverage for the shared ICON/WRF discovery schedule."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from maps.datasets import windy
from maps.datasets.monitoring import discovery_schedules
from maps.tasks import check_fs_data
from restapi.connectors.celery import CeleryExt


def test_shared_windy_schedule_discovers_icon_and_wrf():
    manifest = os.environ.get(
        "DATASET_CONFIG_PATH", str(Path(__file__).parents[3] / "datasets.yml")
    )
    with (
        patch.dict(os.environ, {"DATASET_CONFIG_PATH": str(manifest)}),
        patch.object(CeleryExt, "app", MagicMock()),
        patch.object(windy.Env, "get", side_effect=lambda key, default=None: default),
        patch.object(windy, "DataWatcher") as watcher,
        patch.object(windy.celery, "get_instance", return_value=MagicMock()),
    ):
        schedules = [
            entry for entry in discovery_schedules()
            if entry[1] == "check_latest_data_and_trigger_geoserver_import_windy"
        ]
        assert len(schedules) == 1
        check_fs_data.check_latest_data_and_trigger_geoserver_import_windy.run(
            *schedules[0][2]
        )

    scanned = [path for call in watcher.call_args_list for path in call.kwargs["paths"]]
    assert scanned == [
        "/windy/Windy-00-ICON_2I_all2km.web/Italia",
        "/windy/Windy-12-ICON_2I_all2km.web/Italia",
        "/windy/Windy-00-WRF.web/Italia",
        "/windy/Windy-12-WRF.web/Italia",
    ]
    assert watcher.return_value.check_and_trigger.call_count == 2


def test_explicit_windy_paths_are_not_discovered_twice():
    paths = ["/windy/Windy-12-WRF.web/Italia"]
    with (
        patch.object(CeleryExt, "app", MagicMock()),
        patch.object(check_fs_data, "load_adapter") as load_adapter,
    ):
        check_fs_data.check_latest_data_and_trigger_geoserver_import_windy.run(paths)

    load_adapter.assert_called_once_with("icon")
    load_adapter.return_value.discover.assert_called_once_with(paths)
