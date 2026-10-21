# Dynamic Dataset Endpoints

## Overview

The Meteo-Hub-Maps API now supports **configuration-driven endpoint generation**. You can add, remove, or modify API endpoints by editing `datasets.yml` without touching Python code.

## How It Works

1. **At startup**, the `datasets_dynamic.py` module reads `datasets.yml`
2. **For each dataset**, it generates endpoint classes based on the `endpoint.operations` configuration
3. **RAPyDo's EndpointsLoader** automatically discovers and registers these classes
4. **Endpoints are available** via the REST API

## Configuration Format

### New Structure (Dynamic)

```yaml
datasets:
  - id: icon
    # ... other config ...
    endpoint:
      operations:
        metadata:
          route: /datasets/{dataset}
        file_download:
          route: /datasets/{dataset}/files/<path:relative_path>
```

### Old Structure (Deprecated)

```yaml
endpoint:
  route: /datasets/{dataset}
  operations: [metadata, file_download]  # This is now ignored
```

## Supported Operations

| Operation | Description | Route Pattern |
|-----------|-------------|---------------|
| `metadata` | Returns dataset metadata and capabilities | Custom |
| `file_download` | Downloads files from dataset directory | Custom + `/files/<path>` |
| `status` | Returns ingestion status | Custom |
| `stations` | Returns station list (marine only) | Custom |

## Examples

### ICON Dataset (Metadata + File Download)

```yaml
- id: icon
  endpoint:
    operations:
      metadata:
        route: /datasets/{dataset}
      file_download:
        route: /datasets/{dataset}/files/<path:relative_path>
```

**Generated Endpoints:**
- `GET /api/datasets/icon` - Metadata
- `GET /api/datasets/icon/files/<path>` - File download

### Marine Dataset (Multiple Operations)

```yaml
- id: marine
  endpoint:
    operations:
      status:
        route: /marine/shyfem/status
      stations:
        route: /marine/shyfem/stations
      file_download:
        route: /marine/shyfem/files/<path:relative_path>
```

**Generated Endpoints:**
- `GET /api/marine/shyfem/status` - Status
- `GET /api/marine/shyfem/stations` - Stations
- `GET /api/marine/shyfem/files/<path>` - File download

### Radar Dataset (Status Only)

```yaml
- id: radar
  endpoint:
    operations:
      status:
        route: /radar/status
```

**Generated Endpoints:**
- `GET /api/radar/status` - Status

## Adding a New Endpoint

### Step 1: Add to datasets.yml

```yaml
- id: my-new-dataset
  kind: forecast
  # ... discovery, ingestion, temporal, geoserver config ...
  endpoint:
    operations:
      metadata:
        route: /my-new-dataset/info
      custom_operation:
        route: /my-new-dataset/custom
```

### Step 2: Add Handler (if needed)

If you need a new operation type (beyond `metadata`, `file_download`, `status`, `stations`):

1. Edit `projects/maps/backend/endpoints/datasets_dynamic.py`
2. Add a new `create_*_endpoint_class` function
3. Add it to `_create_endpoint_for_operation()` mapping

### Step 3: Restart Backend

```bash
rapydo restart
```

## Metadata Response Format

All `metadata` endpoints return:

```json
{
  "id": "icon",
  "kind": "forecast",
  "display_name": "ICON 2I all2km",
  "adapter": "bulk_override",
  "capabilities": ["metadata", "file_download"],
  "discovery": {
    "area": "Italia",
    "variables": [],
    "runs": ["00", "12"]
  },
  "temporal": {
    "filename_regex": ".*([0-9]{10}).*",
    "filename_format": "yyyyMMddHH",
    "timezone": "UTC"
  },
  "geoserver": {
    "workspace": "meteohub",
    "store_type": "ImageMosaic",
    "layers": [
      {"variable": "t2m-t2m", "layer": "t2m-t2m"}
    ]
  }
}
```

## File Download Security

The `file_download` operation includes path traversal protection:
- Files must be within the dataset's base directory
- Absolute paths are rejected
- Path traversal (`../`) is blocked

## Implementation Details

### Files Modified

- `projects/maps/datasets.yml` - Updated to new operation-specific route format
- `projects/maps/backend/endpoints/datasets.py` - Simplified to helper functions only
- `projects/maps/backend/endpoints/datasets_dynamic.py` - New dynamic endpoint generator
- `projects/maps/backend/tests/custom/test_dataset_manifest.py` - Added tests

### How Endpoints Are Registered

1. `datasets_dynamic.py` is imported by RAPyDo's endpoint loader
2. At module import time, `generate_dataset_endpoints()` runs
3. For each dataset+operation, a new class is created dynamically
4. The `@decorators.endpoint` decorator is applied programmatically
5. RAPyDo's `EndpointsLoader` discovers the classes via introspection
6. Endpoints are registered with Flask

### Class Naming

Generated classes follow the pattern: `{DatasetId}{Operation}Endpoint`

Examples:
- `IconMetadataEndpoint`
- `MarineStationsEndpoint`
- `RadarStatusEndpoint`

## Troubleshooting

### Endpoints Not Appearing

1. Check `datasets.yml` syntax: `python3 -c "import yaml; yaml.safe_load(open('projects/maps/datasets.yml'))"`
2. Check backend logs: `rapydo logs backend`
3. Verify module import: Look for "Generating dynamic endpoints" in logs

### Invalid Route Format

Routes must use Flask path syntax:
- ✅ `/datasets/{dataset}` → `/datasets/<dataset>` (auto-converted)
- ✅ `/files/<path:relative_path>` (Flask path converter)
- ❌ `/files/{path}` (invalid)

### Operation Not Supported

If you get "Unknown operation" in logs, add a handler in `datasets_dynamic.py`.

## Migration Guide

### From Old Format to New

**Before:**
```yaml
endpoint:
  route: /marine/shyfem/status
  operations: [status, stations, file_download]
```

**After:**
```yaml
endpoint:
  operations:
    status:
      route: /marine/shyfem/status
    stations:
      route: /marine/shyfem/stations
    file_download:
      route: /marine/shyfem/files/<path:relative_path>
```

### Testing

After migration, verify endpoints:

```bash
# List all endpoints
curl http://localhost:8080/api/swagger.json | jq '.paths | keys'

# Test metadata endpoint
curl http://localhost:8080/api/datasets/icon

# Test file download (if enabled)
curl http://localhost:8080/api/datasets/icon/files/some-file.tif
```
