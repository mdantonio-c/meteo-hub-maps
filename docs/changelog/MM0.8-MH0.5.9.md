# Meteo Maps 0.8 — MeteoHub 0.5.9

[Changelog](../../changelog.md) · [Project README](../../README.md)

## Version pairing

- **Meteo Maps:** 0.8.
- **Target MeteoHub version:** 0.5.9.

This document describes the changes intended for this version pairing. The pairing identifies the target integration; it does not record a completed compatibility test or release date.

## Release recap

### Technical updates

- **Dataset architecture:** a validated YAML manifest, registry, reusable bulk/FIFO ingestion behaviors and dataset-specific processors replace much of the large task-module implementation. Discovery schedules and dynamic API routes use dataset configuration.
- **Cache orchestration:** dedicated ingestion, invalidation and warming queues coordinate work through Redis generations/locks. Completion markers wait for required invalidations; tile warming continues asynchronously.
- **Radar pipeline:** successful-import watermarks limit routine discovery to new timestamps. Cache updates target additions, removals and newly copied data while preserving unchanged historical tiles.
- **Cache policy:** 1024-pixel temporal tiles, configurable zoom/expiry settings, persistent per-layer LRU quotas, automatic or explicit global quotas and hourly orphan-metadata cleanup. Direct WMS-C integration is disabled; cached requests use explicit GWC routes.
- **API contracts:** manifest-generated metadata, download and ingestion-status endpoints; standardized status envelopes; zoom-specific WW3 vector downloads; preserved marine station-list and station-JSON routes.
- **Maintenance and access:** shared persisted status drives a reloadable Docker-nginx allowlist gate. Public API/GeoServer/WMS routing passes through that gate, status checks remain exempt, and monitoring/sensitive API controls use framework-resolved client-IP allowlisting.
- **Runtime and operations:** GeoServer 3.0.1, JVM/seeder tuning, centralized HTTP timeouts, lighter health probes, separate worker recovery, Flower monitoring and a bounded-parallel cache-refresh CLI.
- **Verification foundation:** expanded regression suites, updated custom-test CI execution and guides for dataset configuration, caching, endpoints and maintenance.

### Functional updates

- **Map delivery:** matching cached tile requests can reuse background-generated images, reducing repeated rendering work.
- **Radar freshness:** new frames are imported incrementally without routinely rebuilding the full retained history.
- **Data visibility:** clients can inspect dataset capabilities, completed coverage and pending imports through common API structures.
- **Availability communication:** operators can publish maintenance messages, schedules and affected services; clients can keep checking status during maintenance.
- **Controlled access:** designated clients (CINECA VPN IPs) can continue through the maintenance gate, while administrative monitoring controls remain IP-restricted during normal operation too (data ingestion scheduling and removal).
- **Operational control:** operators can tune cache budgets, refresh selected layers/timestamps, monitor task execution and manage dataset policies through shared configuration and tooling.
- **Client integration changes:** consumers must account for revised status payloads and WW3 vector URLs, and select the explicit cached route when requesting WMS-C tiles. A ready marker confirms invalidation completion, not that every replacement tile has finished warming.

## Detailed changes

### Dataset architecture and configuration

Dataset definitions move into `projects/maps/datasets.yml`, with validation and a registry in `projects/maps/backend/datasets/`. The manifest describes source paths, variables, discovery tasks, ingestion behavior, temporal parsing, GeoServer publication, cache policy and API operations for ICON, WRF, radar, WW3, seasonal, sub-seasonal and marine data.

Celery task entry points delegate to dataset-owned processors. Two reusable behaviors support conventional datasets: `bulk_override` replaces the published mosaic with the latest run, while `fifo_granules` merges incoming and published files and applies timestamp-based age/count retention. Existing models retain specialized processing for their layouts, styles and naming conventions.

Discovery schedules are constructed from manifest task declarations. Shared helpers provide path containment, temporal configuration, ready markers, file locks and staged mosaic replacement with backup restoration. Specialized paths still consume some environment-driven settings; the manifest is not a universal replacement for every deployment or processing option.

**Functional impact:** maintainers can configure much of dataset onboarding and policy centrally, reuse ingestion lifecycles and keep model-specific code focused on exceptional conventions.

### Asynchronous cache orchestration and readiness

Ingestion, cache invalidation and tile warming use separate `ingest`, `cache-control` and `cache-warm` queues. Dedicated workers isolate these workloads. Redis per-layer generations suppress superseded warming, while locks coordinate invalidation with new seed submissions.

Invalidation cancels and drains obsolete GWC work, configures temporal cache keys and invalidates selected variants. Full replacements purge the old layer cache; rolling updates invalidate explicit timestamp deltas. Warming proceeds asynchronously in lanes after invalidation.

A Celery chord joins required layer invalidations before its callback writes `.GEOSERVER.READY` and removes selected obsolete ready/debounce markers. When caching is disabled, the completion callback can run without cache work.

**Functional impact:** new publications can supersede stale background work. A completion marker confirms publication and required invalidation, while replacement tiles may still be warming.

### Incremental radar processing

Radar discovery uses the latest successful `.GEOSERVER.READY` endpoint as its watermark. Initial ingestion scans the retention window; subsequent scans select timestamps after successful completion. Pending checked markers do not advance that watermark.

Cache deltas include removed timestamps, newly indexed timestamps and newly copied files. Retained affected times are warmed; unchanged files in overlapping or retried batches keep their existing cached tiles. The default history remains 72 hours.

**Functional impact:** routine radar updates avoid resubmitting and rebuilding the full retained history. The normal incremental path is append-oriented: corrected historical files at already completed timestamps require separate handling.

### Cache policy and storage management

Temporal tile caching uses the `EPSG:900913_1024` gridset, 1024-pixel tiles and PNG by default. Manifest defaults seed zooms 5–8; radar and marine use 5–9. Default server expiry is 86,400 seconds, with mapped radar layers using 259,200 seconds. Deployment client expiry defaults to zero.

Persistent per-layer LRU quotas are configured with `GWC_LAYER_QUOTA_MIB`, defaulting to 1024 MiB. `GWC_GLOBAL_QUOTA_MIB` accepts an explicit limit or, when empty, calculates per-layer MiB multiplied by the live GWC layer count. Equivalent quota units are compared by byte value to avoid unnecessary GeoServer reloads.

The native global quota applies to layers without explicit per-layer quotas; it is not an aggregate hard cap on all managed caches. Eviction is periodic and independent of source GeoTIFF retention.

Hourly cleanup removes only orphan `parameters-<hash>.properties` files. Metadata associated with a sibling hash directory is retained regardless of age, including when that directory is empty.

**Functional impact:** operators can size caches and remove leftover metadata without changing forecast/radar data retention.

### Explicit WMS-C serving

Startup persists `directWMSIntegrationEnabled=false`, keeping ordinary GeoServer WMS separate from cached WMS-C. Cached tile requests use `/wms/cache` or `/geoserver/gwc/service/wms` and must match the configured gridset and parameter filters.

**Functional impact:** matching cached requests can reuse background-generated images. Arbitrary ordinary WMS requests remain on the rendering path. The final policy supersedes the branch's earlier direct-WMS integration enabling.

### Dataset APIs and client contracts

Endpoint classes are generated from manifest operation-route mappings. Supported operations include dataset metadata, configured file downloads, ingestion status and marine station-related metadata. File downloads validate enabled capabilities and resolved-path containment.

Configured status routes use a common envelope containing `id`, `kind`, `display_name`, `ingestion` and `data`. Marker-based ingestion status distinguishes completed coverage from newer pending imports and includes dataset-specific information such as marine forcing availability, radar interval and WW3 offsets.

WW3 vector downloads now require `/api/ww3/vectors/<zoom>/<filename>`, with zoom 0–22 and validated timestamped JSON/GeoJSON filenames under `Mediterraneo/dir-dir/<zoom>`. Marine's generated `/api/marine/shyfem/stations` returns configuration metadata; actual station listing and parsed JSON remain available at `/api/marine/shyfem/data/stations` and its forcing/filename route.

Dynamic mode defaults on. Generated classes are created at module import; the feature flag suppresses selected legacy classes rather than gating the generator itself. Some legacy response contracts and route availability change, including legacy seasonal JSON endpoints without equivalent download operations in the current manifest.

**Functional impact:** clients gain common dataset discovery/status structures, with integration updates needed for revised payloads and URLs.

### Service status and maintenance access

`GET /api/service/status` reads persistent operator-managed status, including message, planned times and affected services. Status scripts edit the shared JSON file. `GET /api/status` remains the API liveness check; there is no active status-update POST.

Docker nginx checks status every second and applies `MAINTENANCE_ALLOWLIST` during maintenance, returning 503 to other clients. The two status routes remain public. Optional forced mode overrides the status file, and invalid/missing updates retain the last applied gate state. Configuration changes are validated before nginx reload.

Host nginx routes API, GeoServer and ordinary/cached WMS through Docker nginx. Trusted proxy configuration governs forwarded-IP resolution at that gate. GeoServer HTML links and redirects are rewritten to the public HTTPS origin.

**Functional impact:** operators can communicate availability and allow designated clients, including configured CINECA VPN networks, to continue through the maintenance gate. Enforcement applies to traffic traversing Docker nginx; independently exposed ports and host-served routes retain their own routing rules.

### Administrative API access

`POST` and `DELETE /api/data/monitoring`, plus `/api/maps/sensitive`, require membership in `MAINTENANCE_ALLOWLIST` during both maintenance and normal operation. Denied API requests receive 403. Empty or invalid allowlists deny access.

The decorator resolves the client using RAPyDo's `BaseAuthentication.get_remote_ip()`, supporting proxy-supplied `X-Real-IP` and proxied forwarded-address handling rather than checking only the Docker connection address. Header trust follows the framework/proxy contract; the decorator does not separately consult the nginx trusted-proxy setting.

**Functional impact:** scheduling and removal of ingestion monitoring are restricted to designated clients, with access checks working through the configured proxy.

### Runtime and operational tools

GeoServer moves to 3.0.1, with JVM/seeder tuning and production 4–8 GiB heap configuration. The custom NetCDF-output extension installation is commented out. Shared backend HTTP timeouts default to 10 seconds for connection and 600 seconds for reads.

The health probe checks a static GeoServer resource. Healthwatch separately restarts unhealthy GeoServer instances and stuck ingestion workers, using Compose service labels; it is disabled in development. Production Flower is exposed at `/flower/` with configured basic authentication.

The manual cache-refresh CLI resolves actual coverage stores through GeoServer, accepts selected timestamps, reports progress and uses bounded parallel seed batches, defaulting to four jobs. `--no-wait` leaves only the final seed batch running.

**Functional impact:** operators gain clearer task visibility, targeted cache refresh and more focused recovery behavior.

### Regression coverage and documentation

New suites cover manifest validation, discovery/dispatch, cache invalidation/readiness, quotas and expiry, radar watermarks, orphan cleanup, manual refresh, service status, nginx maintenance configuration and proxied IP access. CI executes the custom test folder.

Documentation adds dataset configuration, dynamic endpoint, service-status and GeoWebCache guides with task-oriented navigation.

**Functional impact:** maintainers have broader regression coverage and clearer configuration/operations references. This change description reports implementation behavior; it does not establish measured performance gains or a completed MeteoHub 0.5.9 integration test.
