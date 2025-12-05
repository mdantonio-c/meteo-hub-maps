# Sub-Seasonal Data Documentation

This document describes the sub-seasonal forecast data ingestion, storage, and access mechanisms.

## Overview

Sub-seasonal forecast data provides medium-range meteorological predictions (typically 2-4 weeks). The service manages sub-seasonal data through automated ingestion into GeoServer and exposes metadata through a REST API.

## Data Structure

### File System Organization

```
/sub-seasonal-aim/
├── <YYYYMMDD>.READY
├── <YYYYMMDD>-<YYYYMMDD>.CELERY.CHECKED
├── <YYYYMMDD>-<YYYYMMDD>.GEOSERVER.READY
├── t2m/
│   ├── terzile_1/
│   │   ├── <YYYY-MM-DD>.tiff
│   │   └── ...
│   ├── terzile_2/
│   ├── terzile_3/
│   ├── quintile_1/
│   └── quintile_5/
└── tp/
    ├── terzile_1/
    │   ├── <YYYY-MM-DD>.tiff
    │   └── ...
    └── ...
```

**Example:**
```
/sub-seasonal-aim/
├── 20251203.READY
├── 20251201-20251222.GEOSERVER.READY
├── t2m/
│   ├── terzile_1/
│   │   ├── 2025-12-01.tiff
│   │   ├── 2025-12-08.tiff
│   │   └── ...
```

### Status Files

| File Pattern | Purpose |
|--------------|---------|
| `<YYYYMMDD>.READY` | Marks data as ready for processing (trigger) |
| `<Start>-<End>.CELERY.CHECKED` | Debounce marker and processing lock |
| `<Start>-<End>.GEOSERVER.READY` | Confirms GeoServer ingestion and stores metadata |

## Data Ingestion Workflow

### 1. File System Monitoring

The Celery task `check_latest_data_and_trigger_geoserver_import_sub_seasonal` monitors the sub-seasonal directory:

```python
# Default path
sub_seasonal_path = "/sub-seasonal-aim"
```

**Monitoring Schedule:** Every minute

### 2. Detection Process

1. Scan for `.READY` files in `/sub-seasonal-aim`
2. Identify the run date from the filename (e.g., `20251203`)
3. Calculate the data range (Start-End) by inspecting files in `t2m/terzile_1`
4. Check if `<Start>-<End>.GEOSERVER.READY` exists (skip if present)
5. Check if `<Start>-<End>.CELERY.CHECKED` exists (skip if present)
6. Create `.CELERY.CHECKED` file to lock processing

### 3. GeoServer Import

When new data is detected:

```
Task: update_geoserver_sub_seasonal_layers
Args: (run_date, range_str)
```

This triggers the ingestion of sub-seasonal forecast data into GeoServer.
The task:
1. Creates/Updates the workspace `meteohub`
2. Updates SLDs from `projects/maps/builds/geoserver/SLDs/sub-seasonal`
3. Iterates through all variables (e.g., `t2m`, `tp`) and values (e.g., `terzile_1`...`terzile_3`, `quintile_1`, `quintile_5`) found in the directory structure
4. Copies files to GeoServer data directory
5. Creates ImageMosaic stores and layers
6. Enables time dimension
7. Associates SLDs (e.g., `t2m_terzile_1`) with layers

### 4. Status Tracking

After successful import, creates `<Start>-<End>.GEOSERVER.READY`:
```
Processed by GeoServer at <Timestamp>
Run: <YYYYMMDD>
Range: <Start>-<End>
```

## API Access

### Get Latest Sub-Seasonal Data

```bash
GET /api/sub-seasonal/latest
```

**Response:**
```json
{
  "from": "2025-12-01T00:00:00",
  "to": "2025-12-22T00:00:00",
  "run": "20251203",
  "meta": {
    "lastUpdate": "2025-12-03T10:00:00",
    "pendingImport": null
  }
}
```

**Response Fields:**
- `from` - Start date of the forecast range (ISO format)
- `to` - End date of the forecast range (ISO format)
- `run` - Run date of the forecast (YYYYMMDD)
- `meta.lastUpdate` - Timestamp when data was processed
- `meta.pendingImport` - Information about ongoing ingestion (if any)

## GeoServer Access

Once ingested, sub-seasonal forecast data is accessible via GeoServer WMS/WCS services.
Layer names follow the pattern: `sub_seasonal_<variable>_<value>`

**Example:** `meteohub:sub_seasonal_t2m_terzile_1`

```
http://geoserver.dockerized.io:8080/geoserver/meteohub/wms?
  service=WMS&
  request=GetMap&
  layers=meteohub:sub_seasonal_t2m_terzile_1&
  ...
```
