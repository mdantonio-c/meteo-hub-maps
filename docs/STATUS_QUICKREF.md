# System Status Quick Reference

## Routes

```bash
# Maintenance / incident status (JSON)
curl http://localhost:8080/api/service/status

# API liveness check (plain text: "Server is alive")
curl http://localhost:8080/api/status
```

`GET /api/service/status` is read-only. There is no status-update POST endpoint. Update the shared status file with the operator scripts:

```bash
# Maintenance mode
rapydo shell backend 'python scripts/toggle_maintenance.py on "Maintenance message"'

# Return to normal service
rapydo shell backend 'python scripts/toggle_maintenance.py off'

# Read status in the terminal
rapydo shell backend 'python scripts/toggle_maintenance.py status'

# Full status editor (all status values, schedule, affected services)
rapydo shell backend 'python scripts/set_status.py'
```

## Status values and data

- `operational` — normal service
- `maintenance` — planned maintenance
- `degraded` — partial issue
- `outage` — service unavailable

The JSON response includes `status`, `message`, `scheduled_start`, `scheduled_end`, `affected_services`, and `updated_at`.

## Implementation and persistence

- Endpoint: `projects/maps/backend/endpoints/status.py`
- Management scripts: `scripts/toggle_maintenance.py`, `scripts/set_status.py`
- Container file: `/var/lib/meteohub/status.json` (`STATUS_FILE_PATH`)
- Host directory: `${DATA_DIR}/status` (`HOST_STATUS_DIR`)
- Volume mounts: `projects/maps/confs/commons.yml` (backend and Celery)
- Initialize directory: `bash scripts/setup_status_dir.sh`
- Tests: `rapydo shell backend 'pytest projects/maps/backend/tests/custom/test_api_status.py -v'`

See [STATUS_API.md](STATUS_API.md) for endpoint behavior and [STATUS_SETUP.md](STATUS_SETUP.md) for setup and troubleshooting.
