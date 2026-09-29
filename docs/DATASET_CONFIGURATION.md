# Dataset manifest configuration

Dataset definitions live in `projects/maps/datasets.yml`. The backend and Celery containers mount this file read-only at `DATASET_CONFIG_PATH` (currently `/etc/meteohub/datasets.yml`). The code loads and validates the YAML manifest when it builds the dataset registry; edit the project-side YAML and restart/redeploy the affected services to load changes.

This manifest describes dataset discovery, ingestion adapter selection, temporal parsing, GeoServer publication/cache settings, and REST endpoint capabilities. It is not a list of individual forecast files or runtime data values.

**Ingestion flow:** monitoring schedules each dataset's `discovery.task`. `ingestion.behaviour` chooses `bulk_override` (replace a run's mosaic) or `fifo_granules` (keep newest timestamped granules under the configured retention limits). The registry selects a dataset-id specialization when available for that behaviour, otherwise the corresponding default implementation. The manifest never names a Python implementation. The discovery task submits `ingestion.task`; publication runs synchronously, then asynchronous cache invalidation writes `.GEOSERVER.READY` only after it succeeds. Warming may continue afterward. Existing task names remain available.

## Top-level structure

```yaml
version: 1

geoserver:                 # Defaults inherited by every dataset
  cache:
    zoom_start: 5
    zoom_stop: 8

datasets:                  # Dataset definitions
  - id: example
    display_name: Example forecast
    kind: forecast
    enabled: true
    discovery: {}
    ingestion: {}
    temporal: {}
    geoserver: {}
    endpoint: {}
```

`version` is currently required to be `1`. `datasets` must be a non-empty list. Each dataset must have an `id`, `kind`, and the five mapping sections shown above. The fields within each section are interpreted by the corresponding adapter and endpoint code; validation checks required structures and several field types, but does not reject every unknown key.

## Dataset fields

### Identity and activation

| Field | Purpose |
| --- | --- |
| `id` | Stable unique identifier used by the dataset registry and dataset API. Lowercase letters, numbers, `_`, and `-` are allowed; it must start with a letter. |
| `display_name` | Human-readable name returned in dataset metadata. If omitted, the identifier is used. |
| `kind` | Broad dataset category such as `forecast`, `observation`, or `marine`. Descriptive metadata for clients. |
| `enabled` | Activation metadata. It is not currently used by the registry to filter datasets, so do not rely on `false` alone to suppress ingestion. |

### `discovery`

Describes where source data is found and how its files/runs are recognized. Typical options include:

| Option | Purpose |
| --- | --- |
| `task` | Optional Celery discovery task. Defaults to `discover_dataset`, which schedules one task per dataset, passing its id. Existing dataset-specific task names remain supported. |
| `base_path_env` | Optional environment variable that overrides the source root. |
| `base_path_default` | Fallback source root inside the container. |
| `path_suffix` | Optional relative folder below the source root for the default behaviour implementations (e.g. `Mediterraneo`). |
| `folder_pattern` | Source folder template; `{run}` and other adapter-defined values are substituted. |
| `area` | Area/subdirectory within a source folder. |
| `runs` | Forecast run identifiers to discover, e.g. `["00", "12"]`. |
| `variables` | Variable names known to the dataset, e.g. radar `[sri, srt]`. |
| `source_files_path` | Relative/path template for variable data under the source root. `{base_path}`, `{variable}`, `{forcing}`, and `{value}` are used only where the adapter supports them. |
| `forcings_env` | Environment variable naming marine forcings. |
| `markers` | READY, debounce/check, and ingestion-complete filename suffixes. |

Default implementations read direct variable folders and parse TIFF timestamps from `temporal.filename_regex` (capture group 1). Specialized datasets can use their own folder and marker conventions.

### `ingestion`

| Option | Purpose |
| --- | --- |
| `behaviour` | Required for ingestion: `bulk_override` replaces a run's mosaic; `fifo_granules` retains timestamped granules using the limits below. The registry selects a dataset-id implementation when registered, otherwise the behaviour's default. |
| `task` | Optional Celery ingestion task. Defaults to `ingest_dataset` (run and dataset id are passed); existing task names can be retained for external callers. |
| `retention.hours` | For `fifo_granules`: retain granules within this many hours of the newest timestamp. |
| `retention.max_granules` | For `fifo_granules`: keep at most this many newest granules per variable. Both limits apply if supplied; at least one is required. |
| `trigger` | Declares the expected trigger, commonly `ready_marker`; adapter/task code determines the actual trigger behavior. |
| `batch_mode` | Describes input grouping, e.g. `run`, `time_range`, `replacement`, or `forcing_variable`. It is currently declarative; adapter/task code implements the behavior. |
| `rolling_window_hours` | Legacy radar metadata; prefer `retention.hours` for new FIFO datasets. |

### `temporal`

Describes how valid time is extracted and interpreted:

| Option | Purpose |
| --- | --- |
| `filename_regex` | Regular expression used to match/extract a timestamp from source filenames. |
| `filename_format` | Timestamp format used by GeoServer's filename time extractor (for example `yyyyMMddHH`). |
| `timezone` | Timezone associated with extracted timestamps; use `UTC` for UTC source data. |

These three fields are required and must be non-empty strings; the regular expression is compiled during validation.

### `geoserver`

| Option | Purpose |
| --- | --- |
| `workspace` | GeoServer workspace where stores and layers are published. |
| `store_type` | GeoServer store type, typically `ImageMosaic`. |
| `sld.style_name` | Default style template, with supported substitutions such as `{variable}`. |
| `variables` | Optional per-variable settings such as `layer_name`, `layer_name_pattern`, and `style_name`. |
| `cache.eligible` | Whether the dataset's adapter should apply cache invalidation. |
| `cache.zoom_start` | Minimum zoom level to truncate/seed in GeoWebCache. |
| `cache.zoom_stop` | Maximum zoom level to truncate/seed in GeoWebCache. |
| `cache.require_explicit_time` | Declares that cache requests should use an explicit time key for temporal data; runtime cache key behavior is implemented in the GWC adapter. |
| `cache.zoom_start` / `cache.zoom_stop` (top-level) | Manifest-wide zoom defaults inherited by datasets unless a dataset overrides the respective key. |

Zoom ranges are integers. The current global policy is `5` through `8`; radar overrides the stop level with `9`. An explicit per-dataset value wins over the top-level default. When calling the cache invalidator without explicit zoom arguments, it reads the manifest-wide defaults, so changing them requires no Python constant update.

Ingestion adapters pass dataset cache zoom ranges through when configured. The manifest-wide defaults are used where a task does not supply an override. Keep the global setting as the intended default for temporal forecast cache refreshes.

### `endpoint`

| Option | Purpose |
| --- | --- |
| `route` | Required route template for the dataset endpoint. It must begin with `/`; path parameters are adapter/endpoint-specific. |
| `operations` | Capabilities advertised for the route, such as `metadata`, `file_download`, `status`, or `stations`. For example, `file_download` is checked by the safe dataset file helper; endpoint implementation determines which operations are actually available. |

## Example: add an ImageMosaic forecast

For a run-based forecast, provide a publication function in `maps.datasets` and configure its READY directory and task names. For example:

```yaml
- id: example-model
  display_name: Example model
  kind: forecast
  enabled: true
  discovery:
    base_path_env: EXAMPLE_DATA_PATH
    base_path_default: /example
    path_suffix: Italia
    markers:
      ready_suffix: .READY
      checked_suffix: .CELERY.CHECKED
      completed_suffix: .GEOSERVER.READY
  ingestion:
    behaviour: bulk_override
    trigger: ready_marker
    batch_mode: run
  temporal:
    filename_regex: ".*([0-9]{10}).*"
    filename_format: yyyyMMddHH
    timezone: UTC
  geoserver:
    workspace: meteohub
    store_type: ImageMosaic
    sld:
      style_name: "{variable}"
    cache:
      zoom_start: 4       # Optional override; otherwise inherits global 5
      zoom_stop: 7        # Optional override; otherwise inherits global 8
    variables:
      t2m:
        layer_name: example-t2m
        style_name: t2m
  endpoint:
    route: /datasets/{dataset}
    operations: [metadata, file_download]
```

This illustrates a bulk replacement dataset: `ingestion.behaviour: bulk_override` is the only required ingestion choice; the shared discovery and ingestion tasks are defaults. Use `fifo_granules` with `retention.hours` and/or `retention.max_granules` for a rolling mosaic. The default implementations watch the latest READY marker, publish direct variable folders as temporal mosaics, and schedule cache invalidation before writing a completion marker. For nonstandard layouts, register a dataset-id specialization in `datasets/registry.py`; there is no dotted implementation path in YAML. Source paths may also require environment and Docker volume configuration.

## Inheritance and overrides

The top-level `geoserver.cache` mapping provides defaults. A dataset's own `geoserver.cache` mapping is merged over it, key by key. For example, a dataset specifying only `zoom_stop: 9` inherits the global `zoom_start`. Dataset-specific cache options such as `eligible`, `require_explicit_time`, or zoom values should be set at that dataset's `geoserver.cache` level; confirm that the adapter consumes a given override.

## Validate changes

The backend manifest tests load and validate the project's `datasets.yml`:

```bash
rapydo shell backend 'pytest projects/maps/backend/tests/custom/test_dataset_manifest.py -v'
rapydo shell backend 'pytest projects/maps/backend/tests/custom/test_cache_seed.py -v'
```

After a successful validation, restart/redeploy backend and Celery services so their manifest consumers reload the mounted configuration. Related implementation: `projects/maps/backend/datasets/manifest.py`, `registry.py`, and the registered adapter modules.
