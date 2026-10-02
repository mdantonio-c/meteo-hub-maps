# Script Reference and Operator Guide

This guide describes every executable source script in [`scripts/`](../scripts/)
and [`projects/maps/backend/scripts/`](../projects/maps/backend/scripts/): why it
exists, how to run it, what it changes, and how to check the result.

## Choose a Script

| Script | Use it when you need to… | Main effect |
| --- | --- | --- |
| [`setup_status_dir.sh`](#setup_status_dirsh) | Prepare the default host status volume | Creates `data/status/` and an initial status file |
| [`set_status.py`](#set_statuspy) | Describe maintenance, degraded service, or an outage in detail | Interactively replaces the shared status JSON |
| [`toggle_maintenance.py`](#toggle_maintenancepy) | Quickly enable maintenance, restore normal status, or inspect the saved status | Writes or reads the shared status JSON |
| [`refresh_cache.py`](#refresh_cachepy) | Rebuild cached tiles for an existing temporal raster layer | Cancels layer jobs, configures GWC, truncates selected tiles, and seeds replacements |
| [`init.sh`](#initsh) | Start or reset automated dataset discovery | Posts to the monitoring API, which schedules Celery work |
| [`init-thredds-catalog.sh`](#init-thredds-catalogsh) | Understand the retained THREDDS initialization hook | Disabled; running it has no effect |

`scripts/README_STATUS.md` is a [status quick guide](../scripts/README_STATUS.md).
`__pycache__/` files are generated Python bytecode, not operator scripts.

## Paths and Execution Environments

Unless a command is explicitly labelled otherwise, run it **on the host from the
repository root**. Python examples use `python3`; shell examples use `bash`, so
the scripts do not need executable permissions.

| Location | Meaning |
| --- | --- |
| `scripts/` | Host-side status utilities in this repository |
| `projects/maps/backend/scripts/` | Repository source of the backend scripts |
| `/code/maps/scripts/` | Backend script directory in the currently generated RAPyDo Compose configuration (`backend/` is mounted as `/code/maps`) |
| `/proj/maps/backend/scripts/` | If your deployment exposes the backend here, use this path instead of `/code/maps/scripts/`; it is not a second source directory in this checkout |

The root `scripts/` directory is not mounted by the current Compose configuration.
Run its status utilities on the host, pointing them at the host status volume.
For backend utilities, `rapydo shell backend 'COMMAND'` runs a command in the
container with its installed application dependencies and service network.

### Shared Status File

Both status Python scripts resolve their output path in this order:

1. `Env.get("STATUS_FILE_PATH", None)` when the RAPyDo `restapi` package is
   importable; otherwise the process's `STATUS_FILE_PATH` environment variable.
2. If no value is configured, `<repository>/data/status/status.json`, resolved
   from the script location rather than the current working directory.

The deployment settings are:

| Setting | Default | Role |
| --- | --- | --- |
| `HOST_STATUS_DIR` | `${DATA_DIR}/status` | Host directory mounted into backend, Celery, and nginx containers |
| `STATUS_FILE_PATH` | `/var/lib/meteohub/status.json` | Path **inside containers** to the mounted JSON file |

With the usual repository-local `data/` directory, the host fallback and mounted
file are the same file. If `DATA_DIR` or `HOST_STATUS_DIR` is customized, explicitly
select the actual **host** file when running a status script:

```bash
STATUS_FILE_PATH=/srv/meteohub/status/status.json python3 scripts/set_status.py
STATUS_FILE_PATH=/srv/meteohub/status/status.json python3 scripts/toggle_maintenance.py status
```

Replace `/srv/meteohub/status/status.json` with your deployment's host path. An
exported in-container path such as `/var/lib/meteohub/status.json` does not
automatically point to that volume on the host. The scripts need Python 3 and
write permission for the selected directory/file; outside RAPyDo they use only
the Python standard library.

### What a Status Change Means

The scripts publish operator-managed status, read through
`GET /api/service/status`. `GET /api/status` is a separate liveness check.
There is no active status-update POST endpoint.

In the Docker-managed nginx proxy, `status: maintenance` also activates the
maintenance access gate. Non-allowlisted clients receive HTTP 503, except for
`/api/status` and `/api/service/status`. The proxy checks the file every second
and validates/reloads nginx when the gate changes. `MAINTENANCE_ALLOWLIST`
defines permitted client IPs/CIDRs; `MAINTENANCE_MODE=1` or `0` overrides the
file-driven gate. See [status setup](STATUS_SETUP.md#docker-nginx-maintenance-allowlist).

The gate uses the **status string**, not `scheduled_start`, `scheduled_end`, or
`affected_services`. Publishing maintenance with a future start activates it
immediately, and reaching the end time does not restore operational status.
`degraded` and `outage` publish incident information without activating this
maintenance gate. Status updates do not stop containers or Celery monitoring.

## Host Scripts

### `setup_status_dir.sh`

**Source:** [`scripts/setup_status_dir.sh`](../scripts/setup_status_dir.sh)

**Purpose and why:** Prepare the default persistent status directory before
Docker mounts it, and supply a valid initial JSON document for status consumers.

**Usage — host:**

```bash
bash scripts/setup_status_dir.sh
```

There are no arguments or configuration flags. The script derives the repository
root from its own location and always targets `<repository>/data/status`, even
when `HOST_STATUS_DIR`, `DATA_DIR`, or `STATUS_FILE_PATH` are set differently.

**What it does:**

1. Creates `data/status/` and missing parents if necessary.
2. Sets that directory's permissions to `755` on every run (owner can write;
   group and other users can read and traverse it).
3. If `status.json` is absent, creates it with `status: operational`, null
   message/times/`updated_at`, and an empty `affected_services` array.
4. Preserves an existing file and prints the directory and suggested Docker mount
   to `/var/lib/meteohub`.

It does not change ownership, set an existing file's permissions, validate an
existing JSON document, or configure/start Docker. A newly created file inherits
permissions from the process umask. Re-running preserves the current status but
reapplies directory mode `755`. Bash `set -e` stops execution if a command fails.

**Check the result:**

```bash
python3 scripts/toggle_maintenance.py status
```

Use the explicit host-path override described above if the deployment uses a
different volume location; this setup script only prepares the default location.

### `set_status.py`

**Source:** [`scripts/set_status.py`](../scripts/set_status.py)

**Purpose and why:** Publish an informational message, detailed maintenance
notice, or incident report without manually constructing JSON. Use it when you
need a specific status, message, time window, or affected-service list.

**Usage — host, interactive terminal:**

```bash
python3 scripts/set_status.py
```

The script has no command-line options. Configuration is through
`STATUS_FILE_PATH` and terminal prompts.

**Prompt sequence and defaults:**

| Prompt | Behavior when Enter is pressed |
| --- | --- |
| Status (`1`–`4`) | `1`: operational; the other choices are maintenance, degraded, and outage |
| Message | Operational: null; maintenance: `Scheduled maintenance window`; degraded: `System experiencing issues`; outage: `System unavailable` |
| Maintenance start/end | UTC now +1 hour / now +3 hours |
| Degraded/outage issue start and expected resolution | UTC now −1 hour / now +2 hours; saved as `scheduled_start` / `scheduled_end` |
| Affected services | Empty list; otherwise comma-separated entries, with whitespace and empty entries removed |
| Write confirmation | Yes; `y` or `yes` also writes, and other responses cancel |

Operational status skips the time prompts and stores null times. Service names
are free-form strings, such as `maps, radar, windy`, rather than a validated list.
You can attach a message to `operational` to inform users while the service is
running normally, for example to announce a scheduled update. Choose `1`, enter
a message such as `A scheduled update is planned for 2026-10-03 at 02:00 UTC`,
leave affected services empty if appropriate, and confirm. Include any planned
date and time in the message, since operational status does not prompt for them.
Time inputs should be ISO 8601, preferably UTC such as `2026-10-02T14:00:00Z`.
The current implementation warns about an invalid datetime but **still saves the
entered value**. It does not verify that the end follows the start. For non-
operational statuses, leaving a time prompt blank accepts its proposed default.

**What it changes:** After showing a summary and receiving confirmation, it
creates missing parent directories and replaces the entire selected file with
indented JSON containing:

```json
{
  "status": "degraded",
  "message": "Radar updates delayed",
  "scheduled_start": "2026-10-02T13:00:00Z",
  "scheduled_end": "2026-10-02T16:00:00Z",
  "affected_services": ["radar"],
  "updated_at": "2026-10-02T14:00:00Z"
}
```

`updated_at` is generated in UTC when the status document is built. Existing
fields are not merged or backed up. A confirmed write prints the target path and
status; cancellation or Ctrl+C exits with code `0`, and caught errors exit with
code `1`. Writes use a direct file overwrite rather than an atomic rename.

**Example:** To report a radar delay, choose `3` (degraded), enter the message,
review/enter the issue and resolution times, enter `radar`, and confirm. For
planned maintenance, choose `2`, bearing in mind that the proxy gate activates
as soon as that status is written.

**Verify what clients see:**

```bash
python3 scripts/toggle_maintenance.py status
curl http://localhost:8080/api/service/status
```

### `toggle_maintenance.py`

**Source:** [`scripts/toggle_maintenance.py`](../scripts/toggle_maintenance.py)

**Purpose and why:** Provide a short, non-interactive command for routine
maintenance transitions and a terminal view of the saved status. Detailed
incident configuration belongs in `set_status.py`.

**Usage — host:**

```bash
python3 scripts/toggle_maintenance.py on
python3 scripts/toggle_maintenance.py on "Database upgrade in progress"
python3 scripts/toggle_maintenance.py status
python3 scripts/toggle_maintenance.py off
python3 scripts/toggle_maintenance.py help
```

| Command | What it does |
| --- | --- |
| `on [message]` | Replaces the file with maintenance status, default message `Scheduled maintenance`, start now in UTC, intended end two hours later, affected services `["all"]`, and a fresh `updated_at` |
| `off` | Replaces the file with operational status, null message/start/end, an empty service list, and a fresh `updated_at` |
| `status` | Reads the file and prints its status and populated optional fields; if absent, displays operational without creating a file |
| `help` | Prints the script's usage text |

The command name is case-insensitive. Quote a multi-word message: only the first
argument after `on` is used as the message. Missing or unknown commands exit with
code `1`; successful commands exit with code `0`. Malformed JSON or file-access
errors are printed and cause exit code `1`.

Both write commands create missing parent directories, overwrite the whole file
without confirmation, and discard the previous incident details. Writes are
direct overwrites with no backup. `status` reports saved operator state rather
than probing services or checking whether the proxy gate is forced on/off.

**Current time-calculation limitation:** `on` uses
`now.replace(hour=now.hour + 2)` instead of adding a duration. At UTC hours `22`
or `23`, it raises `hour must be in 0..23` and exits before writing. Use
`set_status.py` to publish maintenance during those hours. The proposed end is
informational; explicitly run `off` when maintenance finishes.

**Typical workflow:** Set maintenance before work, inspect
`/api/service/status`, perform the work, then run `off` and inspect the endpoint
again. Use `set_status.py` to publish an actual `outage`; an `on` command with an
outage message still saves `status: maintenance`.

## Backend Scripts

### `refresh_cache.py`

**Source:** [`projects/maps/backend/scripts/refresh_cache.py`](../projects/maps/backend/scripts/refresh_cache.py)

**Purpose and why:** Rebuild GeoWebCache tiles for a published temporal raster
layer after a style change, stale-cache incident, or cache configuration repair.
It provides the manual refresh path without requiring a new data-ingestion run.

**Requirements:** Python 3, `requests`, PyYAML, and the adjacent backend package;
a readable dataset manifest; reachable GeoServer/GWC REST APIs; and GeoServer
credentials with configuration and seed permissions. The backend container
already provides the application environment. The layer and its coverage store
must already exist. Automatic time discovery uses the ImageMosaic granule index.

**Usage — from the host, executing inside the backend container:**

```bash
# Inspect all options without contacting GeoServer.
rapydo shell backend 'python3 /code/maps/scripts/refresh_cache.py --help'

# Refresh every indexed radar SRI time using four parallel timestep jobs.
rapydo shell backend 'python3 /code/maps/scripts/refresh_cache.py --dataset radar --variable sri --parallelism 4'

# Refresh one explicitly selected time for a published layer.
rapydo shell backend 'python3 /code/maps/scripts/refresh_cache.py --dataset radar --layer radar-srt --times 2026-10-02T10:00:00Z'

# Resolve a layer from its actual coverage store.
rapydo shell backend 'python3 /code/maps/scripts/refresh_cache.py --dataset radar --store radar-sri'

# Leave only the final seed batch running after submission.
rapydo shell backend 'python3 /code/maps/scripts/refresh_cache.py --dataset radar --variable sri --times 2026-10-02T10:00:00Z 2026-10-02T10:05:00Z --no-wait'
```

If your container uses `/proj/maps/backend/scripts`, substitute that prefix.
For direct host execution with the Python dependencies installed, use the source
path and configure a host-reachable GeoServer URL and credentials:

```bash
export GEOSERVER_URL=http://localhost:8080/geoserver
export GEOSERVER_ADMIN_USER=admin
# Set GEOSERVER_ADMIN_PASSWORD to the deployment's configured credential.
python3 projects/maps/backend/scripts/refresh_cache.py --dataset radar --variable sri
```

The script reads its settings from the process environment; it does not load
`.env` or `.projectrc` itself.

**Command-line options:**

| Option | Default / interpretation |
| --- | --- |
| `--dataset ID` | `radar`; selects the manifest entry providing workspace, variable mapping, cache eligibility, and zooms. Required context even with `--layer` or `--store` |
| `--variable NAME` | Looks up `geoserver.variables.NAME.layer_name` in the selected dataset |
| `--layer NAME` | Published layer name **without** workspace prefix; takes precedence over `--variable` |
| `--store NAME` | Actual coverage-store name. Alone, resolves its single coverage; if the store lookup returns 404, tries the name as a published layer. With a layer/variable, verifies that it belongs to this store |
| `--times VALUE [VALUE ...]` | Explicit ISO 8601 WMS TIME values. If omitted, uses all unique, sorted times returned by the current granule index |
| `--parallelism N` | `4`; maximum timestep seed jobs per batch, each using one GWC thread. Must be at least `1` |
| `--no-wait` | Skips waiting for the final seed batch only; cancellation, truncation, and earlier seed batches still wait |
| `-h`, `--help` | Displays usage and exits |

A bare invocation fails because it has no variable, layer, or store to select.
An unknown dataset or missing variable mapping also fails. A store with zero or
multiple coverages needs an explicit `--layer`; a vector-backed layer cannot be
resolved as a coverage store. Explicit times are passed through rather than
validated against available granules.

**What it does, in order:**

1. Loads and validates the manifest, chooses the dataset, and resolves the actual
   layer/store relationship from GeoServer REST metadata.
2. Prints the workspace/layer, store, zoom range, server expiry, and parallelism.
3. Cancels existing pending/running GWC jobs for the **whole selected layer** and
   waits for its queue to drain, including when refreshing only one time.
4. Ensures a TIME parameter filter exists, ensures the configured gridset exists,
   sets the layer's grid subsets to that gridset, updates server/client expiry,
   and ensures per-layer/global disk quotas. Quota changes may trigger a
   GeoServer configuration reload.
5. Uses the supplied times or retrieves all indexed granule times, then resolves
   the layer's current default style.
6. Truncates each selected TIME/default-style cache combination serially and
   waits for each truncation to finish.
7. Submits replacement tile-generation jobs in bounded batches and normally
   waits for each batch to drain.
8. Prints `Refresh complete`, or with `--no-wait`, reports submission while the
   final batch may still run.

This removes cached tiles and generates replacements; it does not ingest source
data, republish layers, edit SLD definitions, or create ingestion markers. The
refresh targets the configured zoom range, gridset, image format, and current
default style. It does not purge every historical time/style variant: omitted
`--times` means current indexed times, not all variants remaining on disk.
Automatic time discovery requests `all_times=True`, so `GWC_MAX_TIMES_PER_SEED`
does not cap this script's timestep list.

**Configuration used by the refresh and shared cache adapter:**

| Setting | Fallback / source | Effect |
| --- | --- | --- |
| `DATASET_CONFIG_PATH` | `projects/maps/datasets.yml` relative to the host source tree | Manifest location; use the mounted environment value inside containers |
| `GEOSERVER_URL` | `http://geoserver.dockerized.io:8080/geoserver` | GeoServer base URL |
| `GEOSERVER_ADMIN_USER`, `GEOSERVER_ADMIN_PASSWORD` | Script development defaults | REST authentication; use the deployment's configured credentials |
| Dataset `geoserver.workspace` | `meteohub` | Workspace used to resolve the layer/store |
| Dataset `geoserver.cache.eligible` | `true` when omitted | Explicitly controls this script's cache adapter; it overrides the adapter's global `GEOSERVER_GWC_ENABLED` default |
| Manifest `geoserver.cache.zoom_start`, `zoom_stop` | Shared values, overridden per dataset | Tile zoom range; current shared values are `5`–`8`, radar uses `5`–`9` |
| Dataset `geoserver.cache.expire_seconds` | `GWC_CACHE_EXPIRE_SECONDS`, fallback `86400` | Server cache expiry for a mapped layer; current radar value is `259200` seconds |
| `GWC_CLIENT_EXPIRE_SECONDS` | Adapter fallback `300`; project deployment default `0` | Client cache expiry |
| `GWC_GRID_SET`, `GWC_TILE_SIZE` | `EPSG:900913_1024`, `1024` | Gridset and tile dimensions used when creating a missing gridset |
| `GWC_IMAGE_FORMAT` | `image/png` | Truncate/seed tile format |
| `GWC_LAYER_QUOTA_MIB` | `1024` | Positive per-layer LRU disk quota |
| `GWC_GLOBAL_QUOTA_MIB` | Empty | Automatic quota: per-layer limit × current GWC layer count; positive value overrides it |
| `GEOSERVER_REQUEST_TIMEOUT_SECONDS` | `600` | REST read timeout; connection timeout is `10` seconds |
| `GWC_SEED_WAIT_TIMEOUT`, `GWC_SEED_POLL_INTERVAL` | `1800`, `3` seconds | Queue wait budget per wait operation and polling interval |

The selected dataset supplies the workspace and zoom context even for an explicit
layer name, so select the dataset that owns the layer. With `eligible: false`,
cache mutation helpers become no-ops; automatic granule-time discovery returns
no times. A successful exit with explicit times in that mode is not evidence
that tiles were rebuilt.

**Result and verification:** Progress lines include UTC timestamps and identify
the current truncate/seed batch. Detected REST/configuration/queue failures return
`1`; invalid CLI arguments return argparse's `2`; a completed refresh or accepted
final no-wait batch returns `0`. Some configuration/import failures can produce
a traceback. Queue draining is the completion criterion; no-wait success means
the last batch was accepted, not that every tile is already available.

Inspect the GeoServer GWC seed queue (or its administrative UI) for the selected
layer and request a cached WMS-C image with the same TIME/default style, gridset,
and format. See [GeoWebCache](GWC_CACHE.md) and [radar cache operations](RADAR_DATA.md).
Run manual refreshes during a quiet ingestion interval: this script directly
controls the layer queue and does not acquire the ingestion/cache-controller
locks, so concurrent publication can interfere with the refresh.

### `init.sh`

**Source:** [`projects/maps/backend/scripts/init.sh`](../projects/maps/backend/scripts/init.sh)

**Purpose and why:** A minimal convenience hook for starting automated discovery
after the API and task services are available. Despite its name, it does not
install dependencies, initialize RAPyDo, or start containers.

**Usage — host with the local API listening on port 8080:**

```bash
bash projects/maps/backend/scripts/init.sh
```

Its complete active command is:

```bash
curl -X POST localhost:8080/api/data/monitoring
```

There are no arguments or environment overrides for the URL. `localhost` means
the machine/network namespace where the script is run. Inside a container it
refers to that container, so use this script there only if the API is actually
reachable on its loopback port 8080. For a remote API, issue the corresponding
request directly:

```bash
curl --fail-with-body -X POST https://maps.example.org/api/data/monitoring
```

**Requirements:** Bash, curl, a running API, and working Celery/Redis/scheduler
services. The API checks the caller against `MAINTENANCE_ALLOWLIST` even during
normal operation; localhost is not inherently exempt. A denied call returns 403.

**What the API does after an authorized request:**

1. Enqueues `initialize_geoserver` on Celery's `ingest` queue. When GWC is enabled,
   that task disables direct WMS integration, ensures cache quotas/gridsets/TIME
   filters, and optionally syncs mounted SLD styles.
2. Deletes the existing manifest-defined discovery schedules and recreates them
   to run **every minute**. Dataset discovery tasks shared by several entries
   are deduplicated; generic `discover_dataset` schedules are dataset-specific.
3. Returns HTTP 202 with `Monitoring started`. Initialization and subsequent
   discovery/ingestion happen asynchronously.

The dataset registry/manifest determines which discovery jobs are scheduled.
Those jobs scan ready data and can enqueue ingestion that changes GeoServer
layers and caches. Re-running this script resets the discovery schedules and
queues another initialization task. The independent hourly cache-maintenance
schedule is not controlled by these start/stop operations.

**Check and stop:** Inspect the HTTP response and `rapydo logs celery` for worker
results. HTTP 202 confirms acceptance, not successful initialization or completed
ingestion. To remove the discovery schedules:

```bash
curl --fail-with-body -X DELETE http://localhost:8080/api/data/monitoring
```

Stopping monitoring does not cancel already queued/running ingestion. The script
itself has no `curl --fail` option: HTTP 403 or 500 can still produce shell exit
code `0` if the HTTP exchange succeeded. Check the response, or use the direct
`--fail-with-body` command when an HTTP-aware exit status is needed.

### `init-thredds-catalog.sh`

**Source:** [`projects/maps/backend/scripts/init-thredds-catalog.sh`](../projects/maps/backend/scripts/init-thredds-catalog.sh)

**Purpose and why:** Preserve the former THREDDS initialization hook's location
and explain its disabled state. The file is retained for project history and
possible rollback while THREDDS integration is disabled.

**Usage — optional, host:**

```bash
bash projects/maps/backend/scripts/init-thredds-catalog.sh
```

The file contains only a shebang and comments. It accepts no meaningful options,
prints nothing, performs no filesystem or network operations, and normally exits
`0`. It does not generate a catalog or enable THREDDS. Restoring that integration
requires implementing the hook and restoring the related service configuration;
simply executing this file cannot initialize it.
