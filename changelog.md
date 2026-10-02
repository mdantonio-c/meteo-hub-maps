# Changelog

[Project README](README.md)

Concise release changes are listed here, with links to their full descriptions in `docs/changelog/`. Releases are listed newest first. `MM` identifies the Meteo Maps version; `MH` identifies its target MeteoHub version.

## Meteo Maps 0.8 — target MeteoHub 0.5.9

**Full change description:** [MM0.8-MH0.5.9](docs/changelog/MM0.8-MH0.5.9.md).

| Change | Condensed description |
| --- | --- |
| [Dataset architecture](docs/changelog/MM0.8-MH0.5.9.md#dataset-architecture-and-configuration) | Centralizes dataset definitions, schedules and ingestion policy in YAML, with shared bulk/FIFO behaviors and specialized processors. |
| [Cache orchestration](docs/changelog/MM0.8-MH0.5.9.md#asynchronous-cache-orchestration-and-readiness) | Separates ingestion, invalidation and warming workers; supersedes stale work and writes ready markers after required invalidation. |
| [Incremental radar](docs/changelog/MM0.8-MH0.5.9.md#incremental-radar-processing) | Imports frames after the last successful watermark and preserves unchanged historical tiles. |
| [Cache storage policy](docs/changelog/MM0.8-MH0.5.9.md#cache-policy-and-storage-management) | Adds configurable tile expiry/zooms, persistent LRU quotas, automatic global sizing and hourly orphan-metadata cleanup. |
| [Explicit WMS-C](docs/changelog/MM0.8-MH0.5.9.md#explicit-wms-c-serving) | Keeps ordinary WMS separate from explicit cached tile routes; disables direct WMS-C integration. |
| [Dataset APIs](docs/changelog/MM0.8-MH0.5.9.md#dataset-apis-and-client-contracts) | Generates metadata/download/status routes, standardizes status payloads and adds zoom-specific WW3 vectors while preserving marine station JSON access. |
| [Status and maintenance](docs/changelog/MM0.8-MH0.5.9.md#service-status-and-maintenance-access) | Adds persistent availability information and a proxy maintenance allowlist, with public status checks and maintenance-aware API/WMS routing. |
| [Administrative access](docs/changelog/MM0.8-MH0.5.9.md#administrative-api-access) | Restricts monitoring and sensitive API controls using the shared allowlist and proxy-aware client-IP resolution. |
| [Runtime and tooling](docs/changelog/MM0.8-MH0.5.9.md#runtime-and-operational-tools) | Upgrades GeoServer to 3.0.1; adds timeout/JVM tuning, focused recovery, Flower and parallel manual cache refresh. |
| [Tests and documentation](docs/changelog/MM0.8-MH0.5.9.md#regression-coverage-and-documentation) | Expands ingestion/cache/access regression coverage and adds configuration and operations guides. |

**Client-facing changes:** revised status response structures, zoom-required WW3 vector URLs and explicit cached-route selection. See [API contract details](docs/changelog/MM0.8-MH0.5.9.md#dataset-apis-and-client-contracts).
