# GeoServer Integration Documentation

This document describes the GeoServer integration architecture, configuration, and REST API interactions for dynamic map serving.

## Overview

GeoServer provides Web Map Service (WMS) and Web Coverage Service (WCS) capabilities for dynamic meteorological data. The service uses GeoServer's ImageMosaic plugin to manage time-enabled raster datasets.

## GeoServer Configuration

### Base URL

```
http://geoserver.dockerized.io:8080/geoserver
```

### Admin Credentials

Configured via environment variables:
- `GEOSERVER_ADMIN_USER`
- `GEOSERVER_ADMIN_PASSWORD`

### Workspace

All layers are published in the `meteohub` workspace.

## ImageMosaic Architecture

### What is ImageMosaic?

GeoServer's ImageMosaic plugin manages collections of georeferenced raster files (granules) as a single, queryable layer with support for:
- **Temporal Dimension:** Time-based data selection
- **Spatial Indexing:** Efficient spatial queries
- **Dynamic Mosaicking:** On-the-fly image composition

### Data Types Using ImageMosaic

1. **Windy Data** - Forecast model outputs
2. **Radar Data** - Precipitation observations
3. **Seasonal Data** - Long-range forecasts

## Layer Management

### Workspace Creation

The `meteohub` workspace is automatically created on first use:

```python
create_workspace_generic(geoserver_url, username, password)
```

**REST API Call:**
```http
POST /geoserver/rest/workspaces
Content-Type: application/json

{
  "workspace": {
    "name": "meteohub"
  }
}
```

### Store Creation

ImageMosaic stores are created by uploading a directory with configuration files:

**Store Components:**
- `indexer.properties` - Mosaic configuration
- `timeregex.properties` - Time extraction pattern (for temporal data)
- `*.tif` files - Raster granules

**REST API Call:**
```http
PUT /geoserver/rest/workspaces/meteohub/coveragestores/<store_name>/external.imagemosaic
Content-Type: text/plain

file:///opt/geoserver_data/copies/<layer_name>
```

### Layer Publication

After store creation, layers are published:

```http
POST /geoserver/rest/workspaces/meteohub/coveragestores/<store_name>/coverages
Content-Type: application/json

{
  "coverage": {
    "name": "<layer_name>",
    "nativeName": "<layer_name>",
    "title": "<layer_name>"
  }
}
```

## Time Dimension Configuration

### Enable Time Support

For temporal datasets (radar, windy):

```http
PUT /geoserver/rest/workspaces/meteohub/coveragestores/<store_name>/coverages/<layer_name>
Content-Type: application/xml

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

**Configuration Parameters:**
- `enabled`: true - Activates time dimension
- `presentation`: LIST - Returns all available times
- `units`: ISO8601 - Standard time format
- `defaultValue.strategy`: MAXIMUM - Latest time as default

### Time Extraction

Configured in `timeregex.properties`:

**Radar (DD-MM-YYYY-HH-MM.tif):**
```properties
regex=([0-9]{2}-[0-9]{2}-[0-9]{4}-[0-9]{2}-[0-9]{2}),format=dd-MM-yyyy-HH-mm
```

**Windy (variable.YYYYMMDDHH.offset.tif):**
Timestamp extracted from filename parts.

## SLD Style Management

### Style Upload

SLD (Styled Layer Descriptor) files define layer visualization:

```http
POST /geoserver/rest/styles
Content-Type: application/vnd.ogc.sld+xml

<StyledLayerDescriptor>
  ...
</StyledLayerDescriptor>
```

### Style Association

Link SLD to layer:

```http
PUT /geoserver/rest/layers/<layer_name>
Content-Type: application/json

{
  "layer": {
    "defaultStyle": {
      "name": "<style_name>"
    }
  }
}
```

### Available Styles

Radar styles are stored in `/SLDs/radar/`:

| Style Name | Purpose |
|------------|---------|
| `radar-sri` | Surface rainfall intensity |
| `radar-srt` | Surface rainfall type |
| `radar-vmi` | Vertical maximum intensity |
| `radar-hail` | Hail detection |

## Granule Lifecycle

### Adding Granules

**Method 1: Directory Upload (Initial)**
Upload entire directory to create mosaic:
```http
PUT /geoserver/rest/workspaces/meteohub/coveragestores/<store_name>/external.imagemosaic
Content-Type: text/plain

file:///opt/geoserver_data/copies/<layer_name>
```

**Method 2: Single Granule (Incremental)**
Add individual file to existing mosaic:
```http
POST /geoserver/rest/workspaces/meteohub/coveragestores/<store_name>/external.imagemosaic
Content-Type: text/plain

file:///opt/geoserver_data/copies/<layer_name>/<filename>.tif
```

**Note:** The service uses **Method 1** (reinitialization) for reliability, removing index files and re-uploading the directory.

### Querying Granules

List all granules in a mosaic:

```http
GET /geoserver/rest/workspaces/meteohub/coveragestores/<store_name>/coverages/<layer_name>/index/granules.json
```

**Response:**
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "id": "radar-sri.1",
      "properties": {
        "location": "01-12-2025-14-35.tif",
        "time": "2025-12-01T14:35:00.000Z"
      },
      "geometry": {...}
    }
  ]
}
```

### Removing Granules

Delete by granule ID:

```http
DELETE /geoserver/rest/workspaces/meteohub/coveragestores/<store_name>/coverages/<layer_name>/index/granules/<granule_id>.json
```

Delete by filter (location):

```http
DELETE /geoserver/rest/workspaces/meteohub/coveragestores/<store_name>/coverages/<layer_name>/index/granules?filter=location='<filename>.tif'
```

## Mosaic Reinitialization

For radar incremental updates, the service uses a reinitialization strategy:

### Process

1. **Copy New File** - Add new granule to mosaic directory
2. **Remove Index Files** - Delete `.shp`, `.dbf`, `.properties`, etc.
3. **Recreate Config** - Regenerate `indexer.properties` and `timeregex.properties`
4. **Reinitialize Mosaic** - Upload directory again (forces reindexing)
5. **Reapply Settings** - Reconfigure time dimension and SLD

### Why Reinitialize?

- **Reliability:** Ensures index consistency
- **Simplicity:** Avoids complex granule API edge cases
- **Time Dimension:** Forces proper time range recalculation

### Performance Impact

Minimal for small mosaics (< 5000 granules). GeoServer efficiently rebuilds indexes.

## WMS Services

### GetCapabilities

Discover available layers and dimensions:

```http
GET /geoserver/meteohub/wms?service=WMS&version=1.1.0&request=GetCapabilities
```

### GetMap

Retrieve map image:

```http
GET /geoserver/meteohub/wms?
  service=WMS&
  version=1.1.0&
  request=GetMap&
  layers=meteohub:radar-sri&
  time=2025-12-01T14:35:00.000Z&
  bbox=6.0,36.0,19.0,47.0&
  width=800&
  height=600&
  srs=EPSG:4326&
  format=image/png&
  styles=radar-sri
```

**Time Parameter:**
- Single time: `time=2025-12-01T14:35:00.000Z`
- Time range: `time=2025-12-01T00:00:00.000Z/2025-12-01T23:59:59.000Z`
- Latest: Omit time parameter (uses MAXIMUM strategy)

### GetFeatureInfo

Query pixel values:

```http
GET /geoserver/meteohub/wms?
  service=WMS&
  version=1.1.0&
  request=GetFeatureInfo&
  layers=meteohub:radar-sri&
  query_layers=meteohub:radar-sri&
  time=2025-12-01T14:35:00.000Z&
  bbox=6.0,36.0,19.0,47.0&
  width=800&
  height=600&
  x=400&
  y=300&
  srs=EPSG:4326&
  info_format=application/json
```

## Data Directory Structure

GeoServer data is stored on the server:

```
/geoserver_data/
└── copies/
    ├── radar-sri/
    │   ├── 01-12-2025-14-35.tif
    │   ├── 01-12-2025-14-36.tif
    │   ├── indexer.properties
    │   ├── timeregex.properties
    │   └── radar-sri.shp  (auto-generated index)
    ├── radar-srt/
    │   └── ...
    └── windy-icon-00/
        └── ...
```

### Container Path Mapping

- **Host Path:** `/geoserver_data/copies/`
- **Container Path:** `/opt/geoserver_data/copies/`

File URLs in REST API calls must use the container path.

## Monitoring and Health

### GeoServer Status

Check GeoServer health:

```http
GET /geoserver/rest/about/status
```

### Layer Status

Verify layer exists:

```http
GET /geoserver/rest/workspaces/meteohub/coveragestores/<store_name>/coverages/<layer_name>.json
```

### Granule Count

Get number of granules:

```bash
curl -u admin:password \
  'http://geoserver:8080/geoserver/rest/workspaces/meteohub/coveragestores/mosaic_radar-sri/coverages/radar-sri/index/granules.json' \
  | jq '.features | length'
```

## Troubleshooting

### Layer Not Appearing

1. Check workspace exists: `GET /geoserver/rest/workspaces/meteohub`
2. Check store exists: `GET /geoserver/rest/workspaces/meteohub/coveragestores/<store_name>`
3. Check layer published: `GET /geoserver/rest/workspaces/meteohub/coveragestores/<store_name>/coverages`
4. Review GeoServer logs

### Time Dimension Not Working

1. Verify `timeregex.properties` exists and is correct
2. Check time dimension enabled in layer configuration
3. Test GetCapabilities to see if time dimension is advertised
4. Ensure filenames match time regex pattern

### No Data Returned

1. Check granules exist: `GET .../index/granules.json`
2. Verify time parameter matches available times
3. Confirm bbox overlaps with data extent
4. Test with known working time value

### Slow Performance

1. Check granule count (consider cleanup if > 10,000)
2. Enable GeoServer tile caching (GeoWebCache)
3. Review mosaic index (may need spatial index rebuild)
4. Monitor GeoServer memory usage

## Best Practices

### Granule Management

- Maintain reasonable granule counts (< 10,000 per mosaic)
- Implement retention policies (e.g., 72-hour window for radar)
- Regularly clean up old data

### Configuration

- Use container paths in REST API calls
- Store SLD files separately and version control
- Document custom time extraction patterns

### Performance

- Enable GeoWebCache for frequently accessed layers
- Use appropriate image formats (PNG for transparency, JPEG for opaque)
- Configure connection pooling for data stores

### Security

- Restrict REST API access (IP-based or authentication)
- Use HTTPS in production
- Regularly rotate admin credentials
