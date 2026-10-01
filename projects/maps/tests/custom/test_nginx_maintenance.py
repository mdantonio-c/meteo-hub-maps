"""Verify Docker nginx's maintenance gate configuration and state transitions."""

import importlib.util
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

MODULE_PATH = Path(__file__).resolve().parents[2] / "builds/proxy/maintenance.py"
if not MODULE_PATH.exists():
    MODULE_PATH = Path("/opt/meteohub-proxy/maintenance.py")
SPEC = importlib.util.spec_from_file_location("nginx_maintenance", MODULE_PATH)
maintenance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(maintenance)


def test_allowlist_supports_ipv4_ipv6_and_cidr():
    content = maintenance.render_configuration(
        True, "192.0.2.1, 198.51.100.0/24\n2001:db8::1", "10.0.0.1"
    )
    assert "192.0.2.1/32 1;" in content
    assert "198.51.100.0/24 1;" in content
    assert "2001:db8::1/128 1;" in content
    assert "set_real_ip_from 10.0.0.1/32;" in content
    assert "real_ip_recursive on;" in content
    assert '"1:0" 1;' in content


@pytest.mark.parametrize(
    "value", ["all", "192.0.2.1;", "127.0.0.1\ninclude /tmp/bypass;"]
)
def test_invalid_allowlist_cannot_inject_directives(value):
    with pytest.raises(ValueError):
        maintenance.render_configuration(True, value, "")


def test_empty_allowlist_denies_everyone_and_headers_are_untrusted_by_default():
    content = maintenance.render_configuration(True, "", "")
    assert "geo $meteohub_maintenance_allowed {\n    default 0;\n}" in content
    assert "real_ip_header" not in content
    assert "set_real_ip_from" not in content
    assert "default 0;" in maintenance.render_configuration(False, "", "")


def test_status_changes_and_partial_updates_preserve_active_state(tmp_path):
    status_file = tmp_path / "status.json"
    assert not maintenance.maintenance_active(status_file)
    status_file.write_text(json.dumps({"status": "maintenance"}))
    assert maintenance.maintenance_active(status_file)
    for content in ("{", "null", '{"status":"unknown"}'):
        status_file.write_text(content)
        assert maintenance.maintenance_active(status_file, previous=True)
    status_file.unlink()
    assert maintenance.maintenance_active(status_file, previous=True)
    for status in ("operational", "degraded", "outage"):
        status_file.write_text(json.dumps({"status": status}))
        assert not maintenance.maintenance_active(status_file, previous=True)


def test_guard_applies_to_all_servers_before_location_returns(tmp_path):
    template = tmp_path / "production.conf"
    original = "upstream backend { server localhost; }\nserver {\nlocation / { return 204; }\n}\nserver {\n}\n"
    template.write_text(original)
    maintenance.guard_templates(tmp_path)
    content = template.read_text()
    assert content.count(maintenance.GUARD) == 2
    assert content.index(maintenance.GUARD) < content.index("return 204;")
    assert "upstream backend { server localhost; }" in content
    maintenance.guard_templates(tmp_path)
    assert template.read_text() == content


def test_framework_templates_guard_every_server(tmp_path):
    templates = (
        Path(__file__).resolve().parents[4]
        / "submodules/do/controller/builds/proxy/confs"
    )
    if not templates.exists():
        pytest.skip("RAPyDo proxy templates are not mounted in this container")
    import re

    for name in (
        "production.conf",
        "development.conf",
        "aliases.conf",
        "maintenance.conf",
    ):
        text = (templates / name).read_text()
        (tmp_path / name).write_text(text)
    maintenance.guard_templates(tmp_path)
    for template in tmp_path.glob("*.conf"):
        text = template.read_text()
        assert text.count(maintenance.GUARD) == len(
            re.findall(r"(?m)^\s*server\s*\{", text)
        )


def test_reload_only_on_change_and_rolls_back_failed_validation(tmp_path):
    path = tmp_path / "gate.preconf"
    assert maintenance.sync_configuration(path, "normal", reload=False)
    with patch.object(maintenance.subprocess, "run") as run:
        assert maintenance.sync_configuration(path, "normal", reload=True)
        run.assert_not_called()
        assert maintenance.sync_configuration(path, "maintenance", reload=True)
        assert [call.args[0] for call in run.call_args_list] == [
            ["nginx", "-t"],
            ["nginx", "-s", "reload"],
        ]
    error = subprocess.CalledProcessError(1, "nginx", stderr=b"invalid config")
    with patch.object(maintenance.subprocess, "run", side_effect=error) as run:
        assert not maintenance.sync_configuration(path, "broken", reload=True)
        run.assert_called_once()
    assert path.read_text() == "maintenance"
