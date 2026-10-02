"""Runtime ingestion status from the markers written by dataset processing tasks."""

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from restapi.env import Env
from restapi.exceptions import NotFound

from .manifest import DatasetConfig


_DATES = ("%Y%m%d%H%M", "%Y%m%d%H", "%Y%m%d", "%Y%m%dT%H%M%S")
_DATE_LENGTHS = {fmt: len(datetime(2026, 9, 29, 12, 35).strftime(fmt)) for fmt in _DATES}


def _date(value: str) -> Optional[datetime]:
    for fmt in _DATES:
        # strptime accepts a shorter numeric field with longer formats.
        if len(value) != _DATE_LENGTHS[fmt]:
            continue
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


def _fields(marker: Path) -> Dict[str, str]:
    """Read the metadata written into a completed marker (if any)."""
    fields: Dict[str, str] = {}
    for line in marker.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("Processed by GeoServer at "):
            fields["processed"] = line.removeprefix("Processed by GeoServer at ").strip()
        elif ": " in line:
            key, value = line.split(": ", 1)
            fields[key.lower()] = value.strip()
    return fields


def _range(value: str) -> Tuple[Optional[str], Optional[str]]:
    """Ranges in marker names are compact; marker bodies may contain ISO dates."""
    if " to " in value:
        start, end = value.split(" to ", 1)
        return start, end
    if "-" in value and re.fullmatch(r"\d+-\d+", value):
        start, end = value.split("-", 1)
        first, last = _date(start), _date(end)
        if first and last:
            return first.isoformat(), last.isoformat()
    return None, None


def _coverage_key(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.rstrip("Z"))
    except ValueError:
        return None


def _identifier(marker: Path, suffix: str) -> str:
    return marker.name[: -len(suffix)]


def _run(identifier: str, fields: Dict[str, str]) -> str:
    # Range endpoints describe coverage, not the forecast reference time.
    return (fields.get("run") or fields.get("data") or fields.get("seasonal data") or identifier.split("-", 1)[0].split(".", 1)[0])


def _run_key(identifier: str, fields: Dict[str, str]) -> Tuple[datetime, str]:
    run = _run(identifier, fields)
    # For range markers, the end of coverage identifies the newest chunk.
    end = _range(fields.get("time range") or fields.get("range") or identifier)[1]
    coverage = _coverage_key(end)
    return coverage or _date(run) or datetime.min, run


def _markers(path: Path, suffix: str) -> List[Path]:
    if not path.is_dir():
        return []
    return [p for p in path.iterdir() if p.is_file() and p.name.endswith(suffix)]


def _latest(markers: List[Path], suffix: str) -> Optional[Path]:
    return (
        max(
            markers,
            key=lambda p: (
                _run_key(_identifier(p, suffix), _fields(p)),
                p.stat().st_mtime,
            ),
        )
        if markers
        else None
    )


def _timestamp(marker: Path, fields: Dict[str, str]) -> str:
    return fields.get("processed") or datetime.fromtimestamp(marker.stat().st_mtime, timezone.utc).isoformat()


def _context_paths(config: DatasetConfig, params: Dict[str, str]) -> List[Path]:
    discovery = config.discovery
    env_name = discovery.get("base_path_env")
    base = Path(Env.get(env_name, discovery["base_path_default"]) if env_name else discovery["base_path_default"])

    if discovery.get("folder_pattern"):
        return [base / discovery["folder_pattern"].format(run=run) / discovery["area"] for run in discovery.get("runs", [])]
    if discovery.get("path_suffix"):
        base = base / discovery["path_suffix"]
    if "radar_type" in params:
        radar_type = params["radar_type"]
        if radar_type not in discovery.get("variables", []):
            raise NotFound(f"Invalid radar type: {radar_type}")
        base = base / radar_type
    return [base]


def _status_for_paths(paths: List[Path], suffixes: Dict[str, str]) -> Dict[str, Any]:
    completed_suffix = suffixes.get("completed_suffix", ".GEOSERVER.READY")
    checked_suffix = suffixes.get("checked_suffix", ".CELERY.CHECKED")
    ready_suffix = suffixes.get("ready_suffix", ".READY")
    completed = _latest([m for path in paths for m in _markers(path, completed_suffix)], completed_suffix)
    checked = _latest([m for path in paths for m in _markers(path, checked_suffix)], checked_suffix)
    # A raw READY marker means data was delivered but not yet ingested. Never
    # confuse it with the longer GEOSERVER.READY suffix.
    raw_ready = _latest(
        [m for path in paths for m in _markers(path, ready_suffix) if not m.name.endswith(completed_suffix)],
        ready_suffix,
    )
    result: Dict[str, Any] = {
        "status": "unknown",
        "lastRun": None,
        "lastUpdate": None,
        "from": None,
        "to": None,
        "interval": None,
        "pendingImport": None,
    }

    completed_key = None
    if completed:
        name = _identifier(completed, completed_suffix)
        fields = _fields(completed)
        completed_key = _run_key(name, fields)
        start, end = _range(fields.get("time range") or fields.get("range") or name)
        result.update(status="ready", lastRun=fields.get("run") or (end if end else _run(name, fields)), lastUpdate=_timestamp(completed, fields), **{"from": start, "to": end})

    # A checked marker is still pending only if it represents a newer run or
    # coverage range. Historical checked markers must not mask a completed run.
    pending = checked or raw_ready
    pending_suffix = checked_suffix if checked else ready_suffix
    if raw_ready and checked:
        if _run_key(_identifier(raw_ready, ready_suffix), _fields(raw_ready)) > _run_key(_identifier(checked, checked_suffix), _fields(checked)):
            pending, pending_suffix = raw_ready, ready_suffix
    if pending:
        name = _identifier(pending, pending_suffix)
        fields = _fields(pending)
        pending_key = _run_key(name, fields)
        pending_from, pending_to = _range(fields.get("range") or name)
        # A range can share the same run as a completed marker but extend it.
        covered = completed_key is not None and pending_key <= completed_key
        if completed:
            pending_end = _coverage_key(pending_to) or _date(_run(name, fields))
            completed_end = _coverage_key(result["to"]) or _date(result["lastRun"])
            if pending_end and completed_end:
                covered = pending_end <= completed_end
        if not covered:
            result["pendingImport"] = {
                "status": "pending",
                "run": _run(name, fields),
                "from": pending_from,
                "to": pending_to,
                "detectedAt": _timestamp(pending, {}),
            }
            if not completed:
                result["status"] = "pending"

    return result


def ingestion_status(config: DatasetConfig, params: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Return the same core fields for every dataset, with useful dataset details."""
    params = params or {}
    discovery = config.discovery
    paths = _context_paths(config, params)
    suffixes = discovery.get("markers", {})

    if discovery.get("forcings_env") or discovery.get("forcings"):
        env_name = discovery.get("forcings_env")
        names = Env.get(env_name, "BOLAM,ECMWF,ICON") if env_name else discovery["forcings"]
        forcings = [name.strip() for name in names.split(",") if name.strip()] if isinstance(names, str) else names
        per_forcing = {name: _status_for_paths([paths[0] / name], suffixes) for name in forcings}
        ready = {name: info["lastRun"] for name, info in per_forcing.items() if info["lastRun"]}
        status = _status_for_paths([paths[0] / name for name in forcings], suffixes)
        if ready:
            latest = max(ready.values(), key=lambda value: _date(value) or datetime.min)
            status["availableForcings"] = sorted(name for name, run in ready.items() if run == latest)
        else:
            status["availableForcings"] = []
        status["forcings"] = per_forcing
        return status

    status = _status_for_paths(paths, suffixes)
    if config.identifier == "radar":
        status["interval"] = "5m"
    if config.identifier == "ww3" and status["lastRun"] and status["from"] and status["to"]:
        run = _date(status["lastRun"])
        start = datetime.fromisoformat(status["from"])
        end = datetime.fromisoformat(status["to"])
        if run:
            status["start_offset"] = int((start - run).total_seconds() / 3600)
            status["end_offset"] = int((end - run).total_seconds() / 3600)
            status["step"] = 1
    return status
