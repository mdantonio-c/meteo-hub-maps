# WW3 Data Import System Documentation

This document describes the ww3 file data ingestion, storage, and access mechanisms.

## Overview

The ww3 import system monitors a central data directory for new model runs and processes three specific variables:
- **hs**: Significant wave height (GeoServer Layer)
- **t01**: Mean wave period (GeoServer Layer)
- **gradients**: Gradient vectors (JSON files exposed via API)

## Data Structure

### File System Organization

The system expects the following structure under the configured `WW3_DATA_PATH` (default: `/data/ww3`):

```
/data/ww3/
├── <run_date>.READY
├── <run_date>.GEOSERVER.READY
├── <run_date>.CELERY.CHECKED
├── hs/
│   ├── <date>-<time>.tif
│   └── ...
├── t01/
│   ├── <date>-<time>.tif
│   └── ...
└── gradients/
    ├── <filename>.json
    └── ...
```

**Example:**
```
/data/ww3/
├── 20251203.READY
├── hs/
│   ├── 03-12-2025-00.tif
│   ├── 03-12-2025-01.tif
│   └── ...
├── t01/
│   ├── 03-12-2025-00.tif
│   └── ...
└── gradients/
    ├── 20251203_00.json
    └── ...
```

### File Naming Convention

- **GeoTIFF Files (`hs`, `t01`)**: Should follow `dd-MM-yyyy-HH.tif` format (e.g., `03-12-2025-00.tif`) for correct time dimension extraction.
- **Status Files**:
    - `.READY` - Indicates data generation is complete and ready for processing.
    - `.CELERY.CHECKED` - Marks data as checked by Celery task.
    - `.GEOSERVER.READY` - Confirms data ingestion into GeoServer.

## Data Ingestion Workflow

### 1. File System Monitoring

A Celery task monitors the root directory using the `DataWatcher` utility:

```python
# Task runs every minute
check_latest_data_and_trigger_geoserver_import_ww3()
```

### 2. Detection Logic

1.  Scan for `.READY` files in `WW3_DATA_PATH`.
2.  Check if `.GEOSERVER.READY` already exists for that run.
3.  Trigger ingestion if new data is found.
4.  Uses `DataWatcher` to handle file locking and status updates consistently.

### 3. Import Processing

**Task:** `update_geoserver_ww3_layers`

For `hs` and `t01` folders:
1.  Copies files to GeoServer data directory (`/geoserver_data/copies/ww3_hs`, `/geoserver_data/copies/ww3_t01`).
2.  Creates `indexer.properties` (with `CanBeEmpty=true` to handle sparse data) and `timeregex.properties`.
3.  Creates/Updates GeoServer ImageMosaic store.
4.  Enables time dimension.

For `gradients`:
- Files are left in place and served via API.

### 4. Status Tracking

After successful processing, a `.GEOSERVER.READY` file is created in the root directory.

## API Access

### Gradients Access

#### List Available Gradient Files

```bash
GET /api/ww3/gradients
```

**Response:**
```json
[
  "20251203_00.json",
  "20251203_01.json"
]
```

#### Get Specific Gradient File

```bash
GET /api/ww3/gradients/<filename>
```

**Response:**
Returns the content of the requested JSON file.

## GeoServer Integration

### WMS Layer Access

Data is accessible via GeoServer WMS:

- **Layer Names**: `meteohub:ww3_hs`, `meteohub:ww3_t01`
- **Time Dimension**: Enabled (ISO8601)

```
http://geoserver:8080/geoserver/meteohub/wms?
  service=WMS&
  version=1.1.0&
  request=GetMap&
  layers=meteohub:ww3_hs&
  time=2025-12-03T00:00:00.000Z&
  ...
```

## Configuration

### Environment Variables

- `WW3_DATA_PATH`: Path to the WW3 data root (default: `/data/ww3`).

