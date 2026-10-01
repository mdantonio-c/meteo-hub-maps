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

### HTTPS login behind Nginx

The host proxy configurations are `projects/maps/builds/host_nginx.config`
(production) and `projects/maps/builds/host_nginx_dev.config` (development).
Deploy the appropriate configuration to the host's active Nginx site, then run
`sudo nginx -t && sudo systemctl reload nginx`.

Both the HTML form action and the authentication response's `Location` header
must stay on the public HTTPS origin. `sub_filter` rewrites HTML URLs;
`proxy_redirect` rewrites redirect headers. Rewriting only the HTML is
insufficient: Spring Security can redirect an HTTPS login POST to HTTP, which
the browser blocks under `form-action 'self'`.

Check the development site's redirect without following it:

```bash
curl -sSI https://meteohub-maps.hpc.cineca.it/geoserver/web/
```

Its `Location` must be HTTPS (or a relative URL), never
`http://meteohub-maps.hpc.cineca.it/...`. After reloading the site, use the browser
Network panel to check that the login POST's redirect also stays on HTTPS.

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

The container health check uses GeoServer's lightweight web UI asset endpoint. It
checks that the application is answering without rendering a raster on every
probe. In the production profile, `healthwatch` restarts only GeoServer when its
health check remains unhealthy; Celery's ingestion-failure marker is handled by
restarting the Celery worker, so ingestion problems do not unnecessarily interrupt
map requests. Docker itself does not restart a running container solely because
it becomes unhealthy, which is why the healthwatch service is kept enabled.
The published `8081` port is bound to loopback; external clients should use the
TLS reverse proxy, while services on the Compose network continue to use the
internal GeoServer hostname and port. GeoServer is allowed two minutes to shut
down cleanly so in-flight requests have time to finish during a restart.

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

### Production Capacity and Availability

- The production JVM heap is configured through the OSGeo image's
  `EXTRA_JAVA_OPTS` with a 4 GiB initial and 8 GiB maximum
  heap. Size the host for the heap plus JVM native memory, raster/rendering
  buffers, the OS, and other containers; do not deploy this profile on a host
  with less than 12 GiB available to GeoServer and its runtime overhead.
- Avoid setting a CPU or memory limit below the JVM's configured requirements.
  Watch heap occupancy, GC pauses, CPU saturation, open file descriptors, and
  request latency under representative concurrent WMS load before increasing
  worker or cache-seeding concurrency.
- A single GeoServer container on one host is not highly available: host, disk,
  network, or shared data-directory failures still take the service offline. For
  host-level HA, deploy multiple GeoServer instances behind a load balancer with
  health-based routing, use a supported shared GeoServer data directory and
  coordinated configuration updates, and keep the GeoWebCache strategy consistent
  across instances. Never let independent instances concurrently mutate an
  unsupported shared catalog/data directory.
- Use durable, monitored storage for `/opt/geoserver_data` and maintain tested
  backups of the catalog and data. Container restart recovery cannot recover a
  lost or corrupt data volume.

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
## Direct WMS-C Integration

Worker startup initialization enables **Enable direct WMS-C integration with
GeoServer WMS** by default, persisting `directWMSIntegrationEnabled=true` in
`gwc-gs.xml`. GeoServer is reloaded only when this setting changes. Other GWC
global settings are preserved.

## Per-layer Cache Disk Quotas

Startup initialization enables GWC disk quota enforcement and assigns each
layer in the configured workspace an independent quota with **LRU** (least
recently used) eviction. Set `GWC_LAYER_QUOTA_MIB` in project configuration or
an environment override to specify the per-layer limit in MiB. The default is
`1024` MiB (**1 GiB / 1,073,741,824 bytes**); the value must be a positive integer.
For example, `GWC_LAYER_QUOTA_MIB=512` limits each layer to 512 MiB. Recreate
backend and worker containers after changing the environment configuration.
Newly ingested layers receive the same quota when their GWC layer configuration
is initialized.

The settings are persisted in `gwc/geowebcache-diskquota.xml` through the
GeoServer resource API. GeoServer is reloaded only when quota settings change;
existing cleanup scheduling and unrelated layer quotas are preserved.

Set `GWC_GLOBAL_QUOTA_MIB` to a positive integer to specify the global quota in
MiB, for example `GWC_GLOBAL_QUOTA_MIB=8192`. When unset or empty (the default),
the global quota is calculated as `GWC_LAYER_QUOTA_MIB × number of current GWC
layers`, including layers in other workspaces. The live GWC catalog is queried
on quota checks so additions and removals update the calculated limit, including
when only one layer is being configured. With 512 MiB per layer and 10 cached
layers, the automatic global quota is 5120 MiB; an empty catalog yields 0 MiB.

GWC applies the global quota to layers without explicit per-layer quotas.
Explicit per-layer quotas are independent of it, so the global setting is not
an aggregate hard limit on all layer caches.

Quota cleanup is periodic (every 10 seconds on a fresh configuration), so disk
usage can temporarily exceed the configured limit during seeding or heavy
requests. The quota
covers all cached times, styles, formats and gridsets for a layer together.
