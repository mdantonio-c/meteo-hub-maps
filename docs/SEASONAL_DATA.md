# Seasonal Data Documentation

This document describes the seasonal forecast data ingestion, storage, and access mechanisms.

## Overview

Seasonal forecast data provides long-range meteorological predictions. The service manages seasonal data through automated ingestion into GeoServer and exposes metadata through a REST API.

## Data Structure

### File System Organization

```
/seasonal-aim/
├── <date>.READY
├── <date>.CELERY.CHECKED
├── <date>.GEOSERVER.READY
└── <forecast_folder>/
    └── ... (data files)
```

**Example:**
```
/seasonal-aim/
├── 20251201.GEOSERVER.READY
├── forecast_dec_2025/
└── forecast_jan_2026/
```

### Status Files

| File Pattern | Purpose |
|--------------|---------|
| `<YYYYMMDD>.READY` | Marks data as ready for processing |
| `<YYYYMMDD>.CELERY.CHECKED` | Debounce marker (10-minute validity) |
| `<YYYYMMDD>.GEOSERVER.READY` | Confirms GeoServer ingestion |

## Data Ingestion Workflow

### 1. File System Monitoring

The Celery task `check_latest_data_and_trigger_geoserver_import_seasonal` monitors the seasonal directory:

```python
# Default path
seasonal_path = "/seasonal-aim"
```

**Monitoring Schedule:** Every minute (configurable)

### 2. Detection Process

1. Scan for `.READY` files in `/seasonal-aim`
2. Identify the latest seasonal dataset
3. Check if `.GEOSERVER.READY` exists (skip if present)
4. Apply 10-minute debounce logic via `.CELERY.CHECKED`

### 3. GeoServer Import

When new data is detected:

```
Task: update_geoserver_seasonal_layers
Args: (latest_ready_date,)
```

This triggers the ingestion of seasonal forecast data into GeoServer.

### 4. Status Tracking

After successful import, creates `<date>.GEOSERVER.READY`:
```
Checked by Celery task
```

## Ingestion Status

The service tracks three possible states:

| Status | Description | Indicator |
|--------|-------------|-----------|
| `ingested` | Data successfully loaded into GeoServer | `.GEOSERVER.READY` file exists |
| `ingesting` | Processing in progress | `.CELERY.CHECKED` file exists |
| `null` | No data available | No status files present |

## API Access

### Get Latest Seasonal Data

```bash
GET /api/seasonal/latest
```

**Response:**
```json
{
  "folders": [
    "forecast_dec_2025",
    "forecast_jan_2026",
    "forecast_feb_2026"
  ],
  "ingestion": {
    "last": "2025-12-01",
    "status": "ingested"
  }
}
```

**Response Fields:**
- `folders` - Array of available forecast directories
- `ingestion.last` - Date of last processed dataset (YYYY-MM-DD format)
- `ingestion.status` - Current ingestion status (`ingested`, `ingesting`, or `null`)

### Boxplot Data Access

#### List Boxplot Files

```bash
GET /api/seasonal/json
```

**Response:**
```json
[
  "boxplot_data_1.json",
  "boxplot_data_2.json"
]
```

#### Get Specific Boxplot File

```bash
GET /api/seasonal/json/<filename>
```

**Response:**
Returns the content of the requested JSON file.

## Use Cases

### Check Data Availability

```python
import requests

response = requests.get('http://server:8080/api/seasonal/latest')
data = response.json()

if data['ingestion']['status'] == 'ingested':
    print(f"Latest seasonal forecast: {data['ingestion']['last']}")
    print(f"Available forecasts: {', '.join(data['folders'])}")
elif data['ingestion']['status'] == 'ingesting':
    print("Seasonal data is currently being processed")
else:
    print("No seasonal data available")
```

### Monitor for New Data

```javascript
async function checkSeasonalData() {
  const response = await fetch('/api/seasonal/latest');
  const data = await response.json();
  
  return {
    hasData: data.ingestion.status === 'ingested',
    lastUpdate: data.ingestion.last,
    folders: data.folders
  };
}

// Poll for updates
setInterval(async () => {
  const status = await checkSeasonalData();
  console.log('Seasonal data status:', status);
}, 60000); // Check every minute
```

## GeoServer Access

Once ingested, seasonal forecast data is accessible via GeoServer WMS/WCS services:

```
http://geoserver.dockerized.io:8080/geoserver/meteohub/wms?
  service=WMS&
  request=GetMap&
  layers=meteohub:seasonal-<parameter>&
  ...
```

Specific layer names and parameters depend on the seasonal forecast configuration.

## Operational Notes

### Data Update Frequency

- Seasonal forecasts are typically updated monthly or on a custom schedule
- Update frequency depends on the upstream forecast provider
- Check the `ingestion.last` field to see when data was last updated

### Monitoring

Start the monitoring service:
```bash
POST /api/data/monitoring
```

Stop monitoring:
```bash
DELETE /api/data/monitoring
```

### Troubleshooting

**No data returned:**
1. Verify `/seasonal-aim` directory exists and is accessible
2. Check for `.READY` files in the directory
3. Ensure monitoring task is running
4. Review Celery worker logs for errors

**Status stuck on "ingesting":**
1. Check if `.CELERY.CHECKED` file is older than 10 minutes (should auto-expire)
2. Verify GeoServer is accessible
3. Check backend logs for processing errors
4. Manually remove `.CELERY.CHECKED` if needed to retry

**Old status files:**
- Status files from previous runs can be safely removed
- Keep only the most recent `.GEOSERVER.READY` file for tracking

## Integration Example

```python
import requests
from datetime import datetime

class SeasonalDataClient:
    def __init__(self, base_url):
        self.base_url = base_url
    
    def get_latest(self):
        """Get latest seasonal forecast information."""
        response = requests.get(f'{self.base_url}/api/seasonal/latest')
        response.raise_for_status()
        return response.json()
    
    def is_data_ready(self):
        """Check if seasonal data is ready for use."""
        data = self.get_latest()
        return data['ingestion']['status'] == 'ingested'
    
    def get_last_update_date(self):
        """Get the date of the last seasonal forecast."""
        data = self.get_latest()
        if data['ingestion']['last']:
            return datetime.strptime(data['ingestion']['last'], '%Y-%m-%d')
        return None
    
    def list_forecasts(self):
        """List available seasonal forecast folders."""
        data = self.get_latest()
        return data['folders']

# Usage
client = SeasonalDataClient('http://server:8080')

if client.is_data_ready():
    last_update = client.get_last_update_date()
    forecasts = client.list_forecasts()
    print(f"Seasonal data available from: {last_update}")
    print(f"Available forecasts: {forecasts}")
```
