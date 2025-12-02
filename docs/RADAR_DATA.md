# Radar Data Documentation

This document describes radar data ingestion, processing, and serving through GeoServer ImageMosaics with temporal support.

## Overview

Radar data provides high-resolution precipitation observations with 1-minute temporal resolution. The service manages a rolling 72-hour window of radar imagery, automatically ingesting new data and removing old granules to maintain storage limits.

## Radar Variables

| Variable | Description | SLD Style |
|----------|-------------|-----------|
| `sri` | Surface Rainfall Intensity | `radar-sri` |
| `srt` | Surface Rainfall Type | `radar-srt` |

## Data Structure

### File System Organization

```
/radar/
├── sri/
│   ├── files/
│   │   ├── 01-12-2025-10-30.tif
│   │   ├── 01-12-2025-10-31.tif
│   │   └── ...
│   ├── <from>-<to>.READY
│   ├── <from>-<to>.CELERY.CHECKED
│   └── <from>-<to>.GEOSERVER.READY
└── srt/
    ├── files/
    │   └── ...
    └── ...
```

### File Naming Convention

**Data Files:** `DD-MM-YYYY-HH-MM.tif`
- Format: Day-Month-Year-Hour-Minute
- Example: `01-12-2025-14-35.tif` (December 1, 2025, 14:35 UTC)
- Temporal Resolution: 1 minute

**Status Files:** `<YYYYMMDDHHMM>-<YYYYMMDDHHMM>.<TYPE>`
- Date range format representing batch of processed files
- Example: `202512011000-202512011430.GEOSERVER.READY`

## Data Ingestion Workflow

### 1. File System Monitoring

The Celery task `check_latest_data_and_trigger_geoserver_import_radar` monitors:

```python
# Default path
radar_path = "/radar"

# Monitored variables
variables = ["sri", "srt"]
```

**Monitoring Schedule:** Every minute

### 2. Batch Detection Logic

1. Scan each variable directory for `.READY` files
2. Parse timestamp from latest `.READY` file
3. Determine last processed timestamp from `.GEOSERVER.READY` files
4. Calculate pending file range:
   - If first ingestion: Start from 72 hours before latest READY
   - If incremental: Start from last processed time + 1 minute
5. Collect all files in the pending time range
6. Apply 10-minute debounce via `.CELERY.CHECKED`

### 3. Batch Processing

When new data is detected, triggers batch import:

```
Task: update_geoserver_radar_layers
Args: (variable, filenames[], dates[])
```

**Batch Benefits:**
- Reduces GeoServer API calls
- Improves import efficiency
- Maintains transactional consistency

### 4. GeoServer Import Process

For each radar variable, the system:

#### Initial Setup (First Time)
1. Creates workspace `meteohub`
2. Copies ALL available files to `/geoserver_data/copies/radar-<variable>/`
3. Creates temporal configuration (`indexer.properties`, `timeregex.properties`)
4. Uploads as ImageMosaic store
5. Publishes layer `radar-<variable>`
6. Enables time dimension
7. Associates SLD style

#### Incremental Updates
1. Copies new file(s) to mosaic directory
2. Removes index files (`*.shp`, `*.dbf`, `*.properties`, etc.)
3. Recreates temporal configuration
4. Reinitializes mosaic (forces reindexing)
5. Reapplies time dimension configuration
6. Reapplies SLD style

### 5. Rolling Window Management

After batch processing:

1. Calculate total time span from all granules
2. If span > 72 hours:
   - Remove old `.tif` files from disk
   - Remove oldest granules from GeoServer index
   - Maintain 72-hour window ending at latest data

### 6. Status Tracking

Creates `.GEOSERVER.READY` file with full time range:

```
Processed by GeoServer at 2025-12-01T14:35:00
Files in batch: 5
Total files in GeoServer: 4320
Time range: 2025-11-28T14:35:00 to 2025-12-01T14:35:00
Coverage: 72.0 hours
```

## Temporal Configuration

### Indexer Properties

```properties
PropertyCollectors=TimestampFileNameExtractorSPI[timeregex](time)
TimeAttribute=time
Schema=*the_geom:Polygon,location:String,time:java.util.Date
```

### Time Regex

```properties
regex=([0-9]{2}-[0-9]{2}-[0-9]{4}-[0-9]{2}-[0-9]{2}),format=dd-MM-yyyy-HH-mm
```

This extracts the timestamp from filenames like `01-12-2025-14-35.tif`.

## Time Dimension Configuration

```xml
<coverage>
  <enabled>true</enabled>
  <metadata>
    <entry key="time">
      <dimensionInfo>
        <enabled>true</enabled>
        <presentation>LIST</presentation>
        <units>ISO8601</units>
        <defaultValue>
          <strategy>MAXIMUM</strategy>
        </defaultValue>
      </dimensionInfo>
    </entry>
  </metadata>
</coverage>
```

## GeoServer Access

### WMS GetMap Request

```bash
http://geoserver.dockerized.io:8080/geoserver/meteohub/wms?
  service=WMS&
  version=1.1.0&
  request=GetMap&
  layers=meteohub:radar-sri&
  time=2025-12-01T14:35:00.000Z&
  bbox=...&
  width=800&
  height=600&
  srs=EPSG:4326&
  format=image/png
```

### WMS GetCapabilities

Query available times:

```bash
GET /geoserver/meteohub/wms?
  service=WMS&
  version=1.1.0&
  request=GetCapabilities
```

Look for `<Dimension name="time">` in the `radar-sri` or `radar-srt` layer.

### WMS GetFeatureInfo

Get pixel values on hover:

```bash
GET /geoserver/meteohub/wms?
  service=WMS&
  version=1.1.0&
  request=GetFeatureInfo&
  layers=meteohub:radar-sri&
  query_layers=meteohub:radar-sri&
  time=2025-12-01T14:35:00.000Z&
  x=400&
  y=300&
  ...
```

## SLD Styling

Each radar variable has an associated SLD style:

| Variable | SLD File | Purpose |
|----------|----------|---------|
| sri | `radar-sri.sld` | Rainfall intensity color ramp |
| srt | `radar-srt.sld` | Rainfall type classification |

SLD files are stored in:
```
/SLDs/radar/
└── <variable>/
    └── radar-<variable>.sld
```

Styles are automatically uploaded to GeoServer during initialization.

## Operational Details

### Data Volume

- **Temporal Resolution:** 1 minute
- **Retention Period:** 72 hours
- **Total Granules:** ~4,320 files per variable (72 hours × 60 minutes/hour)
- **File Size:** Varies by variable and coverage

### Performance Considerations

- **Batch Processing:** Multiple files processed in single transaction
- **Index Removal:** Forces mosaic reinitialization for reliability
- **Cleanup Frequency:** Only when 72-hour window is exceeded

### Storage Management

Files are stored in two locations:

1. **Source:** `/radar/<variable>/files/` (original data)
2. **GeoServer:** `/geoserver_data/copies/radar-<variable>/` (served data)

Old files are automatically removed from both locations during cleanup.

## Troubleshooting

### No Radar Data Available

1. Check source directory exists: `/radar/<variable>/files/`
2. Verify `.READY` files are being created
3. Confirm monitoring task is running: `POST /api/data/monitoring`
4. Review Celery logs for task execution errors

### Granules Not Appearing in GeoServer

1. Check if `.GEOSERVER.READY` file was created
2. Verify files exist in `/geoserver_data/copies/radar-<variable>/`
3. Query GeoServer REST API:
   ```bash
   GET /geoserver/rest/workspaces/meteohub/coveragestores/mosaic_radar-sri/coverages/radar-sri/index/granules.json
   ```
4. Check GeoServer logs for errors

### Time Dimension Not Working

1. Verify `indexer.properties` and `timeregex.properties` exist in mosaic directory
2. Confirm time regex matches filename format
3. Check layer configuration via GeoServer admin UI
4. Reinitialize mosaic by deleting index files and re-uploading

### Old Data Not Being Removed

1. Verify cleanup logic is running (logs show "Removing oldest granule")
2. Check if granule deletion API calls are succeeding
3. Manually query and remove granules if needed:
   ```bash
   DELETE /geoserver/rest/workspaces/meteohub/coveragestores/mosaic_radar-sri/coverages/radar-sri/index/granules/<granule-id>
   ```

## Integration Example

### Python Client with Time Selection

```python
import requests
from datetime import datetime, timedelta

class RadarDataClient:
    def __init__(self, geoserver_url, workspace='meteohub'):
        self.geoserver_url = geoserver_url
        self.workspace = workspace
    
    def get_radar_image(self, variable, time, bbox, width=800, height=600):
        """
        Get radar image for specific time.
        
        Args:
            variable: Radar variable (sri, srt)
            time: datetime object
            bbox: (minx, miny, maxx, maxy)
            width: Image width
            height: Image height
        """
        time_str = time.strftime('%Y-%m-%dT%H:%M:%S.000Z')
        
        params = {
            'service': 'WMS',
            'version': '1.1.0',
            'request': 'GetMap',
            'layers': f'{self.workspace}:radar-{variable}',
            'time': time_str,
            'bbox': ','.join(map(str, bbox)),
            'width': width,
            'height': height,
            'srs': 'EPSG:4326',
            'format': 'image/png'
        }
        
        url = f'{self.geoserver_url}/wms'
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        return response.content
    
    def get_latest_time(self, variable):
        """Get the latest available time for a variable."""
        # Query capabilities to find latest time
        # Implementation depends on parsing GetCapabilities XML
        pass

# Usage
client = RadarDataClient('http://geoserver.dockerized.io:8080/geoserver/meteohub')

# Get current radar image
now = datetime.utcnow()
# Round to nearest minute
now = now.replace(second=0, microsecond=0)

image_data = client.get_radar_image(
    variable='sri',
    time=now,
    bbox=(6.0, 36.0, 19.0, 47.0),  # Italy bounds
    width=1024,
    height=768
)

with open('radar_sri_latest.png', 'wb') as f:
    f.write(image_data)
```

### JavaScript with Leaflet

```javascript
// Add radar layer to Leaflet map
const radarLayer = L.tileLayer.wms(
  'http://geoserver.dockerized.io:8080/geoserver/meteohub/wms',
  {
    layers: 'meteohub:radar-sri',
    format: 'image/png',
    transparent: true,
    time: new Date().toISOString(), // Current time
    opacity: 0.7
  }
);

map.addLayer(radarLayer);

// Update time dimension every minute
setInterval(() => {
  radarLayer.setParams({
    time: new Date().toISOString()
  });
}, 60000);
```
