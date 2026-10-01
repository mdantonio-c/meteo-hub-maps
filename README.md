# Meteo-Hub-Maps

A comprehensive meteorological data serving platform providing REST APIs, dynamic WMS services, and static tile serving for weather forecast and radar data.

## Start Here

| I want to… | Read |
| --- | --- |
| Run the project locally | [Quick Start](#quick-start) |
| Configure cache sizes, global quota or WMS-C integration | [GeoWebCache guide](docs/GWC_CACHE.md) |
| Add or change a dataset | [Dataset configuration](docs/DATASET_CONFIGURATION.md) |
| Call the API or request a WMS image | [REST API](docs/API.md) · [GeoServer WMS](docs/GEOSERVER.md#wms-services) |
| Check ingestion and service health | [Status setup](docs/STATUS_SETUP.md) · [Status quick reference](docs/STATUS_QUICKREF.md) |
| Understand the system | [Architecture](docs/ARCHITECTURE.md) |

Browse the [documentation index](docs/README.md) for all guides and data products.

## Overview

Meteo-Hub-Maps delivers multi-source meteorological data through a unified service architecture:

- **REST API** - Metadata and map images for forecast products
- **GeoServer WMS/WCS** - Dynamic, time-enabled raster layers
- **Static Tiles** - Pre-rendered map tiles via nginx
- **Automated Ingestion** - Celery-based data monitoring and processing

### Supported Data Types

| Data Type | Description | Update Frequency | Access Method |
|-----------|-------------|------------------|---------------|
| **Windy** | High-resolution forecast models (ICON, COSMO) | 2x daily (00, 12 UTC) | REST API + GeoServer |
| **Seasonal** | Long-range seasonal forecasts | Monthly | REST API |
| **Radar** | Precipitation observations (up to 1-min resolution, currently 5-min) | Real-time | GeoServer WMS |
| **Tiles** | Multi-layer forecast maps | 2x daily | Static files |

## Quick Start

### Clone the Repository

```bash
git clone https://gitlab.hpc.cineca.it/mistral/meteo-hub-maps.git
cd meteo-hub-maps
```

### Install RAPyDo Controller

```bash
sudo pip3 install --upgrade git+https://github.com/rapydo/do.git@3.0
rapydo install
```

### Initialize and Start Services

```bash
rapydo init
rapydo pull
rapydo start
```

First startup takes several minutes to build Docker images. You should see:

```
Creating maps_backend_1  ... done
Stack started
```

### Development Mode

In dev mode, start the API service manually:

```bash
rapydo shell backend --default
# Inside the backend container:
restapi run
```

### Verify Installation

Open your browser to:
```
http://localhost:8080/api/status
```

You should see: `Server is alive`

### Production Mode

In production, services start automatically and are proxied by nginx.

## Documentation

Start with the [documentation index](docs/README.md), organized by task:

- **Configuration and operations:** [GeoWebCache](docs/GWC_CACHE.md),
  [GeoServer](docs/GEOSERVER.md), [datasets](docs/DATASET_CONFIGURATION.md),
  [status setup](docs/STATUS_SETUP.md).
- **API and development:** [REST API](docs/API.md),
  [dynamic endpoints](docs/DYNAMIC_ENDPOINTS.md), [architecture](docs/ARCHITECTURE.md).
- **Data products:** [Windy](docs/WINDY_DATA.md), [radar](docs/RADAR_DATA.md),
  [seasonal](docs/SEASONAL_DATA.md), [sub-seasonal](docs/SUB_SEASONAL_DATA.md),
  [WW3](docs/WW3_DATA.md), [static tiles](docs/TILES_DATA.md).

### Cache Configuration at a Glance

| Setting | Default | Meaning |
| --- | --- | --- |
| `GWC_LAYER_QUOTA_MIB` | `1024` | Independent cache limit for each managed layer, in MiB |
| `GWC_GLOBAL_QUOTA_MIB` | Empty | Automatic: per-layer quota × current GWC layer count; set a positive MiB value to override |

These are deployment environment settings, configured through
`projects/maps/project_configuration.yaml` or local `.projectrc` overrides.
See [examples, deployment steps and verification](docs/GWC_CACHE.md).

## Key Features

### REST API Endpoints

Access via `http://<server>:8080/api/`:

- `GET /api/maps/ready` - Latest forecast metadata
- `GET /api/maps/offset/<offset>` - Forecast map images
- `GET /api/maps/legend` - Map legends
- `GET /api/windy` - Windy forecast info and data
- `GET /api/seasonal/latest` - Seasonal forecast status
- `GET /api/tiles` - Tile map reference times
- `POST /api/data/monitoring` - Start data monitoring

**API Specifications:** `GET /api/specs`

### Dynamic WMS Layers (GeoServer)

Time-enabled raster data via GeoServer:

```
http://<server>:8080/geoserver/meteohub/wms?
  service=WMS&
  request=GetMap&
  layers=meteohub:radar-sri&
  time=2025-12-01T14:35:00.000Z&
  ...
```

**Available Layers:**
- `radar-sri` - Surface rainfall intensity
- `radar-srt` - Surface rainfall type  
- `windy-icon-*` - ICON model forecasts
- Seasonal forecast layers

### Static Tile Serving

Pre-rendered tiles served by nginx for optimal performance:

```
http://<server>/tiles/<run>-<dataset>/<z>/<x>/<y>.png
```

**Example:**
```
http://server/tiles/00-lm2.2/7/67/45.png
```

## Technology Stack

- **Backend:** Python 3.x, Flask, RAPyDo
- **Task Queue:** Celery, Redis
- **Geospatial:** GeoServer 3.0.1, GeoWebCache, GDAL
- **Infrastructure:** Docker, Nginx
- **Data Formats:** GeoTIFF, PNG, WMS, WCS

## Data Organization

Forecast data is organized by platform, environment, run, and dataset:

```
/<platform>/<env>/<prefix>-<run>-<dataset>.web/
└── <area>/
    ├── <reftime>.READY
    ├── <reftime>.GEOSERVER.READY
    └── <variable>/
        └── <data files>
```

**Example:**
```
/G100/PROD/Windy-00-ICON_2I_all2km.web/
└── Italia/
    ├── 2025120100.GEOSERVER.READY
    └── t2m/
        ├── t2m.2025120100.0000.tif
        ├── t2m.2025120100.0001.tif
        └── ...
```

### Data Prefixes

- **Windy** - `Windy-<run>-<dataset>.web/`
- **Tiles** - `Tiles-<run>-<dataset>.web/`
- **Magics** - `Magics-<run>-<dataset>.web/` (forecast maps)
- **PROB** - `PROB-<run>-iff.web/` (probability/percentile)

### Status Files

- `.READY` - Data generation complete
- `.CELERY.CHECKED` - Monitoring task processed (debounce)
- `.GEOSERVER.READY` - Ingested into GeoServer

## Development

### View Logs

```bash
rapydo logs backend
rapydo logs geoserver
rapydo logs celery
```

### Shell Access

```bash
rapydo shell backend
rapydo shell geoserver
```

### Service Management

```bash
rapydo start          # Start all services
rapydo stop           # Stop all services
rapydo restart        # Restart services
rapydo status         # Check service status
```

## Monitoring

### Start Automated Monitoring

```bash
curl -X POST http://localhost:8080/api/data/monitoring
```

This creates periodic tasks to monitor:
- Windy forecast data
- Seasonal forecast data
- Radar observations

### Stop Monitoring

```bash
curl -X DELETE http://localhost:8080/api/data/monitoring
```

## Support and Links

- **GitLab:** [mistral/meteo-hub-maps](https://gitlab.hpc.cineca.it/mistral/meteo-hub-maps)
- **RAPyDo:** [rapydo/do](https://github.com/rapydo/do)
- **GeoServer:** [GeoServer Documentation](https://docs.geoserver.org/)

## License

See [LICENSE](LICENSE) file for details.
