# System Status API

MeteoHub exposes two distinct status routes. Use the system status route for operator-set maintenance and incident information; use the health route only to check whether the API process is responding.

## System status and maintenance

### `GET /api/service/status`

Returns the contents of the persisted system status file as JSON. If the file is missing or invalid, the endpoint returns the default `operational` status. This endpoint is read-only: there is currently no `POST` route for changing status.

Example response:

```json
{
  "status": "maintenance",
  "message": "Scheduled database upgrade",
  "scheduled_start": "2026-09-30T02:00:00Z",
  "scheduled_end": "2026-09-30T06:00:00Z",
  "affected_services": ["maps", "windy"],
  "updated_at": "2026-09-29T10:00:00Z"
}
```

Response fields:

- `status`: `operational`, `maintenance`, `degraded`, or `outage`.
- `message`: Human-readable status detail, or `null`.
- `scheduled_start`, `scheduled_end`: Optional ISO 8601 timestamps (UTC recommended).
- `affected_services`: Array of affected service names, or an empty array.
- `updated_at`: Timestamp when the status file was last updated.

### Update the status

Update status from the backend container using the included scripts. For a quick maintenance toggle:

```bash
# Set maintenance mode (optional message)
rapydo shell backend 'python scripts/toggle_maintenance.py on "Database upgrade"'

# Return to operational
rapydo shell backend 'python scripts/toggle_maintenance.py off'

# Display current status in the terminal
rapydo shell backend 'python scripts/toggle_maintenance.py status'
```

For a complete status entry, including scheduled times and affected services, run the interactive editor:

```bash
rapydo shell backend 'python scripts/set_status.py'
```

The interactive editor supports all four status values. After writing a change, read the public status response to verify it:

```bash
curl http://localhost:8080/api/service/status
```

## API liveness check

### `GET /api/status`

This is a separate health check. It returns the plain-text response `Server is alive` when the API is running. It does not return system maintenance information.

## Persistence and configuration

The backend reads `/var/lib/meteohub/status.json` by default. `STATUS_FILE_PATH` can override this in-container file path. The default volume maps the host directory `${DATA_DIR}/status` to `/var/lib/meteohub` in the backend and Celery containers, so changes persist across container restarts. See [STATUS_SETUP.md](STATUS_SETUP.md) for volume configuration and troubleshooting.

Example status file:

```json
{
  "status": "operational",
  "message": null,
  "scheduled_start": null,
  "scheduled_end": null,
  "affected_services": [],
  "updated_at": "2026-09-29T10:00:00Z"
}
```

## Related documentation and code

- [API reference](API.md)
- [Setup and operations](STATUS_SETUP.md)
- Endpoint implementation: `projects/maps/backend/endpoints/status.py`
- Status management scripts: `scripts/toggle_maintenance.py`, `scripts/set_status.py`
- Endpoint tests: `projects/maps/backend/tests/custom/test_api_status.py`
