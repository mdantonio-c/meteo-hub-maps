"""Producer wiring tests for deferred GeoServer ready markers."""

from unittest.mock import MagicMock, patch

from maps.datasets.cache import TemporalCacheLayer
from maps.datasets import discovery as check_fs_data
from maps.datasets import seasonal_processing as data_ready
from maps.datasets import radar_processing as radar
from maps.datasets import sub_seasonal_processing as sub_seasonal
from maps.datasets import ww3_processing as ww3
from maps.datasets import windy_processing as windy


def _assert_chord_request(chord_mock, expected_layers):
    requests = chord_mock.call_args.args[0]
    assert [request["layer_name"] for request in requests] == expected_layers
    assert all(request["workspace"] == "meteohub" for request in requests)
    assert chord_mock.call_args.kwargs["ready_file"].endswith(".GEOSERVER.READY")


def test_seasonal_ingestion_chords_all_published_layers(tmp_path, monkeypatch):
    monkeypatch.setattr(data_ready, "SEASONAL_BASE_DIRECTORY", str(tmp_path))
    layers = [
        TemporalCacheLayer("seasonal-mean-TM", "mosaic-mean-TM"),
        TemporalCacheLayer("seasonal-sum-P", "mosaic-sum-P"),
    ]
    with patch.object(data_ready, "process_seasonal_tiff_files", return_value=layers), patch.object(
        data_ready, "schedule_cache_refresh_chord"
    ) as schedule:
        data_ready.update_geoserver_seasonal_layers(
            date="20260928", sld_directory=str(tmp_path / "missing-slds")
        )

    _assert_chord_request(schedule, [layer.name for layer in layers])
    assert [request["store_name"] for request in schedule.call_args.args[0]] == [
        layer.store_name for layer in layers
    ]


def test_subseasonal_ingestion_chords_published_variables(tmp_path, monkeypatch):
    monkeypatch.setattr(sub_seasonal, "SUB_SEASONAL_BASE_PATH", str(tmp_path))
    (tmp_path / "precip" / "week1").mkdir(parents=True)
    monkeypatch.setattr(
        sub_seasonal, "process_sub_seasonal_variable", lambda _var, _val: True
    )
    with patch.object(sub_seasonal, "update_slds_from_local_folders"), patch.object(
        sub_seasonal, "schedule_cache_refresh_chord"
    ) as schedule:
        sub_seasonal.update_geoserver_sub_seasonal_layers(None,
            run_date="20260928", range_str="20260928-20261004"
        )

    _assert_chord_request(schedule, ["sub-seasonal-precip-week1"])
    assert schedule.call_args.args[0][0]["store_name"] == (
        "mosaic-sub-seasonal-precip-week1"
    )


def test_ww3_ingestion_chords_each_variable(tmp_path, monkeypatch):
    base_path = tmp_path / "Mediterraneo"
    (base_path / "hs").mkdir(parents=True)
    (base_path / "tp").mkdir()
    monkeypatch.setattr(ww3, "WW3_BASE_PATH", str(base_path))
    monkeypatch.setattr(ww3, "process_ww3_variable", MagicMock())
    monkeypatch.setattr(ww3, "update_slds_from_local_folders", MagicMock())
    real_exists = ww3.os.path.exists
    monkeypatch.setattr(
        ww3.os.path,
        "exists",
        lambda path: real_exists(path) if str(path).startswith(str(base_path)) else False,
    )

    with patch.object(ww3, "schedule_cache_refresh_chord") as schedule:
        ww3.update_geoserver_ww3_layers(None, run_date="20260928")

    requests = schedule.call_args.args[0]
    assert sorted(request["layer_name"] for request in requests) == [
        "ww3_hs",
        "ww3_tp",
    ]
    assert sorted(request["store_name"] for request in requests) == [
        "mosaic_ww3_hs",
        "mosaic_ww3_tp",
    ]
    assert schedule.call_args.kwargs["ready_file"].endswith(".GEOSERVER.READY")


def test_radar_ingestion_chords_affected_cache_times(tmp_path, monkeypatch):
    radar_root = tmp_path / "radar"
    copies_root = tmp_path / "copies"
    (radar_root / "sri").mkdir(parents=True)
    copy_layer = copies_root / "radar-sri"
    copy_layer.mkdir(parents=True)
    filename = "28-09-2026-09-30.tif"
    monkeypatch.setattr(radar, "RADAR_BASE_DIRECTORY", str(radar_root))
    monkeypatch.setattr(radar, "COPIES_BASE_DIRECTORY", str(copies_root))
    cache_config = {"eligible": True}
    def process_file(_variable, input_filename, *_args):
        (copy_layer / input_filename).touch()
        return True

    monkeypatch.setattr(radar, "process_radar_file", process_file)
    monkeypatch.setattr(radar, "force_update_geoserver_radar_layers_index", lambda *_args: True)
    monkeypatch.setattr(radar, "update_slds_from_local_folders", lambda *_args: True)
    sld_directory = str(tmp_path / "slds")
    real_exists = radar.os.path.exists
    monkeypatch.setattr(
        radar.os.path,
        "exists",
        lambda path: path == sld_directory or real_exists(path),
    )

    invalidator = MagicMock()
    invalidator.get_granule_times.side_effect = [
        [],
        ["2026-09-28T09:30:00.000Z"],
        ["2026-09-28T09:30:00.000Z"],
    ]
    invalidator._normalize_time.return_value = "2026-09-28T09:30:00.000Z"
    monkeypatch.setattr(radar, "GWCInvalidator", lambda *_args, **_kwargs: invalidator)

    with patch.object(radar, "schedule_cache_refresh_chord") as schedule:
        radar.update_geoserver_radar_layers(None,
            variable="sri",
            filenames=[filename],
            dates=["202609280930"],
            sld_directory=sld_directory,
            cache_config=cache_config,
        )

    _assert_chord_request(schedule, ["radar-sri"])
    request = schedule.call_args.args[0][0]
    assert request["times"] == ["2026-09-28T09:30:00.000Z"]
    assert request["warm_times"] == ["2026-09-28T09:30:00.000Z"]


def test_mer_ingestion_chords_layer_before_ready(tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    forcing_dir = tmp_path / "BOLAM"
    copies_dir = tmp_path / "copies"
    source_dir.mkdir()
    forcing_dir.mkdir()
    (source_dir / "input.tif").touch()
    monkeypatch.setattr(check_fs_data, "GEOSERVER_COPIES_BASE_DIRECTORY", str(copies_dir))

    with patch.object(check_fs_data, "upload_geotiff_generic", return_value=True), patch.object(
        check_fs_data, "publish_layer_generic", return_value=True
    ), patch.object(check_fs_data, "_enable_mer_time_dimension"), patch.object(
        check_fs_data, "schedule_cache_refresh_chord"
    ) as schedule:
        check_fs_data.update_geoserver_mer_bolam_layer(None,
            source_dir=str(source_dir),
            forcing_dir=str(forcing_dir),
            forcing_name="BOLAM",
            variable_name="t2m",
            run_date="20260928",
        )

    _assert_chord_request(schedule, ["SHYFEM-BOLAM-t2m"])
    assert schedule.call_args.kwargs["completion"] == {
        "forcing_dir": str(forcing_dir),
        "forcing_name": "BOLAM",
        "run_date": "20260928",
    }
    assert schedule.call_args.kwargs["checked_files"] == [
        str(forcing_dir / "20260928.t2m.CELERY.CHECKED")
    ]


def test_windy_ingestion_chords_layers_and_defers_ready_marker(monkeypatch):
    source_directory = "/windy/Windy-12-WRF.web/Italia"
    monkeypatch.setattr(
        "maps.datasets.windy_processing._ingest_windy_image_mosaic",
        lambda **_kwargs: ["t2m-t2m", "wind-10u"],
    )
    with patch(
        "maps.tasks.cache_control.schedule_cache_refresh_chord"
    ) as schedule:
        windy.update_geoserver_image_mosaic(
            None,
            "http://geoserver",
            "12",
            "20260928",
            "/SLDs",
            "WRF",
            source_directory,
        )

    _assert_chord_request(schedule, ["t2m-t2m", "wind-10u"])
    assert schedule.call_args.kwargs["ready_file"] == (
        f"{source_directory}/2026092812.GEOSERVER.READY"
    )
