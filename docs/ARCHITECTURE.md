# Service Architecture Documentation

This document provides an overview of the Meteo-Hub-Maps service architecture, components, and data flow.

## System Overview

The Meteo-Hub-Maps service is a comprehensive meteorological data serving platform that provides:
- REST API for forecast metadata and map images
- GeoServer WMS/WCS for dynamic raster data
- Static tile serving for pre-rendered maps
- Automated data ingestion and monitoring

## Technology Stack

### Backend Services

- **Python 3.x** - Core application language
- **Flask** - Web framework for REST API
- **RAPyDo** - Development and deployment framework
- **Celery** - Distributed task queue for background jobs
- **Redis** - Message broker for Celery
- **PostgreSQL** - Relational database (if needed)

### Geospatial Services

- **GeoServer 2.26.x** - WMS/WCS map server
- **GDAL** - Geospatial data abstraction library
- **ImageMosaic Plugin** - Time-enabled raster management

### Infrastructure

- **Docker** - Container orchestration
- **Nginx** - Static file serving and reverse proxy
- **Rapydo CLI** - Service management

## Component Architecture

```mermaid
graph TB
    subgraph "Client Applications"
        A[Web Browser]
        B[Mobile App]
        C[GIS Software]
    end
    
    subgraph "API Layer"
        D[Nginx Reverse Proxy]
        E[Flask REST API]
    end
    
    subgraph "Processing Layer"
        F[Celery Workers]
        G[Redis Broker]
    end
    
    subgraph "Data Services"
        H[GeoServer WMS/WCS]
        I[Nginx Static Files]
    end
    
    subgraph "Storage"
        J[File System]
        K[GeoServer Data Dir]
    end
    
    A --> D
    B --> D
    C --> D
    
    D --> E
    D --> H
    D --> I
    
    E --> F
    F --> G
    F --> H
    F --> J
    F --> K
    
    H --> K
    I --> J
    
    style E fill:#4A90E2
    style F fill:#7ED321
    style H fill:#F5A623
```

## Data Flow

### 1. Forecast Data Ingestion (Windy)

```mermaid
sequenceDiagram
    participant Model as Forecast Model
    participant FS as File System
    participant Celery as Celery Worker
    participant GS as GeoServer
    participant API as REST API
    
    Model->>FS: Write GeoTIFF files
    Model->>FS: Create .READY file
    
    loop Every minute
        Celery->>FS: Check for .READY files
    end
    
    Celery->>FS: Find new data
    Celery->>FS: Create .CELERY.CHECKED
    Celery->>GS: Upload ImageMosaic
    GS->>GS: Create time-enabled layer
    Celery->>FS: Create .GEOSERVER.READY
    
    API->>FS: Check .GEOSERVER.READY
    API-->>API: Return latest reftime
```

### 2. Radar Data Ingestion (Batch)

```mermaid
sequenceDiagram
    participant Radar as Radar System
    participant FS as File System
    participant Celery as Celery Worker
    participant GS as GeoServer
    
    loop Every minute
        Radar->>FS: Write 1-minute GeoTIFF
    end
    
    Radar->>FS: Create .READY file
    
    Celery->>FS: Detect new .READY
    Celery->>FS: Find pending files<br/>(not in GeoServer)
    Celery->>FS: Create .CELERY.CHECKED
    
    loop For each pending file
        Celery->>FS: Copy to GeoServer dir
    end
    
    Celery->>FS: Remove index files
    Celery->>GS: Reinitialize mosaic
    GS->>GS: Rebuild spatial index
    GS->>GS: Update time dimension
    
    alt Time range > 72h
        Celery->>GS: Remove oldest granules
        Celery->>FS: Delete old .tif files
    end
    
    Celery->>FS: Create date-range<br/>.GEOSERVER.READY
```

### 3. Map Request Flow

```mermaid
sequenceDiagram
    participant Client
    participant API as REST API
    participant FS as File System
    participant GS as GeoServer
    
    Client->>API: GET /api/maps/ready
    API->>FS: Find latest .READY file
    API->>FS: Read offsets
    API-->>Client: Return metadata
    
    Client->>API: GET /api/maps/offset/0012
    API->>FS: Read PNG image
    API-->>Client: Return image
    
    Client->>GS: WMS GetMap (radar)
    GS->>GS: Query by time
    GS->>GS: Apply SLD style
    GS-->>Client: Return rendered image
```

## Directory Structure

```
/home/dcrisant/Documents/MISTRAL/meteo-hub-maps/
├── projects/
│   └── maps/
│       ├── backend/
│       │   ├── endpoints/      # REST API endpoints
│       │   │   ├── maps.py
│       │   │   ├── windy.py
│       │   │   ├── seasonal.py
│       │   │   ├── tiles.py
│       │   │   ├── dataready.py
│       │   │   └── config.py
│       │   ├── tasks/          # Celery tasks
│       │   │   ├── check_fs_data.py
│       │   │   ├── radar.py
│       │   │   ├── data_ready.py
│       │   │   ├── upload_image_mosaic.py
│       │   │   └── geoserver_utils.py
│       │   └── utils/
│       ├── builds/
│       │   └── geoserver/
│       │       └── SLDs/       # Style files
│       └── confs/              # Configuration
├── data/                       # Data mount point
│   ├── G100/
│   │   └── PROD/
│   │       ├── Windy-00-ICON_2I_all2km.web/
│   │       ├── Windy-12-ICON_2I_all2km.web/
│   │       ├── Tiles-00-lm2.2.web/
│   │       └── Magics-00-lm2.2.web/
│   └── leonardo/
├── geoserver_data/             # GeoServer data
│   └── copies/
│       ├── radar-sri/
│       ├── radar-srt/
│       └── windy-icon-00/
└── docs/                       # Documentation
    ├── API.md
    ├── WINDY_DATA.md
    ├── SEASONAL_DATA.md
    ├── RADAR_DATA.md
    ├── TILES_DATA.md
    ├── GEOSERVER.md
    └── ARCHITECTURE.md
```

## Key Components

### REST API Endpoints

Located in `projects/maps/backend/endpoints/`:

| Endpoint | File | Purpose |
|----------|------|---------|
| `/api/maps/*` | `maps.py` | Forecast map images and metadata |
| `/api/windy` | `windy.py` | Windy forecast data info |
| `/api/seasonal/latest` | `seasonal.py` | Seasonal forecast status |
| `/api/tiles` | `tiles.py` | Tile map metadata |
| `/api/data/monitoring` | `dataready.py` | Start/stop monitoring tasks |

### Celery Tasks

Located in `projects/maps/backend/tasks/`:

| Task | File | Purpose |
|------|------|---------|
| `check_latest_data_and_trigger_geoserver_import_windy` | `check_fs_data.py` | Monitor windy data |
| `check_latest_data_and_trigger_geoserver_import_seasonal` | `check_fs_data.py` | Monitor seasonal data |
| `check_latest_data_and_trigger_geoserver_import_radar` | `check_fs_data.py` | Monitor radar data |
| `update_geoserver_radar_layers` | `radar.py` | Ingest radar batch |
| `update_geoserver_image_mosaic` | `upload_image_mosaic.py` | Ingest windy data |
| `update_geoserver_seasonal_layers` | `data_ready.py` | Ingest seasonal data |

### GeoServer Utilities

Located in `projects/maps/backend/tasks/geoserver_utils.py`:

- `create_workspace_generic()` - Create workspace
- `upload_geotiff_generic()` - Upload ImageMosaic
- `publish_layer_generic()` - Publish coverage
- `associate_sld_with_layer_generic()` - Apply styles
- `update_slds_from_local_folders()` - Sync SLD files

## Deployment

### Development Mode

```bash
# Clone repository
git clone https://gitlab.hpc.cineca.it/mistral/meteo-hub-maps.git
cd meteo-hub-maps

# Install RAPyDo controller
sudo pip3 install --upgrade git+https://github.com/rapydo/do.git@2.4

# Initialize and start
rapydo install
rapydo init
rapydo pull
rapydo start

# Start API manually (dev mode)
rapydo shell backend --default
```

### Production Mode

```bash
# API service starts automatically
rapydo start

# Nginx proxies requests
# http://server:8080/api -> Flask backend
# http://server:8080/geoserver -> GeoServer
```

### Service Management

```bash
# Start all services
rapydo start

# Stop services
rapydo stop

# View logs
rapydo logs backend
rapydo logs geoserver

# Shell access
rapydo shell backend
rapydo shell geoserver
```

## Scaling Considerations

### Horizontal Scaling

- **API Service:** Scale Flask workers behind load balancer
- **Celery Workers:** Add worker instances for parallel processing
- **GeoServer:** Cluster with shared data directory

### Caching

- **API Responses:** Enable Flask-Caching with Redis
- **GeoServer:** Enable GeoWebCache for WMS tiles
- **Static Files:** CDN for tile serving

### Data Management

- **Archival:** Move old forecast runs to cold storage
- **Cleanup:** Automated deletion of expired data
- **Partitioning:** Separate data by platform/environment

## Monitoring and Observability

### Health Checks

- **API:** `GET /api/status` - Returns "Server is alive"
- **GeoServer:** `GET /geoserver/rest/about/status`
- **Celery:** Monitor task queue depth in Redis

### Logging

- **Flask:** Application logs in `backend` container
- **Celery:** Task logs with correlation IDs
- **GeoServer:** WMS request logs

### Metrics

Key metrics to monitor:
- API response times
- Celery task duration
- GeoServer WMS request latency
- Disk usage (data directories)
- Granule counts per mosaic

## Security

### Authentication

- IP-based restrictions on `/api/data/*` endpoints
- GeoServer admin credentials via environment variables
- No authentication on public data endpoints

### Network

- Internal Docker network for service communication
- Nginx reverse proxy for external access
- CORS headers for browser clients

## Future Enhancements

Potential improvements:
- **Caching:** Implement Redis-based API caching
- **Async Processing:** Long-running tasks with WebSocket updates
- **Versioning:** API version management
- **Real-time Updates:** WebSocket notifications for new data
- **User Management:** Authentication for restricted datasets
