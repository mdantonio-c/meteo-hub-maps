# GeoWebCache Configuration

[Project README](../README.md) · [Documentation index](README.md) · [GeoServer guide](GEOSERVER.md)

GeoWebCache (GWC) stores rendered map tiles so repeat requests can reuse them.
This guide explains how to size that cache and check that workers have received
the configuration.

## On This Page

- [Settings](#settings)
- [Configuration examples](#configuration-examples)
- [Apply and verify changes](#apply-and-verify-changes)
- [How quotas work](#how-quotas-work)
- [Direct WMS-C integration](#direct-wms-c-integration)
- [Parameter metadata cleanup](#parameter-metadata-cleanup)
- [Related guides](#related-guides)

## Settings

| Environment variable | Default | Accepted values | Purpose |
| --- | --- | --- | --- |
| `GWC_LAYER_QUOTA_MIB` | `1024` | Positive integer | Independent disk quota for each layer managed in the configured workspace |
| `GWC_GLOBAL_QUOTA_MIB` | Empty | Positive integer, or empty for automatic sizing | Global disk quota; automatic sizing uses per-layer MiB × current GWC layer count |
| `GEOSERVER_GWC_ENABLED` | `1` | `1` enables initialization | Enables the application's GWC configuration and cache management |

**Units:** 1 MiB = 1,048,576 bytes; 1024 MiB = 1 GiB.

Disk quotas are deployment environment settings. Dataset-specific cache expiry
and seed zoom ranges belong in the [dataset manifest](DATASET_CONFIGURATION.md#geoserver).
Reducing a tile cache quota does not reduce GeoTIFF retention.

## Configuration Examples

Set shared defaults in `projects/maps/project_configuration.yaml` under
`variables.env`. For a local deployment override, merge the following into your
existing `.projectrc` under `project_configuration.variables.env`.

### Automatic Global Quota

```yaml
project_configuration:
  variables:
    env:
      GWC_LAYER_QUOTA_MIB: 512
      GWC_GLOBAL_QUOTA_MIB: ""
```

Each managed layer gets a 512 MiB quota. With 10 current GWC layers, the global
quota is **5120 MiB**. The count includes all workspaces and comes from the live
GWC catalog, rather than saved quota entries. An empty catalog gives 0 MiB.

The calculated quota is refreshed during startup and layer-configuration checks,
including single-layer ingestion updates. It is not a separate continuous poll.

### Explicit Global Quota

```yaml
project_configuration:
  variables:
    env:
      GWC_LAYER_QUOTA_MIB: 1024
      GWC_GLOBAL_QUOTA_MIB: 8192
```

Each managed layer gets 1024 MiB; the global quota is fixed at **8192 MiB**.
Clear `GWC_GLOBAL_QUOTA_MIB` to return to automatic sizing.

## Apply and Verify Changes

1. Edit the deployment defaults or `.projectrc` overrides.
2. Regenerate the RAPyDo deployment configuration (`rapydo init`, using your
   deployment's usual profile flags).
3. **Recreate** the affected containers: `backend`, `celery`,
   `gwc_cache_control` and `gwc_cache_warm`. A plain restart does not update a
   container's environment. All workers should receive the same quota values.
4. Check the environment in each worker. For the default Compose project name:

   ```bash
   docker exec maps-celery-1 printenv GWC_LAYER_QUOTA_MIB
   docker exec maps-gwc_cache_control-1 printenv GWC_LAYER_QUOTA_MIB
   docker exec maps-gwc_cache_warm-1 printenv GWC_LAYER_QUOTA_MIB
   docker exec maps-celery-1 printenv GWC_GLOBAL_QUOTA_MIB
   ```

   Adjust names if your deployment uses different container names. An empty
   global value means automatic sizing; the per-layer value should be numeric.

5. Check startup logs for `Configured … MiB per-layer GWC disk quotas …` when
   configuration changes. Already-current settings need no update or reload.
6. In GeoServer's **Tile Caching → Disk Quota** page, check that enforcement is
   enabled and the global/per-layer limits match your settings. You can also
   inspect the authenticated REST endpoint `GET /geoserver/gwc/rest/diskquota.xml`.

**If `printenv` shows no per-layer value:** check that your deployed
`projects/maps/confs/commons.yml` contains the variable for the worker, regenerate
the deployment configuration and recreate that container.

## How Quotas Work

- **Per layer:** startup assigns an independent quota to each managed layer in
  the configured workspace. Newly ingested layers get it when their GWC
  configuration is initialized. One layer's quota covers all of its cached
  times, styles, formats and gridsets together.
- **Eviction:** managed layers use LRU (least recently used) eviction. Cleanup
  is periodic—every 10 seconds on a fresh configuration—so usage can briefly
  exceed the limit during seeding or heavy requests.
- **Global scope:** GWC applies its global quota to layers **without explicit
  per-layer quotas**. It is not an aggregate hard cap on independently limited
  layers. The automatic formula sizes this native global setting; it does not
  change its scope.
- **Persistence:** settings are stored in `gwc/geowebcache-diskquota.xml` via the
  GeoServer resource API. GeoServer reloads only when quota settings change.
  Existing cleanup scheduling and unrelated layer quotas are preserved.

## Direct WMS-C Integration

Worker startup enables **Enable direct WMS-C integration with GeoServer WMS**
and persists `directWMSIntegrationEnabled=true` in `gwc-gs.xml`. GeoServer reloads
only if this setting changes; other global GWC settings are preserved.

This allows eligible tiled WMS requests to use GWC through the GeoServer WMS
endpoint. Ordinary arbitrary-size WMS images are not automatically tile-cache
hits; requests must match the configured gridset and parameter filters.

## Parameter Metadata Cleanup

Backend startup registers the `cleanup_gwc_parameters` Celery task to run hourly
at minute `0`, on the `cache-control` queue. It scans layer directories under
`${GEOSERVER_DATA_PATH}/gwc` (default `/geoserver_data/gwc`) and removes
`parameters-<hash>.properties` files when either:

- their modification time is more than three days old; or
- no sibling tile-cache directory ends in `_<hash>` (for example,
  `EPSG_900913_1024_05_<hash>`), as can happen after a truncate.

Recent files with an associated directory are retained, including empty
directories. Old files are removed even when an associated directory exists.
The task only deletes parameter metadata; it does not truncate tiles or remove
granules. Symlinked files and layer directories are skipped. Each run logs
scanned, expired, orphaned and error counts. Cleanup is independent of ingestion
monitoring and skips filesystem access when `GEOSERVER_GWC_ENABLED=0`.

## Related Guides

- [GeoServer integration](GEOSERVER.md): WMS requests, layers, time dimensions and styles.
- [Dataset configuration](DATASET_CONFIGURATION.md#geoserver): cache expiry, retention and seed zooms.
- [Radar data](RADAR_DATA.md): incremental ingestion, cache invalidation and manual refresh.
- [Architecture](ARCHITECTURE.md): ingestion and cache worker responsibilities.
