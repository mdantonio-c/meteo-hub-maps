"""GeoWebCache invalidation adapter."""

import os
import shutil
import time
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Tuple, Union
from xml.etree import ElementTree

import requests
from maps.utils.geoserver import GEOSERVER_REQUEST_TIMEOUT
from .manifest import load_cache_defaults, load_manifest

log = logging.getLogger(__name__)

GWC_ENABLED_DEFAULT = os.environ.get("GEOSERVER_GWC_ENABLED", "1") == "1"
# Caps how many TIME values get an individual seed/truncate request per call,
# so a mosaic with a long history doesn't trigger hundreds of HTTP requests.
GWC_MAX_TIMES_PER_SEED = int(os.environ.get("GWC_MAX_TIMES_PER_SEED", "12"))
# GeoServer names its EPSG:3857 grid set with the legacy equivalent EPSG:900913.
WEB_MERCATOR_GRID_SET = "EPSG:900913"
GWC_GRID_SET = os.environ.get("GWC_GRID_SET", "EPSG:900913_1024")
GWC_TILE_SIZE = int(os.environ.get("GWC_TILE_SIZE", "1024"))
GWC_IMAGE_FORMAT = os.environ.get("GWC_IMAGE_FORMAT", "image/png")
GWC_BLOBSTORE_ROOT = os.environ.get("GEOSERVER_DATA_PATH", "/geoserver_data")
# Ingestion explicitly removes stale entries. Expiry is a safety net when an
# ingestion fails before truncating its layer. Datasets can override this lifetime.
GWC_CACHE_EXPIRE_SECONDS = int(os.environ.get("GWC_CACHE_EXPIRE_SECONDS", "86400"))
# Forecast publication invalidates server-side tiles, but browsers cannot be
# purged. Keep their copy below the five-minute radar update cadence.
GWC_CLIENT_EXPIRE_SECONDS = int(os.environ.get("GWC_CLIENT_EXPIRE_SECONDS", "300"))
GWC_LAYER_QUOTA_GIB = 1
# Max seconds to wait for GWC seed queue to drain (tile generation).
GWC_SEED_WAIT_TIMEOUT = int(os.environ.get("GWC_SEED_WAIT_TIMEOUT", "1800"))
# Seconds between seed queue polls.
GWC_SEED_POLL_INTERVAL = int(os.environ.get("GWC_SEED_POLL_INTERVAL", "3"))


@dataclass(frozen=True)
class TemporalCacheLayer:
    """Published temporal layer and its GeoServer coverage-store identity."""

    name: str
    store_name: Optional[str] = None


class GWCInvalidator:
    """Truncate and re-seed cached tiles after a successful layer update."""

    def __init__(
        self,
        geoserver_url: str,
        username: str,
        password: str,
        workspace: str,
        enabled: Optional[bool] = None,
        timeout: Optional[Union[float, Tuple[float, float]]] = None,
        zoom_start: Optional[int] = None,
        zoom_stop: Optional[int] = None,
    ) -> None:
        self.base_url = geoserver_url.rstrip("/")
        self.username = username
        self.password = password
        self.workspace = workspace
        self.enabled = enabled if enabled is not None else GWC_ENABLED_DEFAULT
        self.timeout = timeout if timeout is not None else GEOSERVER_REQUEST_TIMEOUT
        self.manifest_path = os.environ.get("DATASET_CONFIG_PATH") or str(
            Path(__file__).resolve().parents[2] / "datasets.yml"
        )
        cache_defaults = (
            load_cache_defaults(self.manifest_path)
            if zoom_start is None or zoom_stop is None
            else {}
        )
        self.zoom_start = (
            cache_defaults.get("zoom_start") if zoom_start is None else zoom_start
        )
        self.zoom_stop = (
            cache_defaults.get("zoom_stop") if zoom_stop is None else zoom_stop
        )
        if self.zoom_start is None or self.zoom_stop is None:
            raise ValueError(
                "GeoWebCache zoom range must be set with geoserver.cache.zoom_start "
                "and geoserver.cache.zoom_stop in the dataset manifest, or passed "
                "explicitly to GWCInvalidator"
            )

    def _seed_request(
        self,
        layer_name: str,
        seed_type: str,
        time_value: Optional[str],
        thread_count: int,
        style_name: Optional[str] = None,
    ) -> bool:
        layer_id = f"{self.workspace}:{layer_name}"
        url = f"{self.base_url}/gwc/rest/seed/{layer_id}.xml"
        if time_value:
            # GeoServer resolves an empty STYLES= request to the layer's default
            # style before GWC builds its cache key. Seed that canonical value.
            parameters_xml = (
                "\n  <parameters>"
                "\n    <entry>"
                "\n      <string>STYLES</string>"
                "\n      <string>{}</string>"
                "\n    </entry>"
                "\n    <entry>"
                "\n      <string>TIME</string>"
                "\n      <string>{}</string>"
                "\n    </entry>"
                "\n  </parameters>"
            ).format(style_name or "", time_value)
        else:
            # Seed the entire layer — GWC will generate tiles for all TIME
            # values present in the granule index (no per-time HTTP round-trip).
            parameters_xml = ""
        payload = (
            "<seedRequest>\n"
            "  <name>{}</name>\n"
            "  <type>{}</type>\n"
            "  <gridSetId>{}</gridSetId>\n"
            "  <format>{}</format>\n"
            "  <zoomStart>{}</zoomStart>\n"
            "  <zoomStop>{}</zoomStop>\n"
            "  <threadCount>{}</threadCount>{}\n"
            "</seedRequest>"
        ).format(
            layer_id,
            seed_type,
            GWC_GRID_SET,
            GWC_IMAGE_FORMAT,
            self.zoom_start,
            self.zoom_stop,
            thread_count,
            parameters_xml,
        )

        try:
            response = requests.post(
                url,
                data=payload,
                headers={"Content-Type": "application/xml"},
                auth=(self.username, self.password),
                timeout=self.timeout,
            )
        except requests.RequestException:
            return False
        return response.status_code in (200, 201, 202)

    def get_default_style(self, layer_name: str) -> Optional[str]:
        """Get the style GeoServer resolves for an empty WMS STYLES parameter."""
        url = f"{self.base_url}/rest/layers/{self.workspace}:{layer_name}.json"
        try:
            response = requests.get(
                url, auth=(self.username, self.password), timeout=self.timeout
            )
            if response.status_code != 200:
                log.error(
                    f"GeoServer default style lookup failed for {layer_name}: "
                    f"HTTP {response.status_code} {response.text}"
                )
                return None
            return response.json().get("layer", {}).get("defaultStyle", {}).get("name")
        except (requests.RequestException, ValueError):
            log.exception(f"GeoServer default style lookup failed for {layer_name}")
            return None

    def _wait_for_seed_completion(
        self,
        layer_name: str,
        timeout: float = GWC_SEED_WAIT_TIMEOUT,
        poll_interval: float = GWC_SEED_POLL_INTERVAL,
    ) -> bool:
        """Poll GWC seed queue until seeding completes or timeout.

        Blocks until all queued seed tasks for the layer have drained,
        meaning tiles are fully generated and no longer lazily cached
        on user request.
        """
        layer_id = f"{self.workspace}:{layer_name}"
        url = f"{self.base_url}/gwc/rest/seed/{layer_id}.json"

        while timeout > 0:
            try:
                response = requests.get(
                    url,
                    auth=(self.username, self.password),
                    timeout=self.timeout,
                )
                if response.status_code != 200:
                    timeout -= poll_interval
                    time.sleep(poll_interval)
                    continue

                data = response.json()

                # GeoWebCache's native endpoint returns task arrays as
                # [processed, total, remaining_seconds, id, status], where
                # 0=pending, 1=running, 2=done, and -1=aborted. GeoServer
                # versions may instead expose inQueue/inProgress metadata.
                task_arrays = data.get("long-array-array")
                if task_arrays is not None:
                    active = any(
                        len(task) >= 5 and task[4] in (0, 1) for task in task_arrays
                    )
                    if not active:
                        return True
                else:
                    # GWC 2.x returns a flat structure with inQueue/inProgress
                    # at top level; some versions wrap it under seedQueue.
                    seed_queue = data.get("seedQueue", data)
                    in_queue = seed_queue.get("inQueue", False)
                    in_progress = seed_queue.get("inProgress", False)

                    # If both are false, seeding is complete.
                    if not in_queue and not in_progress:
                        # Check for any failed tasks as a safety net.
                        tasks = seed_queue.get("tasks", [])
                        if tasks:
                            failed = any(
                                task.get("status") == "failed" for task in tasks
                            )
                            if failed:
                                return False
                        return True

                timeout -= poll_interval
                time.sleep(poll_interval)

            except (requests.RequestException, ValueError):
                timeout -= poll_interval
                time.sleep(poll_interval)

        return False

    def cancel_seed_tasks(self, layer_name: str) -> bool:
        """Cancel pending and running GWC work for one layer.

        GWC schedules seed and truncate requests in a shared FIFO queue.  A
        newer publication must remove obsolete warming before its truncate is
        submitted; otherwise a fresh cache invalidation can wait behind tiles
        that are already stale.
        """
        if not self.enabled:
            return True

        layer_id = f"{self.workspace}:{layer_name}"
        url = f"{self.base_url}/gwc/rest/seed/{layer_id}"
        try:
            response = requests.post(
                url,
                data={"kill_all": "all"},
                auth=(self.username, self.password),
                timeout=self.timeout,
            )
        except requests.RequestException:
            log.exception("GWC seed cancellation failed for {}", layer_name)
            return False
        if response.status_code != 200:
            log.error(
                "GWC seed cancellation failed for {}: HTTP {} {}",
                layer_name,
                response.status_code,
                response.text,
            )
            return False
        return True

    def ensure_direct_wms_integration(self) -> bool:
        """Enable GeoServer's direct WMS-C integration in persisted GWC settings."""
        if not self.enabled:
            return True
        url = f"{self.base_url}/rest/resource/gwc-gs.xml"
        try:
            response = requests.get(
                url, auth=(self.username, self.password), timeout=self.timeout
            )
            if response.status_code != 200:
                log.error(
                    "GWC global configuration lookup failed: HTTP %s",
                    response.status_code,
                )
                return False
            config = ElementTree.fromstring(response.content)
            setting = config.find("directWMSIntegrationEnabled")
            if setting is not None and setting.text == "true":
                return True
            if setting is None:
                setting = ElementTree.SubElement(config, "directWMSIntegrationEnabled")
            setting.text = "true"
            response = requests.put(
                url,
                data=ElementTree.tostring(config, encoding="utf-8"),
                headers={"Content-Type": "application/xml"},
                auth=(self.username, self.password),
                timeout=self.timeout,
            )
            if response.status_code not in (200, 201):
                log.error(
                    "GWC global configuration update failed: HTTP %s",
                    response.status_code,
                )
                return False
            # The resource endpoint persists XML; reload makes GWC use it now.
            response = requests.post(
                f"{self.base_url}/rest/reload",
                auth=(self.username, self.password),
                timeout=self.timeout,
            )
            if response.status_code not in (200, 201):
                log.error("GeoServer reload failed: HTTP %s", response.status_code)
                return False
        except (requests.RequestException, ElementTree.ParseError):
            log.exception("Could not enable direct WMS integration")
            return False
        log.info("Enabled direct WMS-C integration with GeoServer WMS")
        return True

    def ensure_disk_quota(self, layer_names: Iterable[str]) -> bool:
        """Persist independent 1 GiB LRU quotas and restart quota enforcement.

        The native diskquota REST PUT only mutates runtime configuration in
        GeoServer 3.0. Persist the quota XML through the resource API and reload
        GeoServer so quotas survive restarts and the cleanup monitor starts.
        """
        if not self.enabled:
            return True
        url = f"{self.base_url}/rest/resource/gwc/geowebcache-diskquota.xml"
        try:
            response = requests.get(
                url, auth=(self.username, self.password), timeout=self.timeout
            )
            if response.status_code == 404:
                config = ElementTree.fromstring(
                    "<gwcQuotaConfiguration><enabled>true</enabled>"
                    "<cacheCleanUpFrequency>10</cacheCleanUpFrequency>"
                    "<cacheCleanUpUnits>SECONDS</cacheCleanUpUnits>"
                    "<maxConcurrentCleanUps>2</maxConcurrentCleanUps>"
                    "<globalExpirationPolicyName>LFU</globalExpirationPolicyName>"
                    "<globalQuota><value>500</value><units>MiB</units></globalQuota>"
                    "<layerQuotas/></gwcQuotaConfiguration>"
                )
                changed = True
            elif response.status_code == 200:
                config = ElementTree.fromstring(response.content)
                # ConfigLoader's persisted XML may have a default namespace.
                for element in config.iter():
                    element.tag = element.tag.rsplit("}", 1)[-1]
                if config.tag != "gwcQuotaConfiguration":
                    log.error("Unexpected GWC disk quota configuration format")
                    return False
                changed = False
            else:
                log.error("GWC disk quota lookup failed: HTTP %s", response.status_code)
                return False

            enabled = config.find("enabled")
            if enabled is None:
                enabled = ElementTree.SubElement(config, "enabled")
            if enabled.text != "true":
                enabled.text = "true"
                changed = True
            quotas = config.find("layerQuotas")
            if quotas is None:
                quotas = ElementTree.SubElement(config, "layerQuotas")
            for layer_name in sorted(set(layer_names)):
                layer_id = f"{self.workspace}:{layer_name}"
                existing = [q for q in quotas if q.findtext("layer") == layer_id]
                if (
                    len(existing) == 1
                    and existing[0].findtext("expirationPolicyName") == "LRU"
                    and existing[0].findtext("quota/value") == str(GWC_LAYER_QUOTA_GIB)
                    and existing[0].findtext("quota/units") == "GiB"
                ):
                    continue
                for entry in existing:
                    quotas.remove(entry)
                entry = ElementTree.SubElement(quotas, "LayerQuota")
                ElementTree.SubElement(entry, "layer").text = layer_id
                ElementTree.SubElement(entry, "expirationPolicyName").text = "LRU"
                quota = ElementTree.SubElement(entry, "quota")
                ElementTree.SubElement(quota, "value").text = str(GWC_LAYER_QUOTA_GIB)
                ElementTree.SubElement(quota, "units").text = "GiB"
                changed = True
            if not changed:
                return True
            response = requests.put(
                url,
                data=ElementTree.tostring(config, encoding="utf-8"),
                headers={"Content-Type": "application/xml"},
                auth=(self.username, self.password),
                timeout=self.timeout,
            )
            if response.status_code not in (200, 201):
                log.error("GWC disk quota update failed: HTTP %s", response.status_code)
                return False
            response = requests.post(
                f"{self.base_url}/rest/reload",
                auth=(self.username, self.password),
                timeout=self.timeout,
            )
            if response.status_code not in (200, 201):
                log.error("GWC disk quota reload failed: HTTP %s", response.status_code)
                return False
        except (requests.RequestException, ElementTree.ParseError):
            log.exception("Could not configure GWC disk quotas")
            return False
        log.info("Configured 1 GiB per-layer GWC disk quotas with LRU eviction")
        return True

    def _cache_expiry_seconds(self, layer_name: str) -> int:
        """Resolve a mapped layer's dataset-specific server cache lifetime."""
        for dataset in load_manifest(self.manifest_path):
            if dataset.geoserver.get("workspace") != self.workspace:
                continue
            variables = dataset.geoserver.get("variables", {}).values()
            if any(variable.get("layer_name") == layer_name for variable in variables):
                return int(
                    dataset.geoserver.get("cache", {}).get(
                        "expire_seconds", GWC_CACHE_EXPIRE_SECONDS
                    )
                )
        return GWC_CACHE_EXPIRE_SECONDS

    def ensure_time_parameter_filter(self, layer_name: str) -> bool:
        """Configure GWC to cache distinct WMS TIME parameter values for a layer."""
        if not self.enabled:
            return True

        layer_id = f"{self.workspace}:{layer_name}"
        url = f"{self.base_url}/gwc/rest/layers/{layer_id}.xml"
        try:
            response = requests.get(
                url, auth=(self.username, self.password), timeout=self.timeout
            )
            if response.status_code != 200:
                log.error(
                    f"GWC layer configuration lookup failed for {layer_name}: "
                    f"HTTP {response.status_code} {response.text}"
                )
                return False
            layer = ElementTree.fromstring(response.content)
        except (requests.RequestException, ElementTree.ParseError):
            log.exception(f"GWC layer configuration lookup failed for {layer_name}")
            return False

        filters = layer.find("parameterFilters")
        if filters is None:
            filters = ElementTree.SubElement(layer, "parameterFilters")
        if any((item.findtext("key") or "").upper() == "TIME" for item in filters):
            filter_added = False
        else:
            time_filter = ElementTree.SubElement(filters, "regexParameterFilter")
            ElementTree.SubElement(time_filter, "key").text = "TIME"
            ElementTree.SubElement(time_filter, "defaultValue").text = ""
            # ImageMosaic validates its time dimension; GWC keeps a tile set per value.
            ElementTree.SubElement(time_filter, "regex").text = ".*"
            filter_added = True

        grid_subsets = layer.find("gridSubsets")
        current_grid_sets = (
            [item.findtext("gridSetName") for item in grid_subsets]
            if grid_subsets is not None
            else []
        )
        cache_expiry = layer.find("expireCache")
        client_expiry = layer.find("expireClients")
        expire_seconds = self._cache_expiry_seconds(layer_name)
        cache_expiry_is_current = cache_expiry is not None and cache_expiry.text == str(
            expire_seconds
        )
        client_expiry_is_current = (
            client_expiry is not None
            and client_expiry.text == str(GWC_CLIENT_EXPIRE_SECONDS)
        )
        # A layer can retain a gridset reference after its gridset was removed
        # from GWC. Verify it before accepting the otherwise-current layer
        # configuration; GWC then fails requests with a null GridSubset.
        if not self._ensure_grid_set():
            return False
        if (
            current_grid_sets == [GWC_GRID_SET]
            and not filter_added
            and cache_expiry_is_current
            and client_expiry_is_current
        ):
            return self.ensure_disk_quota([layer_name])
        if grid_subsets is not None:
            layer.remove(grid_subsets)
        grid_subsets = ElementTree.SubElement(layer, "gridSubsets")
        grid_subset = ElementTree.SubElement(grid_subsets, "gridSubset")
        ElementTree.SubElement(grid_subset, "gridSetName").text = GWC_GRID_SET
        if cache_expiry is None:
            cache_expiry = ElementTree.SubElement(layer, "expireCache")
        cache_expiry.text = str(expire_seconds)
        if client_expiry is None:
            client_expiry = ElementTree.SubElement(layer, "expireClients")
        client_expiry.text = str(GWC_CLIENT_EXPIRE_SECONDS)
        try:
            response = requests.put(
                url,
                data=ElementTree.tostring(layer, encoding="utf-8"),
                headers={"Content-Type": "application/xml"},
                auth=(self.username, self.password),
                timeout=self.timeout,
            )
        except requests.RequestException:
            log.exception(f"GWC layer configuration update failed for {layer_name}")
            return False
        if response.status_code not in (200, 201):
            log.error(
                f"GWC layer configuration update failed for {layer_name}: "
                f"HTTP {response.status_code} {response.text}"
            )
        return response.status_code in (200, 201) and self.ensure_disk_quota([layer_name])

    def _ensure_grid_set(self) -> bool:
        """Create the Web Mercator gridset used by 1024px WMS tiles."""
        url = f"{self.base_url}/gwc/rest/gridsets/{GWC_GRID_SET}.xml"
        try:
            response = requests.get(
                url,
                auth=(self.username, self.password),
                timeout=self.timeout,
            )
        except requests.RequestException:
            log.exception(f"GWC gridset lookup failed for {GWC_GRID_SET}")
            return False
        if response.status_code == 200:
            return True
        gridset_missing = response.status_code == 404 or (
            response.status_code == 500 and "does not exist" in response.text.lower()
        )
        if not gridset_missing:
            log.error(
                f"GWC gridset lookup failed for {GWC_GRID_SET}: "
                f"HTTP {response.status_code} {response.text}"
            )
            return False

        resolutions = [156543.03392804097 / (2**zoom) for zoom in range(23)]
        resolution_xml = "".join(
            f"<double>{resolution}</double>" for resolution in resolutions
        )
        payload = (
            "<gridSet>"
            f"<name>{GWC_GRID_SET}</name>"
            "<srs><number>900913</number></srs>"
            "<extent><coords>"
            "<double>-20037508.342789244</double>"
            "<double>-20037508.342789244</double>"
            "<double>20037508.342789244</double>"
            "<double>20037508.342789244</double>"
            "</coords></extent>"
            "<alignTopLeft>true</alignTopLeft>"
            f"<resolutions>{resolution_xml}</resolutions>"
            "<metersPerUnit>1.0</metersPerUnit>"
            f"<tileWidth>{GWC_TILE_SIZE}</tileWidth>"
            f"<tileHeight>{GWC_TILE_SIZE}</tileHeight>"
            "<yCoordinateFirst>false</yCoordinateFirst>"
            "</gridSet>"
        )
        try:
            response = requests.put(
                url,
                data=payload,
                headers={"Content-Type": "application/xml"},
                auth=(self.username, self.password),
                timeout=self.timeout,
            )
        except requests.RequestException:
            log.exception(f"GWC gridset creation failed for {GWC_GRID_SET}")
            return False
        if response.status_code not in (200, 201):
            log.error(
                f"GWC gridset creation failed for {GWC_GRID_SET}: "
                f"HTTP {response.status_code} {response.text}"
            )
        return response.status_code in (200, 201)

    def truncate(
        self,
        layer_name: str,
        times: Optional[Iterable[str]] = None,
        style_name: Optional[str] = None,
        wait_per_time: bool = True,
    ) -> bool:
        """Truncate one layer's GWC cache; disabled mode is an intentional no-op.

        Args:
            layer_name: Layer name without workspace prefix.
            times: Optional ISO8601 TIME dimension values to truncate individually.
                    When omitted, removes every cache variant for the layer,
                    including stale dates and styles no longer in the mosaic.
            wait_per_time: When False, submit all truncate requests before
                    waiting once for GeoWebCache to drain. Use only while a
                    controller lock prevents warm submissions from entering
                    GWC between the truncate requests.
        """
        if not self.enabled:
            return True

        time_values = list(times) if times else [None]
        for index, time_value in enumerate(time_values):
            if not self._seed_request(
                layer_name,
                "truncate",
                time_value,
                thread_count=1,
                style_name=style_name,
            ):
                return False
            if not wait_per_time:
                continue
            # Truncation updates the file blob-store quota asynchronously.
            # Existing direct callers retain this conservative behavior.
            if not self._wait_for_seed_completion(layer_name):
                log.error(
                    "GWC truncate did not complete for {} (TIME {}/{})",
                    layer_name,
                    index + 1,
                    len(time_values),
                )
                return False
        if not wait_per_time and not self._wait_for_seed_completion(layer_name):
            log.error(
                "GWC batch truncate did not complete for {} ({} TIME values)",
                layer_name,
                len(time_values),
            )
            return False
        return True

    def seed(
        self,
        layer_name: str,
        wait: bool = True,
        times: Optional[Iterable[str]] = None,
        style_name: Optional[str] = None,
        parallelism: int = 1,
    ) -> bool:
        """Seed one layer's GWC cache for every requested TIME value.

        Args:
            layer_name: Layer name without workspace prefix.
            wait: When True, blocks until seed queue drains and tiles are
                  fully generated (not lazily cached on first user request).
            times: ISO8601 TIME values to seed, one parameter combination per job.
            parallelism: Maximum timestep jobs submitted before waiting for the
                         layer queue to drain. Each job uses one GWC thread.

        Returns:
            True if every seed request was accepted and (if wait=True)
            completed successfully, False otherwise.
        """
        if parallelism < 1:
            raise ValueError("Seed parallelism must be at least 1")
        if not self.enabled:
            return True

        time_values = list(times) if times is not None else [None]
        for index, time_value in enumerate(time_values):
            if not self._seed_request(
                layer_name, "seed", time_value, thread_count=1, style_name=style_name
            ):
                return False
            batch_end = (index + 1) % parallelism == 0
            last_time = index + 1 == len(time_values)
            # With parallel jobs, bound the queue even when the caller skips
            # waiting for the final batch. Serial no-wait callers are unchanged.
            should_wait = (wait and (batch_end or last_time)) or (
                parallelism > 1 and batch_end and not last_time
            )
            if should_wait and not self._wait_for_seed_completion(layer_name):
                return False
        return True

    def get_granule_times(
        self, layer_name: str, store_name: Optional[str] = None, all_times: bool = False
    ) -> List[str]:
        """Fetch the ISO8601 TIME values currently present in a mosaic layer's granule index.

        Args:
            layer_name: Layer name without workspace prefix.
            store_name: Optional store name (defaults to layer_name).
            all_times: When True, return ALL time values instead of capping
                       to the most recent GWC_MAX_TIMES_PER_SEED. Useful for
                       seeding all available timesteps during ingestion.
        """
        if not self.enabled:
            return []

        store = store_name or layer_name
        url = (
            f"{self.base_url}/rest/workspaces/{self.workspace}/coveragestores/"
            f"{store}/coverages/{layer_name}/index/granules.json"
        )
        try:
            response = requests.get(
                url, auth=(self.username, self.password), timeout=self.timeout
            )
        except requests.RequestException:
            log.exception(f"GWC granule lookup failed for {layer_name} at {store}")
            return []
        if response.status_code != 200:
            log.error(
                f"GWC granule lookup failed for {layer_name} at {store}: "
                f"HTTP {response.status_code} {response.text}"
            )
            return []

        try:
            features = response.json().get("features", [])
        except ValueError:
            return []

        times = sorted(
            {
                self._normalize_time(feature.get("properties", {}).get("time"))
                for feature in features
                if feature.get("properties", {}).get("time")
            }
        )
        if all_times:
            return times
        return times[-GWC_MAX_TIMES_PER_SEED:]

    def get_cached_times(self, layer_name: str) -> List[str]:
        """Return TIME values represented by GWC's file-blobstore metadata.

        GeoWebCache keeps one ``parameters-<hash>.properties`` file for each
        parameter set.  On this GWC version an unparameterized truncate does
        not reliably remove temporal variants, so full layer refreshes must
        explicitly truncate every cached TIME value, including times no longer
        available in the ImageMosaic.
        """
        layer_id = f"{self.workspace}_{layer_name}"
        cache_dir = os.path.join(GWC_BLOBSTORE_ROOT, "gwc", layer_id)
        try:
            names = os.listdir(cache_dir)
        except OSError:
            return []

        times = set()
        for name in names:
            if not name.startswith("parameters-") or not name.endswith(".properties"):
                continue
            try:
                with open(
                    os.path.join(cache_dir, name), encoding="utf-8"
                ) as parameter_file:
                    for line in parameter_file:
                        if line.startswith("TIME="):
                            times.add(
                                line.partition("=")[2].strip().replace("\\:", ":")
                            )
                            break
            except OSError:
                continue
        return sorted(times)

    def purge_layer_cache(self, layer_name: str) -> bool:
        """Remove every file-blobstore entry for a fully replaced layer.

        Parameterized GWC truncates leave ``parameters-*.properties`` metadata
        behind, and older GWC versions can retain orphaned parameter variants.
        Call this only after cancelling and draining GWC work for a non-rolling
        layer; radar uses targeted truncates and must retain its other times.
        """
        if not self.enabled:
            return True

        cache_dir = os.path.join(
            GWC_BLOBSTORE_ROOT, "gwc", f"{self.workspace}_{layer_name}"
        )
        try:
            shutil.rmtree(cache_dir)
        except FileNotFoundError:
            return True
        except OSError:
            log.exception("GWC blobstore purge failed for {}", layer_name)
            return False
        log.info("Purged every GWC blobstore entry for {}", layer_name)
        return True

    def refresh_temporal_layer(self, layer: TemporalCacheLayer) -> bool:
        """Replace every cached tile for one temporal layer after publication.

        The unparameterized truncate removes all stale GWC variants first. The
        current mosaic times and effective GeoServer style are then used to
        rebuild precisely the cache keys served to WMS clients.
        """
        if not self.enabled:
            return True
        if not self.ensure_time_parameter_filter(layer.name):
            log.error(f"GWC TIME/gridset configuration failed for {layer.name}")
            return False
        times = self.get_granule_times(
            layer.name, store_name=layer.store_name, all_times=True
        )
        if not times:
            log.error(
                f"GWC found no granule times for {layer.name} "
                f"using store {layer.store_name or layer.name}"
            )
            return False
        style_name = self.get_default_style(layer.name)
        if not style_name:
            log.error(f"GWC could not resolve default style for {layer.name}")
            return False
        # Truncate each TIME variant explicitly. An unparameterized truncate
        # can leave temporal cache entries behind on some GWC versions.
        if not self.truncate(layer.name, times=times, style_name=style_name):
            log.error(f"GWC truncate failed for {layer.name}")
            return False
        seeded = self.seed(layer.name, wait=True, times=times, style_name=style_name)
        if not seeded:
            log.error(f"GWC seed failed for {layer.name} at {times}")
        return seeded

    def seed_new_times(
        self,
        layer_name: str,
        new_times: List[str],
        store_name: Optional[str] = None,
        wait: bool = True,
        style_name: Optional[str] = None,
    ) -> bool:
        """Seed only the given TIME values without truncating the layer cache.

        This is useful for incremental updates where only new granules have
        arrived (e.g. radar) and you want to add those timestamps to the GWC
        cache without removing already-cached older tiles.

        The method skips the full truncate + granule-discover cycle and seeds
        only the supplied ``new_times``. If ``wait`` is True, blocks until
        each seed request's queue drains.

        Args:
            layer_name: Layer name without workspace prefix.
            new_times: ISO8601 TIME values to seed (only these will be seeded).
            store_name: Optional coverage store name (defaults to layer_name).
            wait: When True, blocks until each seed queue drains.
            style_name: Optional effective style name. When omitted, resolved
                       from GeoServer as in ``seed()``.

        Returns:
            True if every requested TIME was seeded successfully, False otherwise.
        """
        if not self.enabled:
            return True

        if not new_times:
            log.info(f"No new TIME values to seed for {layer_name}")
            return True

        style_name = style_name or self.get_default_style(layer_name)
        if not style_name:
            log.error(f"Could not resolve default style for {layer_name}")
            return False

        seeded_all = True
        for time_value in new_times:
            if not self._seed_request(
                layer_name, "seed", time_value, thread_count=2, style_name=style_name
            ):
                seeded_all = False
                continue
            if wait and not self._wait_for_seed_completion(layer_name):
                seeded_all = False
                # Continue seeding remaining times even if one waits timeouts.
        if seeded_all:
            log.info(f"Seeded {len(new_times)} new TIME values for {layer_name}")
        else:
            log.warning(
                f"Some TIME values failed to seed for {layer_name}: {new_times}"
            )
        return seeded_all

    @staticmethod
    def _normalize_time(value: str) -> str:
        """Use JavaScript Date.toISOString() form for matching Leaflet cache keys."""
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return (
            parsed.astimezone(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
