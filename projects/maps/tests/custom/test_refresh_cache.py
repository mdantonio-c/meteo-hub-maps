"""CLI coverage for bounded manual GWC warming."""

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from maps.datasets.cache import TemporalCacheLayer


@pytest.fixture
def refresh_script(monkeypatch):
    path = Path(__file__).resolve().parents[2] / "backend/scripts/refresh_cache.py"
    spec = importlib.util.spec_from_file_location("refresh_cache", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    invalidator = MagicMock()
    invalidator.get_granule_times.return_value = ["first", "second"]
    invalidator.get_default_style.return_value = "radar_sri"
    monkeypatch.setattr(module, "GWCInvalidator", lambda *args, **kwargs: invalidator)
    monkeypatch.setattr(
        module,
        "_resolve_cache_layer",
        lambda *args: TemporalCacheLayer("radar-sri", "mosaic_radar-sri"),
    )
    return module, invalidator


@pytest.mark.parametrize("explicit", [False, True])
def test_refresh_seeds_all_requested_times_with_default_parallelism(
    refresh_script, monkeypatch, explicit
):
    script, invalidator = refresh_script
    args = ["refresh_cache", "--variable", "sri"]
    if explicit:
        args += ["--times", "first", "second"]
    monkeypatch.setattr(script.sys, "argv", args)

    assert script.main() == 0
    assert invalidator.truncate.call_args_list == [
        call("radar-sri", times=["first"], style_name="radar_sri"),
        call("radar-sri", times=["second"], style_name="radar_sri"),
    ]
    invalidator.seed.assert_called_once_with(
        "radar-sri",
        times=["first", "second"],
        style_name="radar_sri",
        wait=True,
        parallelism=4,
    )


def test_refresh_configurable_parallelism_and_no_wait(refresh_script, monkeypatch):
    script, invalidator = refresh_script
    monkeypatch.setattr(
        script.sys,
        "argv",
        ["refresh_cache", "--variable", "sri", "--parallelism", "2", "--no-wait"],
    )
    assert script.main() == 0
    assert invalidator.seed.call_args.kwargs["parallelism"] == 2
    assert invalidator.seed.call_args.kwargs["wait"] is False


def test_refresh_rejects_invalid_parallelism(refresh_script, monkeypatch):
    script, invalidator = refresh_script
    monkeypatch.setattr(script.sys, "argv", ["refresh_cache", "--parallelism", "0"])
    with pytest.raises(SystemExit) as exc:
        script.main()
    assert exc.value.code == 2
    invalidator.seed.assert_not_called()


def test_refresh_does_not_seed_after_failed_truncation(refresh_script, monkeypatch):
    script, invalidator = refresh_script
    monkeypatch.setattr(script.sys, "argv", ["refresh_cache", "--variable", "sri"])
    invalidator.truncate.return_value = False
    assert script.main() == 1
    invalidator.seed.assert_not_called()


def test_refresh_reports_batch_progress(refresh_script, monkeypatch, capsys):
    script, invalidator = refresh_script
    invalidator.get_granule_times.return_value = [f"time-{index}" for index in range(5)]
    monkeypatch.setattr(script.sys, "argv", ["refresh_cache", "--variable", "sri"])
    assert script.main() == 0
    assert [len(item.kwargs["times"]) for item in invalidator.seed.call_args_list] == [
        4,
        1,
    ]
    output = capsys.readouterr().out
    assert "Truncate 5/5: time-4" in output
    assert "Seed batch 1/2" in output
    assert "Seed batch 2/2 complete (5/5 timesteps)" in output
    assert "Refresh complete" in output
