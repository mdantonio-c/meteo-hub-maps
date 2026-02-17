# Meteo-Hub-Maps

A comprehensive meteorological data serving platform providing REST APIs, dynamic WMS services, and static tile serving for weather forecast and radar data.

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
git checkout 0.6

### Install RAPyDo Controller

```bash
sudo pip3 install --upgrade git+https://github.com/rapydo/do.git@3.0
rapydo install

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

Comprehensive documentation is available in the [`docs/`](docs/) directory:

- **[API Reference](docs/API.md)** - Complete REST API documentation
- **[Windy Data](docs/WINDY_DATA.md)** - Forecast model data (ICON, COSMO)
- **[Seasonal Data](docs/SEASONAL_DATA.md)** - Long-range forecasts
- **[Radar Data](docs/RADAR_DATA.md)** - Precipitation observations
- **[Tiles Data](docs/TILES_DATA.md)** - Static tile serving
- **[GeoServer Integration](docs/GEOSERVER.md)** - WMS/WCS configuration
- **[Architecture](docs/ARCHITECTURE.md)** - System design and components

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
- **Geospatial:** GeoServer 2.26.x, GDAL
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
