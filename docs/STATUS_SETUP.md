# System Status Setup and Operations

This guide covers the persisted maintenance/incident status exposed at `GET /api/service/status`. It is different from `GET /api/status`, which only checks whether the API process is alive.

## How it works

```text
Host: ${DATA_DIR}/status/status.json
        │ mounted into backend and Celery containers
        ▼
Container: /var/lib/meteohub/status.json
        │ read by
        ▼
GET /api/service/status
```

The default path is configured by `STATUS_FILE_PATH` in `projects/maps/project_configuration.yaml`; the host directory is configured by `HOST_STATUS_DIR`. The status endpoint reads the JSON file. It does not offer a `POST` update operation.

## Initialize the status directory

The setup script creates `data/status/status.json` with an initial `operational` status if it does not exist:

```bash
bash scripts/setup_status_dir.sh
```

The configured volume mounts are in `projects/maps/confs/commons.yml`. The host directory is mounted to `/var/lib/meteohub` in both backend and Celery containers. Normally, keep `STATUS_FILE_PATH` at `/var/lib/meteohub/status.json` so it points to the mounted file.

## Change system status

Run these commands on the host from the project environment:

```bash
# Enable maintenance (optional message)
rapydo shell backend 'python scripts/toggle_maintenance.py on "Database upgrade"'

# Return to operational when finished
rapydo shell backend 'python scripts/toggle_maintenance.py off'

# Display the saved status in the terminal
rapydo shell backend 'python scripts/toggle_maintenance.py status'
```

For a detailed update with a chosen status, message, schedule, and affected services, use the interactive script:

```bash
rapydo shell backend 'python scripts/set_status.py'
```

It supports `operational`, `maintenance`, `degraded`, and `outage`. The script writes the status file; check the API response afterward:

```bash
curl http://localhost:8080/api/service/status
```

## Status file format

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

Use ISO 8601 timestamps for `scheduled_start` and `scheduled_end`; UTC (`Z`) is recommended. `affected_services` is a list such as `["maps", "windy"]`. For direct file edits, preserve valid JSON and the field names shown above.

| Status | Meaning |
| --- | --- |
| `operational` | Normal service |
| `maintenance` | Planned maintenance |
| `degraded` | Partial service issue |
| `outage` | Service unavailable |

## Configuration and troubleshooting

| Setting | Default | Purpose |
| --- | --- | --- |
| `STATUS_FILE_PATH` | `/var/lib/meteohub/status.json` | Status file path inside the containers |
| `HOST_STATUS_DIR` | `${DATA_DIR}/status` | Host directory mounted for status persistence |

If an update is not reflected, confirm the file was written and the volume is mounted:

```bash
rapydo shell backend 'ls -l /var/lib/meteohub/status.json'
rapydo shell backend 'cat /var/lib/meteohub/status.json'
curl http://localhost:8080/api/service/status
```

If the API returns `operational` while a status file is present, validate that the file contains valid JSON. The endpoint falls back to the default status when it cannot parse the file.

## Testing

Run the endpoint tests in the backend container:

```bash
rapydo shell backend 'pytest projects/maps/backend/tests/custom/test_api_status.py -v'
```

See [STATUS_API.md](STATUS_API.md) for response details and [API.md](API.md) for the broader API reference.
