# Status Management Scripts

Use these host-side utilities to publish MeteoHub Maps maintenance and incident
status. See the [detailed script reference](../docs/SCRIPTS.md) for every script
in this directory and `projects/maps/backend/scripts/`, including prerequisites,
defaults, side effects, and current limitations.

## Prepare the Default Directory

Run from the repository root on the host:

```bash
bash scripts/setup_status_dir.sh
```

This prepares `data/status/`, sets its directory permissions to `755`, and
creates an operational `status.json` only if the file does not already exist.

## Quick Toggle

```bash
# Enable maintenance, optionally with a quoted message.
python3 scripts/toggle_maintenance.py on "Database upgrade in progress"

# Inspect the saved status.
python3 scripts/toggle_maintenance.py status

# Restore operational status and clear incident details.
python3 scripts/toggle_maintenance.py off
```

The `on` command publishes maintenance immediately, affecting all services. Its
current two-hour end-time calculation fails at UTC hours 22 and 23; use the
interactive script during those hours. The saved end time does not automatically
disable maintenance.

## Interactive Configuration

```bash
python3 scripts/set_status.py
```

Choose `operational`, `maintenance`, `degraded`, or `outage`, then enter the
message, applicable start/end times, affected services, and write confirmation.
Use this script for an outage: the quick `on` command always writes maintenance,
regardless of its message.

## Select the Correct File

Outside RAPyDo, both Python scripts default to the repository's
`data/status/status.json`. The configured host volume is `HOST_STATUS_DIR`
(default `${DATA_DIR}/status`), mounted into containers at `/var/lib/meteohub`.
The current Compose configuration does not mount the root `scripts/` directory.

If your host status volume uses another location, select it explicitly:

```bash
STATUS_FILE_PATH=/srv/meteohub/status/status.json python3 scripts/set_status.py
STATUS_FILE_PATH=/srv/meteohub/status/status.json python3 scripts/toggle_maintenance.py status
```

Replace the example path with the actual host volume path. Both write commands
replace the complete JSON document and need write permission on that file.

## Verify Through the API

```bash
curl http://localhost:8080/api/service/status
```

This endpoint reads operator-managed status; it does not accept status-update
POST requests. `GET /api/status` is the separate API liveness check.

With the file-driven Docker nginx gate, maintenance status returns HTTP 503 to
non-allowlisted clients except on the two status routes. Future schedule times
do not delay the gate, and `degraded`/`outage` do not activate it. See
[status setup](../docs/STATUS_SETUP.md) for allowlists, forced gate settings, and
volume configuration.
