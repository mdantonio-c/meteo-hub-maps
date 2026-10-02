# System Status Setup and Operations

This guide covers the persisted maintenance/incident status exposed at `GET /api/service/status`. It is different from `GET /api/status`, which only checks whether the API process is alive.

## Docker Nginx Maintenance Allowlist

The Docker-managed `proxy` nginx enforces maintenance access
when `status.json` contains `"status": "maintenance"`. Only clients in
`MAINTENANCE_ALLOWLIST` pass through; others receive HTTP **503** before the
request reaches the API or a location handler. An empty allowlist blocks all
clients during maintenance except for **`/api/status`** and
**`/api/service/status`**, which remain publicly accessible for health and
maintenance checks (including requests with query parameters). Normal operation
is unrestricted by this gate.

Configure deployment environment overrides in `.projectrc`:

```yaml
project_configuration:
  variables:
    env:
      MAINTENANCE_ALLOWLIST: "192.0.2.10, 198.51.100.0/24, 2001:db8::10"
      MAINTENANCE_TRUSTED_PROXIES: ""
      MAINTENANCE_MODE: ""
```

- `MAINTENANCE_ALLOWLIST`: comma/space-separated IPv4, IPv6 or CIDR entries.
  Invalid entries prevent proxy startup. The backend uses the same allowlist to
  guard `POST` and `DELETE /api/data/monitoring` and `/api/maps/sensitive`, even
  during normal operation. Empty or invalid allowlists deny these API requests
  with HTTP **403**.
  API checks use RAPyDo's client-IP resolver (`X-Real-IP`, or `X-Forwarded-For`
  when `PROXIED_CONNECTION` is enabled), falling back to the connection address.
  Backend access should pass through the configured proxy, which supplies these headers.
- `MAINTENANCE_TRUSTED_PROXIES`: IPs/CIDRs of reverse proxies that may supply
  `X-Forwarded-For`. Leave empty for direct connections. Behind a host nginx,
  set this to its actual source address as seen by Docker nginx and ensure that
  host nginx forwards the client address. Untrusted forwarded headers cannot
  bypass the allowlist.
- `MAINTENANCE_MODE`: empty follows the shared status file; `1` forces the gate
  on, `0` forces it off. The standalone RAPyDo `maintenance` container always
  forces maintenance and applies the same allowlist to its maintenance page.

Regenerate RAPyDo configuration using your usual deployment profile, then
recreate the `proxy` and `backend` containers after changing environment values. The status
directory is mounted read-only into nginx. Status-file changes made by either
status script are checked every second and trigger a validated nginx reload;
no container restart is needed to toggle the status. Missing or malformed
updates retain the last applied state (a first startup without a status file
starts operational).

Test from an allowlisted address and from another address after enabling
maintenance. Also check that sending a forged `X-Forwarded-For` from an
untrusted peer still returns 503. During maintenance the nginx container's
health probe needs an explicitly allowlisted loopback address if it should pass.
The tracked host nginx templates route `/api`, `/wms`, `/wms/cache` and
`/geoserver/` through Docker nginx, including preflight requests. Install the
updated host template and reload host nginx when deploying this routing change.
Independently exposed service ports and host-served static routes use their own
routing/access rules.

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
