# REST API Documentation

This document provides comprehensive documentation for all REST API endpoints exposed by the Meteo-Hub-Maps service.

## Base URL

```
http://<server>:8080/api
```

## API Specifications

The complete OpenAPI specifications are available at:
```
GET /api/specs
```

---

## Maps Endpoints

### Get Map Set Reference Time

Retrieve the last available map set for a specific run, returning the reference time and available offsets.

**Endpoint:** `GET /api/maps/ready`

**Parameters:**

| Parameter | Type | Required | Values | Description |
|-----------|------|----------|--------|-------------|
| `run` | string | Yes | `00`, `12` | Forecast run hour |
| `res` | string | Yes | `lm2.2`, `lm5`, `WRF_OL`, `WRF_DA_ITA`, `icon` | Model resolution |
| `field` | string | Yes | `prec1`, `prec3`, `prec6`, `prec12`, `prec24`, `t2m`, `wind`, `cloud`, `pressure`, `cloud_hml`, `humidity`, `snow1`, `snow3`, `snow6`, `snow12`, `snow24`, `percentile`, `probability` | Meteorological field |
| `area` | string | Yes | `Italia`, `Nord_Italia`, `Centro_Italia`, `Sud_Italia`, `Area_Mediterranea` | Geographic area |
| `platform` | string | No | `G100`, `leonardo` | Computing platform (auto-detected if not provided) |
| `level_pe` | string | No | `1`, `10`, `25`, `50`, `70`, `75`, `80`, `90`, `95`, `99` | Percentile level (for `percentile` field) |
| `level_pr` | string | No | `5`, `10`, `20`, `50` | Probability threshold (for `probability` field) |
| `weekday` | string | No | `0`-`6` | Day of week (0=Monday) |
| `env` | string | No | `PROD`, `DEV` | Environment (default: `PROD`) |

**Response:** `200 OK`

```json
{
  "reftime": "2025120100",
  "offsets": ["0000", "0001", "0002", "..."],
  "platform": "G100",
  "weekday": "0"
}
```

**Error Responses:**
- `400 Bad Request` - Invalid parameters
- `404 Not Found` - Map set does not exist
- `503 Service Unavailable` - Platform unavailable

---

### Get Forecast Map Image

Retrieve a specific forecast map image for a given offset.

**Endpoint:** `GET /api/maps/offset/<map_offset>`

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `map_offset` | string | Time offset (e.g., `0000`, `0012`, `0024`) |

**Query Parameters:** Same as `/api/maps/ready`

**Response:** `200 OK`

Returns PNG image with `Content-Type: image/png`

**Error Responses:**
- `400 Bad Request` - Invalid parameters
- `404 Not Found` - Map image does not exist

---

### Get Map Legend

Retrieve the legend for a specific forecast field.

**Endpoint:** `GET /api/maps/legend`

**Parameters:** Same as `/api/maps/offset/<offset>`

**Response:** `200 OK`

Returns PNG image with `Content-Type: image/png`

**Error Responses:**
- `400 Bad Request` - Invalid parameters
- `404 Not Found` - Legend does not exist

---

## Wind Direction Endpoints

### List Wind Direction Files

Retrieve a list of available static wind direction GeoTIFF files for the most recent run. The service automatically identifies the latest available run (00 or 12) using `.READY` files.

**Endpoint:** `GET /api/maps/wind-direction/list/files`

**Response:** `200 OK`

```json
[
  "wind_direction_00.tif",
  "wind_direction_01.tif",
  "..."
]
```

**Error Responses:**
- `404 Not Found` - No `.READY` files found for any run

---

### Get Wind Direction File

Download a specific static wind direction GeoTIFF file from the `wind-direction` subfolder of the most recent run.

**Endpoint:** `GET /api/maps/wind-direction/files/<filename>`

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `filename` | string | Name of the file to retrieve (e.g., `wind_direction_00.tif`) |

**Response:** `200 OK`

Returns GeoTIFF file with `Content-Type: image/tiff`

**Error Responses:**
- `404 Not Found` - File not found or no `.READY` files found

---

## Windy Endpoint

### Get Windy Data Information

Get the last available windy map set or download specific data files.

**Endpoint:** `GET /api/windy`

**Parameters:**

| Parameter | Type | Required | Values | Description |
|-----------|------|----------|--------|-------------|
| `dataset` | string | Yes | `lm5`, `lm2.2`, `iff`, `icon` | Dataset identifier |
| `run` | string | No | `00`, `12` | Forecast run (auto-detected if not provided) |
| `foldername` | string | No | - | Folder name within the dataset |
| `filename` | string | No | - | Specific file to download |

**Response (without foldername/filename):** `200 OK`

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

**Response (with foldername/filename):** GeoTIFF file download

**Error Responses:**
- `400 Bad Request` - Invalid parameters
- `404 Not Found` - Dataset or file not found

---

## Seasonal Endpoint

### Get Latest Seasonal Data

Retrieve information about the latest available seasonal forecast data.

**Endpoint:** `GET /api/seasonal/latest`

**Response:** `200 OK`

```json
{
  "folders": ["folder1", "folder2"],
  "ingestion": {
    "last": "2025-12-01",
    "status": "ingested"
  }
}
```

**Ingestion Status Values:**
- `ingested` - Data successfully processed by GeoServer
- `ingesting` - Data processing in progress
- `null` - No data available

**Error Responses:**
- `404 Not Found` - Seasonal data directory not found

### List Seasonal Boxplot Files

List all files in the seasonal boxplot folder.

**Endpoint:** `GET /api/seasonal/json`

**Response:** `200 OK`

```json
[
  "file1.json",
  "file2.json"
]
```

**Error Responses:**
- `404 Not Found` - Boxplot folder not found

### Get Seasonal Boxplot File

Retrieve a specific file from the seasonal boxplot folder.

**Endpoint:** `GET /api/seasonal/json/<filename>`

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `filename` | string | Yes | Name of the file to retrieve |

**Response:** `200 OK`

Returns the file content.

**Error Responses:**
- `404 Not Found` - File not found

---

## Sub-Seasonal Endpoint

### Get Latest Sub-Seasonal Data

Retrieve information about the latest available sub-seasonal forecast data.

**Endpoint:** `GET /api/sub-seasonal/latest`

**Response:** `200 OK`

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

**Error Responses:**
- `404 Not Found` - Sub-seasonal data directory not found

---

## Tiles Endpoint

### Get Tiles Reference Time

Get the last available tiled map set reference time.

**Endpoint:** `GET /api/tiles`

**Parameters:**

| Parameter | Type | Required | Values | Description |
|-----------|------|----------|--------|-------------|
| `dataset` | string | Yes | `lm5`, `lm2.2`, `iff`, `icon` | Dataset identifier |
| `run` | string | No | `00`, `12` | Forecast run (auto-detected if not provided) |

**Response:** `200 OK`

```json
{
  "dataset": "lm5",
  "area": "Area_Mediterranea",
  "start_offset": 0,
  "end_offset": 72,
  "step": 1,
  "boundaries": {
    "SW": [25.8, -30.9],
    "NE": [55.5, 47.0]
  },
  "reftime": "2025120100",
  "platform": null
}
```

**Error Responses:**
- `400 Bad Request` - Invalid parameters
- `404 Not Found` - No tiles data available

---

## Radar Endpoints

### Get Radar Status

Retrieve metadata about the last ingested radar data chunk, including time range, last update timestamp, and pending import information.

**Endpoint:** `GET /api/radar/{radar_type}/status`

**Path Parameters:**

| Parameter | Type | Required | Values | Description |
|-----------|------|----------|--------|-------------|
| `radar_type` | string | Yes | `sri`, `srt` | Type of radar data |

**Response (with completed import):** `200 OK`

```json
{
  "from": "2025-11-22T11:35:00Z",
  "to": "2025-11-25T11:35:00Z",
  "interval": "5m",
  "meta": {
    "lastUpdate": "2025-12-02T10:08:07.832427Z",
    "pendingImport": null
  }
}
```

**Response (with pending import):** `200 OK`

```json
{
  "from": "2025-11-22T11:35:00Z",
  "to": "2025-11-25T11:35:00Z",
  "interval": "5m",
  "meta": {
    "lastUpdate": "2025-12-02T10:08:07.832427Z",
    "pendingImport": {
      "status": "pending",
      "file": "202511251135-202511271135.CELERY.CHECKED",
      "from": "2025-11-25T11:35:00",
      "to": "2025-11-27T11:35:00",
      "detectedAt": "2025-12-02T11:00:00",
      "estimatedFinishSeconds": "8"
    }
  }
}
```

**Response (no GEOSERVER.READY, only pending):** `200 OK`

```json
{
  "from": null,
  "to": null,
  "interval": "5m",
  "meta": {
    "lastUpdate": null,
    "pendingImport": {
      "status": "pending",
      "file": "202511221135-202511251135.CELERY.CHECKED",
      "from": "2025-11-22T11:35:00",
      "to": "2025-11-25T11:35:00",
      "detectedAt": "2025-12-02T10:05:00",
      "estimatedFinishSeconds": "10"
    }
  }
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `from` | string/null | Start time of the radar data range (ISO 8601 format with Z suffix), null if no data ingested yet |
| `to` | string/null | End time of the radar data range (ISO 8601 format with Z suffix), null if no data ingested yet |
| `interval` | string | Time interval between radar frames (always "5m" for 5 minutes) |
| `meta.lastUpdate` | string/null | Timestamp when the data was last processed by GeoServer (ISO 8601 format with Z suffix) |
| `meta.pendingImport` | object/null | Information about pending data import, null if no pending import |
| `meta.pendingImport.status` | string | Import status (always "pending") |
| `meta.pendingImport.file` | string | Name of the CELERY.CHECKED file detected |
| `meta.pendingImport.from` | string | Start time of the pending data range (ISO 8601 format) |
| `meta.pendingImport.to` | string | End time of the pending data range (ISO 8601 format) |
| `meta.pendingImport.detectedAt` | string | Timestamp when the pending import was detected (ISO 8601 format) |
| `meta.pendingImport.estimatedFinishSeconds` | string | Estimated seconds until import completion (uses logarithmic scaling: 6s for small batches, up to 14s for large batches) |

**Error Responses:**
- `400 Bad Request` - Invalid radar type (must be 'sri' or 'srt')
- `404 Not Found` - No radar data available (no GEOSERVER.READY or CELERY.CHECKED files found)

**Notes:**

- The endpoint checks for `.GEOSERVER.READY` files to get the currently available data range
- It also checks for `.CELERY.CHECKED` files to detect pending imports
- When only a pending import exists (no GEOSERVER.READY), the response returns `null` for `from`, `to`, and `lastUpdate`
- The `estimatedFinishSeconds` calculation uses logarithmic scaling based on the number of 5-minute intervals to process

**Examples:**

Get status for SRI (Surface Rain Intensity) radar:
```bash
curl "http://localhost:8080/api/radar/sri/status"
```

Get status for SRT (Surface Rain Total) radar:
```bash
curl "http://localhost:8080/api/radar/srt/status"
```

---

## WW3 Endpoints

### Get WW3 Status

Get the status and availability of the WW3 dataset.

**Endpoint:** `GET /api/ww3/status`

**Response:** `200 OK`

```json
{
  "reftime": "2025120300",
  "start_offset": 0,
  "end_offset": 72,
  "step": 1,
  "dataset": "ww3"
}
```

**Error Responses:**
- `404 Not Found` - Run not found

---

### List WW3 Vector Files

List available WW3 vector files (JSON format).

**Endpoint:** `GET /api/ww3/vectors`

**Response:** `200 OK`

```json
[
  "20251203_00.json",
  "20251203_01.json",
  "..."
]
```

**Error Responses:**
- `404 Not Found` - Vectors folder not found

---

### Get WW3 Vector File

Retrieve the content of a specific WW3 vector file.

**Endpoint:** `GET /api/ww3/vectors/<filename>`

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `filename` | string | Yes | Name of the vector file (e.g., `20251203_00.json`) |

**Response:** `200 OK`

Returns the JSON content of the vector file.

**Error Responses:**
- `404 Not Found` - File not found

---

## Data Monitoring Endpoints

### Start Data Monitoring

Start periodic Celery tasks to monitor data directories and trigger GeoServer imports.

**Endpoint:** `POST /api/data/monitoring`

**Response:** `202 Accepted`

```json
"Monitoring started"
```

This creates periodic tasks for:
- Windy data monitoring
- Seasonal data monitoring
- Radar data monitoring
- Sub-seasonal data monitoring

---

### Stop Data Monitoring

Stop all periodic monitoring tasks.

**Endpoint:** `DELETE /api/data/monitoring`

**Response:** `202 Accepted`

```json
"Monitoring has been disabled"
```

or

```json
"Monitoring is not active"
```

---

## Status Endpoint

### Health Check

Check if the API service is running.

**Endpoint:** `GET /api/status`

**Response:** `200 OK`

```
Server is alive
```

---

## Notes

### Authentication

Most endpoints are publicly accessible. Some administrative endpoints (e.g., `/api/data/monitoring`, `/api/data/ready`) are IP-restricted.

### Caching

Endpoints may be cached with a 900-second (15-minute) timeout. Cache decorators are currently commented out in the code but can be enabled for production.

### Data Availability

The availability of data depends on:
1. Successful completion of forecast model runs
2. Data transfer to the server
3. Processing and creation of `.READY` files
4. GeoServer ingestion for dynamic data types

### Platform Selection

When `platform` parameter is not specified for maps endpoints, the service automatically selects the platform with the most recent available data, checking in order: G100 (default), leonardo.
