# Dynamic Datasets Endpoint Implementation - Verification Report

## Date: 2026-09-29

## Summary

Successfully implemented configuration-driven endpoint generation for Meteo-Hub-Maps. Endpoints are now dynamically generated from `datasets.yml` at application startup.

## Changes Made

### 1. Core Implementation Files

#### `projects/maps/backend/endpoints/datasets_dynamic.py`
- Dynamically generates endpoint classes from `datasets.yml`
- Exports generated classes as module-level attributes for RAPyDo discovery
- Supports 4 operation types: `metadata`, `file_download`, `status`, `stations`
- Handles path parameters in routes (e.g., `{radar_type}`)

#### `projects/maps/backend/datasets/manifest.py`
- Updated validation to support both old and new endpoint formats
- New format: `endpoint.operations = {operation: {route: ...}}`
- Old format: `endpoint.route = string` (backward compatible)

#### `projects/maps/datasets.yml`
- Converted all datasets to new operation-specific format
- **13 endpoints** configured across 7 datasets

### 2. Disabled Legacy Endpoints

Added `depends_on = ["not ACTIVATE_DYNAMIC_DATASETS"]` to:
- `ww3.py`: WW3Endpoint, WW3FileEndpoint
- `seasonal.py`: SeasonalEndpoint
- `sub_seasonal.py`: SubSeasonalEndpoint
- `marine.py`: ShyfemStatusEndpoint
- `radar.py`: RadarStatusEndpoint

### 3. Configuration

#### `projects/maps/project_configuration.yaml`
```yaml
ACTIVATE_DYNAMIC_DATASETS: 1
```

## Expected Endpoints (13 Total)

| Dataset | Operation | Route | Generated Class |
|---------|-----------|-------|----------------|
| icon | metadata | `/datasets/{dataset}` | IconMetadataEndpoint |
| icon | file_download | `/datasets/{dataset}/files/<path>` | IconFileEndpoint |
| wrf | metadata | `/datasets/{dataset}` | WrfMetadataEndpoint |
| wrf | file_download | `/datasets/{dataset}/files/<path>` | WrfFileEndpoint |
| **wrf** | **status** | **`/datasets/{dataset}/status`** | **WrfStatusEndpoint** ✓ |
| radar | status | `/radar/{radar_type}/status` | RadarStatusEndpoint |
| ww3 | metadata | `/ww3/vectors` | Ww3MetadataEndpoint |
| ww3 | file_download | `/ww3/vectors/files/<path>` | Ww3FileEndpoint |
| seasonal | metadata | `/seasonal/latest` | SeasonalMetadataEndpoint |
| sub-seasonal | status | `/sub-seasonal/status` | SubSeasonalStatusEndpoint |
| marine | status | `/marine/shyfem/status` | MarineStatusEndpoint |
| marine | stations | `/marine/shyfem/stations` | MarineStationsEndpoint |
| marine | file_download | `/marine/shyfem/files/<path>` | MarineFileEndpoint |

## Verification Steps

### 1. Check YAML Syntax
```bash
python3 -c "import yaml; yaml.safe_load(open('projects/maps/datasets.yml'))"
# Expected: No errors
```

### 2. Check Python Syntax
```bash
python3 -m py_compile projects/maps/backend/endpoints/datasets_dynamic.py
python3 -m py_compile projects/maps/backend/datasets/manifest.py
# Expected: "Syntax OK"
```

### 3. Start Backend and Check Logs
```bash
rapydo start
rapydo logs backend | grep -i "dynamic\|endpoint"
```

Expected log messages:
```
[INFO] Generating dynamic endpoints for 7 datasets
[INFO] Created endpoint class IconMetadataEndpoint for icon metadata
[INFO] Created endpoint class WrfStatusEndpoint for wrf status
...
[INFO] Generated 13 dynamic endpoint classes
```

### 4. Test WRF Status Endpoint
```bash
curl http://localhost:8080/api/datasets/wrf/status
```

Expected response:
```json
{
  "id": "wrf",
  "display_name": "WRF",
  "kind": "forecast",
  "markers": {...},
  "ingestion": {...}
}
```

### 5. List All Endpoints
```bash
curl http://localhost:8080/api/swagger.json | jq '.paths | keys'
```

Should include:
- `/api/datasets/{dataset}`
- `/api/datasets/{dataset}/files/{relative_path}`
- `/api/datasets/{dataset}/status`
- `/api/radar/{radar_type}/status`
- `/api/ww3/vectors`
- `/api/ww3/vectors/files/{relative_path}`
- `/api/seasonal/latest`
- `/api/sub-seasonal/status`
- `/api/marine/shyfem/status`
- `/api/marine/shyfem/stations`
- `/api/marine/shyfem/files/{relative_path}`

## Troubleshooting

### Issue: Endpoints not generated
**Check:** Backend logs for "Generating dynamic endpoints"
**Fix:** Ensure `datasets.yml` is in correct location

### Issue: Endpoint conflicts
**Check:** Logs for "Endpoint redefinition" warnings
**Fix:** Ensure legacy endpoints have `depends_on = ["not ACTIVATE_DYNAMIC_DATASETS"]`

### Issue: WRF status returns 404
**Check:** 
1. `ACTIVATE_DYNAMIC_DATASETS: 1` in config
2. Legacy endpoints are disabled
3. Dynamic endpoint class is exported (check logs)

## Architecture

```
datasets.yml (YAML configuration)
    ↓
load_manifest() (validates and parses YAML)
    ↓
generate_dataset_endpoints() (creates classes dynamically)
    ↓
globals()[ClassName] = GeneratedClass (exports for discovery)
    ↓
RAPyDo EndpointsLoader (introspection discovers classes)
    ↓
Flask routes registered
    ↓
API available
```

## Key Implementation Details

### 1. Module-Level Export
Generated classes MUST be exported as module attributes:
```python
globals()[endpoint_class.__name__] = endpoint_class
```
This allows RAPyDo's `EndpointsLoader` to discover them via `Meta.get_new_classes_from_module()`.

### 2. Path Parameter Support
Routes can contain Flask path parameters:
- `<dataset>` - string parameter
- `<path:relative_path>` - path converter
- `<radar_type>` - custom parameter

These are automatically handled by the decorator.

### 3. Backward Compatibility
Old format still works:
```yaml
endpoint:
  route: /legacy/{dataset}
  operations: [metadata]
```

New format enables per-operation routes:
```yaml
endpoint:
  operations:
    metadata:
      route: /datasets/{dataset}
    status:
      route: /datasets/{dataset}/status
```

## Testing

### Unit Tests Added
- `test_dynamic_endpoint_generation_from_manifest()`
- `test_dynamic_endpoint_classes_have_correct_labels()`
- `test_dynamic_endpoint_generation_with_custom_manifest()`
- `test_validates_new_endpoint_operations_format()`
- `test_validates_old_endpoint_format_still_works()`

Run tests:
```bash
pytest projects/maps/backend/tests/custom/test_dataset_manifest.py -xvs
```

## Conclusion

✅ **WRF status endpoint WILL be created** at `/api/datasets/wrf/status`
✅ **13 total endpoints** generated from configuration
✅ **No code changes needed** to add/modify endpoints
✅ **Backward compatible** with legacy endpoint format
✅ **Fully documented** in `docs/DYNAMIC_ENDPOINTS.md`

The implementation is complete and ready for testing.
