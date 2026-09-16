# AGENTS.md - Meteo-Hub-Maps

## Project Overview

Meteorological data serving platform built on **RAPyDo 3.0** framework. Provides:
- REST API (Flask) for forecast metadata and map images
- GeoServer 2.26.x WMS/WCS for dynamic raster layers
- Celery + Redis for automated data ingestion
- Static tile serving via nginx

**GitLab:** https://gitlab.hpc.cineca.it/mistral/meteo-hub-maps

## Quick Start Commands

```bash
# Install RAPyDo controller (required)
sudo pip3 install --upgrade git+https://github.com/rapydo/do.git@3.0

# Initialize and start all services
rapydo install      # First-time setup
rapydo init         # Initialize project config
rapydo pull         # Build/pull Docker images
rapydo start        # Start all services
```

First startup takes several minutes. Verify with:
```bash
curl http://localhost:8080/api/status  # Should return "Server is alive"
```

## Development Workflow

### Dev Mode (manual API start)
```bash
rapydo shell backend --default
# Inside container: restapi run
```

### Production Mode (auto-start services)
```bash
rapydo --testing --prod init --force
rapydo ssl --volatile
rapydo start
```

### Service Management
```bash
rapydo stop          # Stop all
rapydo restart       # Restart all
rapydo status        # Check status
rapydo logs backend  # View backend logs
rapydo logs geoserver
rapydo logs celery
rapydo shell backend # Shell access
rapydo shell geoserver
```

## Testing

### Run Tests (CI workflow)
```bash
rapydo pull --quiet
rapydo start
rapydo shell backend 'restapi wait'
rapydo shell backend 'restapi tests --wait --destroy'
```

Tests use `pytest` with fixtures in `projects/maps/backend/tests/`. Test data paths are mocked to `/tmp/` for cleanup.

### Code Quality
```bash
# Linting (flake8)
flake8 projects/maps/backend/

# Formatting (black, isort)
black projects/maps/backend/
isort projects/maps/backend/

# Type checking (mypy)
rapydo --testing --prod mypy
```

Config: `.flake8`, `pyproject.toml` (black/isort)

## Architecture

### Directory Structure
```
/
├── projects/maps/
│   ├── backend/
│   │   ├── endpoints/      # REST API (maps.py, windy.py, seasonal.py, etc.)
│   │   ├── tasks/          # Celery tasks (data ingestion, GeoServer ops)
│   │   ├── utils/          # Helpers
│   │   └── tests/          # pytest suites
│   ├── builds/geoserver/   # GeoServer Docker + SLD styles
│   └── confs/              # RAPyDo configs (development.yml, production.yml)
├── data/                   # Mounted data volumes (GeoTIFFs, GeoServer data dir)
├── docs/                   # API, architecture, data type documentation
└── .env                    # Environment overrides (RAPyDo)
```

### Key Components

**REST API Endpoints** (`projects/maps/backend/endpoints/`):
- `/api/maps/*` - Forecast map images and metadata
- `/api/windy` - Windy forecast data (ICON, COSMO, WRF models)
- `/api/seasonal/*` - Long-range forecasts
- `/api/sub-seasonal/*` - Sub-seasonal forecasts
- `/api/marine/shyfem/*` - Marine model data (BOLAM, ECMWF, ICON)
- `/api/tiles` - Static tile metadata
- `/api/data/monitoring` - Start/stop Celery monitoring

**Celery Tasks** (`projects/maps/backend/tasks/`):
- `check_fs_data.py` - Monitor filesystem for `.READY` markers
- `radar.py` - Radar batch ingestion (72h retention window)
- `upload_image_mosaic.py` - Windy GeoServer ImageMosaic updates
- `data_ready.py` - Seasonal layer ingestion
- `geoserver_utils.py` - GeoServer REST API wrappers

**Data Flow Pattern:**
1. External system writes GeoTIFFs + creates `<timestamp>.READY` file
2. Celery cron (every minute) scans for `.READY` files
3. Creates `.CELERY.CHECKED` debounce marker
4. Triggers GeoServer ingestion via REST API
5. Creates `.GEOSERVER.READY` on success

### Configuration

**Primary Config Files:**
- `projects/maps/project_configuration.yaml` - RAPyDo project metadata, env vars
- `.projectrc` - Local overrides (GeoServer credentials, Redis password, feature flags)
- `.env` - Full environment (auto-generated, do not commit sensitive changes)

**Critical Environment Variables:**
```yaml
PLATFORM: G100
DATA_PATH: /meteo
ACTIVATE_GEOSERVER: 1
GEOSERVER_ADMIN_USER: admin
GEOSERVER_ADMIN_PASSWORD: D3vMode!  # Change in production
REDIS_PASSWORD: lsaksdj9asss
GEOSERVER_PROXY_BASE_URL: maps.mistralportal.it
WINDY_INGEST_FOLDERS: Windy-00-ICON_2I_all2km.web,Windy-12-ICON_2I_all2km.web
```

## Data Organization

Forecast data structure on filesystem:
```
/<platform>/<env>/<prefix>-<run>-<dataset>.web/
└── <area>/
    ├── <reftime>.READY           # Data generation complete
    ├── <reftime>.GEOSERVER.READY # Ingested into GeoServer
    └── <variable>/
        └── <data files>
```

**Prefixes:**
- `Windy-<run>-<dataset>.web` - High-res forecasts (ICON, COSMO, WRF)
- `Tiles-<run>-<dataset>.web` - Pre-rendered tiles
- `Magics-<run>-<dataset>.web` - Forecast maps
- `PROB-<run>-iff.web` - Probability/percentile data

## GeoServer Integration

**Admin UI:** http://localhost:8080/geoserver (admin / D3vMode!)

**WMS Example:**
```
http://localhost:8080/geoserver/meteohub/wms?
  service=WMS&request=GetMap&
  layers=meteohub:radar-sri&
  time=2025-12-01T14:35:00.000Z&
  bbox=...&width=512&height=512&format=image/png
```

**Available Layers:**
- `radar-sri` - Surface rainfall intensity
- `radar-srt` - Surface rainfall type
- `windy-icon-*` - ICON model forecasts
- Seasonal forecast layers

SLD styles are in `projects/maps/builds/geoserver/` and synced automatically.

## Important Gotchas

1. **RAPyDo Version:** Must use v3.0 (`@3.0` tag in pip install). v2.x has breaking changes.

2. **GeoServer Data Dir:** Uses existing data dir (`GEOSERVER_EXISTING_DATA_DIR: true`). Do not delete `data/geoserver_data/` unless intentional reset.

3. **Celery Debounce:** Tasks create `.CELERY.CHECKED` files to avoid re-processing. Clear these manually if re-ingestion is needed.

4. **Radar Retention:** Only 72 hours of radar data retained. Older granules auto-deleted.

5. **THREDDS Disabled:** THREDDS integration was disabled in commit `73decfe`. Related code is commented out.

6. **Auth Disabled:** `ACTIVATE_AUTH: 0` in config. All endpoints are public except `/api/data/*` which uses IP whitelist.

7. **Test Cleanup:** Tests use `/tmp/shyfem_test` and auto-cleanup via `setup_shyfem_env` fixture. Do not hardcode `/shyfem` path.

8. **Branch Strategy:** Main branch is `main`. Version tags like `0.6`. Feature branches use numeric prefixes (e.g., `32-wrf-integration`).

## CI/CD

GitHub Actions workflows:
- **Backend:** Dev + Prod mode tests on push
- **CodeQL:** Daily security scan
- **Semgrep:** On-demand security scan
- **MyPy:** Type checking on push

CI uses `rapydo/actions/*` helpers for setup and coverage reporting.

## References

- **API Docs:** `docs/API.md`
- **Architecture:** `docs/ARCHITECTURE.md`
- **Data Types:** `docs/WINDY_DATA.md`, `docs/RADAR_DATA.md`, `docs/SEASONAL_DATA.md`
- **GeoServer:** `docs/GEOSERVER.md`
- **RAPyDo:** https://github.com/rapydo/do
