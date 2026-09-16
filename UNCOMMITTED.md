# Uncommitted Changes

This file documents all changes not yet committed to the repository.

---

## 1. Atomic File Copy for GeoServer Ingestion

### Problem
When copying GeoTIFF files to the GeoServer volume, files were being made visible to GeoServer before the REST API refresh was triggered. If GeoServer started reading files during the copy, it could ingest partial/corrupted data.

### Solution
Copy files to a `.tmp` subdirectory, then use `os.rename()` (atomic on Linux) to move the entire directory into place. Only after the atomic move are GeoServer REST API calls made.

### Implementation

#### New helpers in `projects/maps/backend/datasets/geoserver.py`
- `atomic_copy_to_mosaic(target_dir, source_files) → tmp_dir` — creates `target_dir.tmp`, copies all source files there.
- `finalize_atomic_copy(tmp_dir, target_dir) → None` — calls `os.rename(tmp_dir, target_dir)`. Raises on failure. Caller should `shutil.rmtree(tmp_dir)` on exception.

### Pattern used in all task modules
```python
tmp_dir = atomic_copy_to_mosaic(target_dir, source_files)
try:
    create_mosaic_config(tmp_dir)        # write index/temporal config in tmp
    finalize_atomic_copy(tmp_dir, target_dir)  # os.rename() — atomic on Linux
except Exception:
    shutil.rmtree(tmp_dir, ignore_errors=True)
    raise
# Now safe to call GeoServer REST APIs — all files are fully visible
```

### Files changed
| File | Function |
|------|----------|
| `tasks/upload_image_mosaic.py` | `_ingest_windy_image_mosaic` — WRF/ICON tiles |
| `tasks/radar.py` | `process_radar_file` — initial + incremental |
| `tasks/ww3.py` | `process_ww3_variable` |
| `tasks/data_ready.py` | `process_seasonal_tiff_files` |
| `tasks/sub_seasonal.py` | `process_sub_seasonal_variable` |
| `tasks/check_fs_data.py` | `_ingest_mer_layer` — SHYFEM marine |

---

## 2. Manifest-Driven SLD Assignment

### Problem
SLD style names were hardcoded in every task module using separate mapping dicts (`RADAR_SLD_MAPPING`, `sld_dir_mapping`, `seasonal_sld_mapping`, `MER_WL_STYLE_NAME`). This was duplicated, unconfigurable, and hard to maintain.

### Solution
SLD style names are now declared in `datasets.yml` and resolved at ingestion time via `DatasetConfig.resolve_sld()`.

### Schema in `datasets.yml`
```yaml
geoserver:
  sld:
    style_name: radar-{variable}          # dataset-level template
  variables:
    sri:
      layer_name: radar-sri
      style_name: radar_sri                # variable-level override
```

### Resolution order
1. **Variable-level** `style_name` — takes priority
2. **Dataset-level** `sld.style_name` — template resolved with `{variable}`, `{layer_name}`, `{value}`, `{forcing}`
3. **None** — layer created without SLD (no regression)

### Changes
| File | What |
|------|------|
| `datasets.yml` | Full SLD mapping for all 7 datasets (icon, wrf, radar, ww3, seasonal, sub-seasonal, marine) |
| `datasets/manifest.py` | Added `DatasetConfig.resolve_sld(variable, layer_name, **kwargs) → str | None` |
| `datasets/geoserver.py` | Added `GeoServerPublisher.associate_slds(layer_name, sld_names)` |
| `tasks/upload_image_mosaic.py` | `config.resolve_sld(variable=folder, layer_name=geoserver_name)` |
| `datasets/windy.py` | Passes `config` to `_ingest_windy_image_mosaic` |
| `tasks/radar.py` | `process_radar_file(..., sld_name=sld_name)` |
| `datasets/radar.py` | Calls `config.resolve_sld(variable=variable)` |
| `tasks/ww3.py` | `config.resolve_sld(variable=var, layer_name=layer_name)` |
| `datasets/ww3.py` | Passes `config` to `_ingest_ww3_layers` |
| `tasks/data_ready.py` | `config.resolve_sld(variable=subdir, layer_name=layer_name)` |
| `datasets/seasonal.py` | Passes `config` to `_ingest_seasonal_layers` |
| `tasks/sub_seasonal.py` | `config.resolve_sld(variable=var, layer_name=layer_name, value=val)` |
| `datasets/sub_seasonal.py` | Passes `config` to `_ingest_sub_seasonal_layers` |
| `tasks/check_fs_data.py` | `config.resolve_sld(variable=variable_name, layer_name=layer_name, forcing=forcing_name)` |

---

## 3. Environment & Configuration Changes

### `project_configuration.yaml`
- Added `DATASET_CONFIG_PATH: /etc/meteohub/datasets.yml` — path where the manifest is mounted.
- Added `GEOSERVER_GWC_ENABLED: 1` — enables GeoWebCache invalidation.
- Added trailing newline to file (minor).

### `confs/commons.yml`
- Added `GEOSERVER_GWC_ENABLED` env var to both `backend` and `celery` services.
- Added `DATASET_CONFIG_PATH` env var to both services.
- Added volume mount: `${PROJECT_DIR}/datasets.yml:${DATASET_CONFIG_PATH}:ro` (read-only) to both services.
- Added trailing newline to file (minor).

### `initialization.py`
- Added `load_registry()` call at `Initializer.__init__` to validate the manifest at startup.

---

## 4. New Files (Untracked)

| File | Description |
|------|-------------|
| `datasets.yml` | Dataset manifest with all 7 dataset configurations (icon, wrf, radar, ww3, seasonal, sub-seasonal, marine) |
| `datasets/__init__.py` | Package init (auto-created) |
| `datasets/manifest.py` | Manifest loader, `DatasetConfig` dataclass, validation, `resolve_sld()` |
| `datasets/registry.py` | Registry that loads all configs from manifest |
| `datasets/geoserver.py` | `GeoServerPublisher`, atomic copy helpers, SLD association |
| `datasets/windy.py` | `WindyIngestionAdapter` |
| `datasets/radar.py` | `RadarIngestionAdapter` |
| `datasets/ww3.py` | `WW3IngestionAdapter` |
| `datasets/seasonal.py` | `SeasonalIngestionAdapter` |
| `datasets/sub_seasonal.py` | `SubSeasonalIngestionAdapter` |
| `datasets/marine.py` | `MarineIngestionAdapter` |
| `datasets/locking.py` | File-based dataset lock |
| `datasets/markers.py` | `.READY` / `.GEOSERVER.READY` marker creation |
| `datasets/temporal.py` | Temporal config writer for ImageMosaic |
| `datasets/cache.py` | GeoWebCache invalidator |
| `datasets/paths.py` | Safe filesystem path utilities |
| `endpoints/datasets.py` | Generic manifest-driven REST endpoints (`/datasets/<id>`, `/datasets/<id>/files/...`) |
| `tests/test_dataset_manifest.py` | 9-test suite for manifest validation |
| `.wayfinder/` | Wayfinder planning documents |
| `AGENTS.md` | Project documentation |

---

## 5. Files Deleted (Not in repo)

- `projects/maps/builds/geoserver/` — Removed (was a git submodule)

---

## Running Tests

```bash
PYTHONPATH=projects/maps/backend /usr/bin/pytest -q projects/maps/backend/tests/test_dataset_manifest.py
python -m py_compile projects/maps/backend/datasets/geoserver.py
python -m py_compile projects/maps/backend/tasks/upload_image_mosaic.py
python -m py_compile projects/maps/backend/tasks/radar.py
python -m py_compile projects/maps/backend/tasks/ww3.py
python -m py_compile projects/maps/backend/tasks/data_ready.py
python -m py_compile projects/maps/backend/tasks/sub_seasonal.py
python -m py_compile projects/maps/backend/tasks/check_fs_data.py
git diff --check
```
