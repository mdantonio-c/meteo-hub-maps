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
