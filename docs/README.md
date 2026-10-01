# Documentation

[Project README](../README.md)

Choose a guide by what you need to do. For first-time installation, follow the
[Quick Start](../README.md#quick-start).

## Configure and Operate

| Guide | What you will find |
| --- | --- |
| [GeoWebCache configuration](GWC_CACHE.md) | Per-layer and global disk quotas, automatic sizing, direct WMS-C integration, deployment and verification |
| [GeoServer integration](GEOSERVER.md) | WMS requests, ImageMosaic layers, time dimensions, styles, proxy configuration and troubleshooting |
| [Dataset configuration](DATASET_CONFIGURATION.md) | Manifest structure, discovery, ingestion, retention, cache lifetime and zoom ranges |
| [Status setup](STATUS_SETUP.md) | Set up service and ingestion monitoring |
| [Status quick reference](STATUS_QUICKREF.md) | Common monitoring checks and commands |
| [Status API](STATUS_API.md) | Status endpoint payloads and integration |

## Build Clients and Develop

| Guide | What you will find |
| --- | --- |
| [REST API reference](API.md) | Endpoint parameters, responses and request examples |
| [Dynamic endpoints](DYNAMIC_ENDPOINTS.md) | Manifest-driven dataset endpoints |
| [Architecture](ARCHITECTURE.md) | Services, data flows, repository layout and development workflow |

## Understand a Data Product

| Product | Guide |
| --- | --- |
| High-resolution forecast models | [Windy](WINDY_DATA.md) |
| Precipitation observations and radar cache refresh | [Radar](RADAR_DATA.md) |
| Long-range forecasts | [Seasonal](SEASONAL_DATA.md) |
| Sub-seasonal forecasts | [Sub-seasonal](SUB_SEASONAL_DATA.md) |
| Wave forecasts | [WW3](WW3_DATA.md) |
| Pre-rendered map tiles | [Static tiles](TILES_DATA.md) |

## Which Configuration File Should I Edit?

| Change | File |
| --- | --- |
| Deployment defaults, including cache disk quotas | `projects/maps/project_configuration.yaml` |
| Environment-specific overrides | `.projectrc`, under `project_configuration.variables.env` |
| Dataset paths, variables, retention, cache expiry and seed zooms | `projects/maps/datasets.yml` |
| Which environment variables and volumes reach each service | `projects/maps/confs/commons.yml` |

For cache disk limits, begin with the [GeoWebCache examples](GWC_CACHE.md#configuration-examples).
For dataset changes, begin with the [manifest guide](DATASET_CONFIGURATION.md).
