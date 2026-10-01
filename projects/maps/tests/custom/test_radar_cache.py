"""Radar batches preserve unchanged cache keys and seed new timesteps."""

from unittest.mock import MagicMock

import pytest

from maps.datasets import radar_processing as radar
from maps.datasets.cache import GWCInvalidator


@pytest.mark.parametrize("has_new_time", [True, False])
def test_overlapping_radar_batch_preserves_existing_times_at_zoom_5_to_9(
    tmp_path, monkeypatch, has_new_time
):
    copies = tmp_path / "copies" / "radar-sri"
    copies.mkdir(parents=True)
    source = tmp_path / "radar" / "sri"
    source.mkdir(parents=True)
    # An old queued full-window task must not invalidate the unchanged old file.
    filenames = ["18-09-2026-10-00.tif", "18-09-2026-10-05.tif"]
    for filename in filenames:
        (copies / filename).touch()
    old = "2026-09-18T09:55:00.000Z"
    overlapping = "2026-09-18T10:00:00.000Z"
    new = "2026-09-18T10:05:00.000Z"
    invalidator = MagicMock()
    invalidator.get_granule_times.side_effect = (
        [[old, overlapping], [overlapping, new]]
        if has_new_time else [[overlapping, new], [overlapping, new]]
    )
    invalidator._normalize_time = GWCInvalidator._normalize_time
    constructor = MagicMock(return_value=invalidator)
    schedule = MagicMock()
    monkeypatch.setattr(radar, "GWCInvalidator", constructor)
    monkeypatch.setattr(radar, "COPIES_BASE_DIRECTORY", str(tmp_path / "copies"))
    monkeypatch.setattr(radar, "RADAR_BASE_DIRECTORY", str(tmp_path / "radar"))
    monkeypatch.setattr(radar, "update_slds_from_local_folders", MagicMock())
    monkeypatch.setattr(radar, "process_radar_file", MagicMock(return_value=True))
    monkeypatch.setattr(radar, "force_update_geoserver_radar_layers_index", MagicMock())
    monkeypatch.setattr(radar, "schedule_cache_refresh_chord", schedule)

    radar.update_geoserver_radar_layers(
        None, "sri", filenames, ["202609181000", "202609181005"],
        sld_directory=str(tmp_path), cache_config={"zoom_start": 5, "zoom_stop": 9},
    )

    if not has_new_time:
        assert schedule.call_args.args[0] == []
        return
    request = schedule.call_args.args[0][0]
    assert request["times"] == [old, new]
    assert request["warm_times"] == [new]
    assert request["zoom_start"] == 5
    assert request["zoom_stop"] == 9
