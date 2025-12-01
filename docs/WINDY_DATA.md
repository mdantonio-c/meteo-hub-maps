# Windy Data Documentation

This document describes the Windy forecast data ingestion, storage, and access mechanisms.

## Overview

Windy data provides high-resolution forecast model outputs in GeoTIFF format, served through GeoServer as time-enabled ImageMosaics. The service supports multiple forecast models with different spatial resolutions and forecast horizons.

## Supported Datasets

| Dataset | Model | Area | Resolution | Forecast Length | Time Step |
|---------|-------|------|------------|-----------------|-----------|
| `icon` | ICON 2I | Italia | ~2km | 0-72h | 1 hour |
| `lm2.2` | COSMO LM | Italia | 2.2km | 0-48h | 1 hour |
| `lm5` | COSMO LM | Area Mediterranea | 5km | 0-72h | 1 hour |

### Geographic Boundaries

**Italia (icon, lm2.2)**
- Southwest: 33.69°N, 2.99°E
- Northeast: 48.91°N, 22.01°E

**Area Mediterranea (lm5)**
- Southwest: 25.8°N, -30.9°E
- Northeast: 55.5°N, 47.0°E

## Data Structure

### File System Organization

```
/data/<platform>/<env>/Windy-<run>-<dataset>.web/
└── <area>/
    ├── <reftime>.READY
    ├── <reftime>.GEOSERVER.READY
    ├── <reftime>.CELERY.CHECKED
    └── <variable>/
        └── <filename>.tif
```

**Example:**
```
/data/G100/PROD/Windy-00-ICON_2I_all2km.web/
└── Italia/
    ├── 2025120100.GEOSERVER.READY
    └── t2m/
        ├── t2m.2025120100.0000.tif
        ├── t2m.2025120100.0001.tif
        └── ...
```

### File Naming Convention

**Data Files:** `<variable>.<reftime>.<offset>.tif`
- `variable` - Meteorological variable (e.g., `t2m`, `prec6`, `wind`)
- `reftime` - Reference time in `YYYYMMDDHH` format (e.g., `2025120100`)
- `offset` - Forecast offset in hours, zero-padded to 4 digits (e.g., `0000`, `0012`, `0048`)

**Status Files:**
- `.READY` - Indicates data generation is complete
- `.CELERY.CHECKED` - Marks data as checked by Celery task (debounce mechanism)
- `.GEOSERVER.READY` - Confirms data ingestion into GeoServer

## Data Ingestion Workflow

### 1. File System Monitoring

The Celery task `check_latest_data_and_trigger_geoserver_import_windy` monitors data directories:

```python
# Default paths monitored
paths = [
    "/windy/Windy-00-ICON_2I_all2km.web/Italia",
    "/windy/Windy-12-ICON_2I_all2km.web/Italia"
]
```

**Monitoring Schedule:** Every minute (configurable via crontab)

### 2. Detection Logic

1. Scan for `.READY` files in monitored directories
2. Sort by reference time to find the latest run
3. Check if `.GEOSERVER.READY` already exists (skip if present)
4. Apply debounce logic with `.CELERY.CHECKED` file (10-minute window)

### 3. GeoServer Import

When new data is detected, the task triggers:

```
Task: update_geoserver_image_mosaic
Args: (geoserver_url, date, run)
```

This creates or updates a GeoServer ImageMosaic with:
- **Workspace:** `meteohub`
- **Store Name:** Based on dataset and run
- **Time Dimension:** Enabled with ISO8601 format
- **Default Time:** Maximum (latest) timestamp

### 4. Status Tracking

After successful import, a `.GEOSERVER.READY` file is created with metadata:
```
Processed by GeoServer at 2025-12-01T10:30:00
Reference time: 2025120100
Forecast offsets: 73
```

## API Access

### Get Latest Windy Data Info

```bash
GET /api/windy?dataset=icon
```

**Response:**
```json
{
  "dataset": "icon",
  "area": "Italia",
  "start_offset": 0,
  "end_offset": 72,
  "step": 1,
  "boundaries": {
    "SW": [33.69, 2.9875],
    "NE": [48.91, 22.0125]
  },
  "reftime": "2025120100",
  "platform": null
}
```

### Get Latest Data for Specific Run

```bash
GET /api/windy?dataset=icon&run=00
```

### Download Specific GeoTIFF File

```bash
GET /api/windy?dataset=icon&foldername=t2m&filename=t2m.2025120100.0012.tif
```

Returns the GeoTIFF file with `Content-Type: image/tif`

## GeoServer Integration

### WMS Layer Access

Once ingested, data is accessible via GeoServer WMS:

```
http://geoserver.dockerized.io:8080/geoserver/meteohub/wms?
  service=WMS&
  version=1.1.0&
  request=GetMap&
  layers=meteohub:windy-icon-00&
  time=2025-12-01T00:00:00.000Z&
  ...
```

### Time Dimension

The ImageMosaic is configured with temporal support:
- **Time Attribute:** Extracted from filename
- **Presentation:** LIST (all available times)
- **Default Value:** MAXIMUM (latest time)
- **Units:** ISO8601

### Available Times Query

```bash
GET /geoserver/meteohub/wms?
  service=WMS&
  version=1.1.0&
  request=GetCapabilities
```

Look for the `<Dimension name="time">` element in the layer capabilities.

## Operational Notes

### Data Freshness

- **Update Frequency:** Typically 2 runs per day (00 UTC, 12 UTC)
- **Processing Delay:** 15-30 minutes after model run completion
- **Monitoring Interval:** Every minute

### Storage Management

- Old forecast runs are replaced when new data arrives
- `.GEOSERVER.READY` files indicate successfully ingested runs
- Manual cleanup of old runs may be needed for disk space management

### Troubleshooting

**No data available:**
1. Check if `.READY` file exists in the data directory
2. Verify monitoring task is running: `GET /api/data/monitoring`
3. Check GeoServer logs for import errors
4. Confirm file permissions allow read access

**Stale data:**
1. Verify upstream model runs are completing
2. Check Celery worker is processing tasks
3. Look for error logs in backend container
4. Ensure `.CELERY.CHECKED` files are not blocking new imports (should auto-expire after 10 minutes)

## Example Usage

### Python Client

```python
import requests

# Get latest icon forecast info
response = requests.get('http://server:8080/api/windy?dataset=icon')
data = response.json()

reftime = data['reftime']  # e.g., "2025120100"
print(f"Latest forecast: {reftime}")
print(f"Available hours: {data['start_offset']} to {data['end_offset']}")

# Download specific forecast hour
url = (
    'http://server:8080/api/windy'
    f'?dataset=icon&foldername=t2m&filename=t2m.{reftime}.0012.tif'
)
response = requests.get(url)
with open('forecast_t2m_12h.tif', 'wb') as f:
    f.write(response.content)
```

### JavaScript Client

```javascript
// Get latest forecast info
fetch('/api/windy?dataset=icon')
  .then(response => response.json())
  .then(data => {
    console.log('Latest forecast:', data.reftime);
    console.log('Coverage:', data.boundaries);
    
    // Use with Leaflet/OpenLayers WMS layer
    const wmsUrl = `http://geoserver:8080/geoserver/meteohub/wms`;
    // Configure your map layer...
  });
```
