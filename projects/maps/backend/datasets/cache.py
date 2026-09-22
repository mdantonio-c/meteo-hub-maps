"""GeoWebCache invalidation adapter."""

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional
from xml.etree import ElementTree

import requests

SEED_ZOOM_START = int(os.environ.get("GWC_ZOOM_START", "5"))
SEED_ZOOM_STOP = int(os.environ.get("GWC_ZOOM_STOP", "8"))
GWC_ENABLED_DEFAULT = os.environ.get("GEOSERVER_GWC_ENABLED", "1") == "1"
# Caps how many TIME values get an individual seed/truncate request per call,
# so a mosaic with a long history doesn't trigger hundreds of HTTP requests.
GWC_MAX_TIMES_PER_SEED = int(os.environ.get("GWC_MAX_TIMES_PER_SEED", "12"))
# GeoServer names its EPSG:3857 grid set with the legacy equivalent EPSG:900913.
WEB_MERCATOR_GRID_SET = "EPSG:900913"
# Ingestion explicitly removes stale entries. Expiry is a safety net when an
# ingestion fails before truncating its layer.
GWC_CACHE_EXPIRE_SECONDS = int(os.environ.get("GWC_CACHE_EXPIRE_SECONDS", "86400"))
GWC_CLIENT_EXPIRE_SECONDS = int(os.environ.get("GWC_CLIENT_EXPIRE_SECONDS", "86400"))
# Max seconds to wait for GWC seed queue to drain (tile generation).
GWC_SEED_WAIT_TIMEOUT = int(os.environ.get("GWC_SEED_WAIT_TIMEOUT", "300"))
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
        timeout: float = 30.0,
    ) -> None:
        self.base_url = geoserver_url.rstrip("/")
        self.username = username
        self.password = password
        self.workspace = workspace
        self.enabled = enabled if enabled is not None else GWC_ENABLED_DEFAULT
        self.timeout = timeout

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
            "  <zoomStart>{}</zoomStart>\n"
            "  <zoomStop>{}</zoomStop>\n"
            "  <threadCount>{}</threadCount>{}\n"
            "</seedRequest>"
        ).format(
            layer_id,
            seed_type,
            WEB_MERCATOR_GRID_SET,
            SEED_ZOOM_START,
            SEED_ZOOM_STOP,
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
            response = requests.get(url, auth=(self.username, self.password), timeout=self.timeout)
            if response.status_code != 200:
                return None
            return response.json().get("layer", {}).get("defaultStyle", {}).get("name")
        except (requests.RequestException, ValueError):
            return None

    def _wait_for_seed_completion(
        self, layer_name: str, timeout: float = GWC_SEED_WAIT_TIMEOUT,
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

                # GWC 2.x returns a flat structure with inQueue/inProgress at top level
                # Some versions wrap it under "seedQueue" key
                if "seedQueue" in data:
                    seed_queue = data["seedQueue"]
                else:
                    seed_queue = data

                in_queue = seed_queue.get("inQueue", False)
                in_progress = seed_queue.get("inProgress", False)

                # If both are false, seeding is complete
                if not in_queue and not in_progress:
                    # Check for any failed tasks as a safety net
                    tasks = seed_queue.get("tasks", [])
                    if tasks:
                        failed = any(t.get("status") == "failed" for t in tasks)
                        if failed:
                            return False
                    return True

                timeout -= poll_interval
                time.sleep(poll_interval)

            except (requests.RequestException, ValueError):
                timeout -= poll_interval
                time.sleep(poll_interval)

        return False

    def ensure_time_parameter_filter(self, layer_name: str) -> bool:
        """Configure GWC to cache distinct WMS TIME parameter values for a layer."""
        if not self.enabled:
            return True

        layer_id = f"{self.workspace}:{layer_name}"
        url = f"{self.base_url}/gwc/rest/layers/{layer_id}.xml"
        try:
            response = requests.get(url, auth=(self.username, self.password), timeout=self.timeout)
            if response.status_code != 200:
                return False
            layer = ElementTree.fromstring(response.content)
        except (requests.RequestException, ElementTree.ParseError):
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
            [item.findtext("gridSetName") for item in grid_subsets] if grid_subsets is not None else []
        )
        cache_expiry = layer.find("expireCache")
        client_expiry = layer.find("expireClients")
        cache_expiry_is_current = (
            cache_expiry is not None and cache_expiry.text == str(GWC_CACHE_EXPIRE_SECONDS)
        )
        client_expiry_is_current = (
            client_expiry is not None and client_expiry.text == str(GWC_CLIENT_EXPIRE_SECONDS)
        )
        if (
            current_grid_sets == [WEB_MERCATOR_GRID_SET]
            and not filter_added
            and cache_expiry_is_current
            and client_expiry_is_current
        ):
            return True
        if grid_subsets is not None:
            layer.remove(grid_subsets)
        grid_subsets = ElementTree.SubElement(layer, "gridSubsets")
        grid_subset = ElementTree.SubElement(grid_subsets, "gridSubset")
        ElementTree.SubElement(grid_subset, "gridSetName").text = WEB_MERCATOR_GRID_SET
        if cache_expiry is None:
            cache_expiry = ElementTree.SubElement(layer, "expireCache")
        cache_expiry.text = str(GWC_CACHE_EXPIRE_SECONDS)
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
            return False
        return response.status_code in (200, 201)

    def truncate(
        self,
        layer_name: str,
        times: Optional[Iterable[str]] = None,
        style_name: Optional[str] = None,
    ) -> bool:
        """Truncate one layer's GWC cache; disabled mode is an intentional no-op.

        Args:
            layer_name: Layer name without workspace prefix.
            times: Optional ISO8601 TIME dimension values to truncate individually.
                   When omitted, removes every cache variant for the layer,
                   including stale dates and styles no longer in the mosaic.
        """
        if not self.enabled:
            return True

        time_values = list(times) if times else [None]
        for time_value in time_values:
            if not self._seed_request(
                layer_name, "truncate", time_value, thread_count=1, style_name=style_name
            ):
                return False
        # Enqueue deletion for every time first, then wait once. This ensures
        # no seed task can be submitted until matching stale tiles are gone.
        return self._wait_for_seed_completion(layer_name)

    def seed(
        self,
        layer_name: str,
        wait: bool = True,
        times: Optional[Iterable[str]] = None,
        style_name: Optional[str] = None,
    ) -> bool:
        """Seed one layer's GWC cache for every requested TIME value.

        Args:
            layer_name: Layer name without workspace prefix.
            wait: When True, blocks until seed queue drains and tiles are
                  fully generated (not lazily cached on first user request).
            times: ISO8601 TIME values to seed. GWC can only seed one
                   parameter combination per request, so values are handled
                   serially just as they are in the GeoWebCache UI.

        Returns:
            True if every seed request was accepted and (if wait=True)
            completed successfully, False otherwise.
        """
        if not self.enabled:
            return True

        time_values = list(times) if times is not None else [None]
        for time_value in time_values:
            if not self._seed_request(
                layer_name, "seed", time_value, thread_count=2, style_name=style_name
            ):
                return False
            if wait and not self._wait_for_seed_completion(layer_name):
                return False
        return True

    def get_granule_times(self, layer_name: str, store_name: Optional[str] = None,
                          all_times: bool = False) -> List[str]:
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
            response = requests.get(url, auth=(self.username, self.password), timeout=self.timeout)
        except requests.RequestException:
            return []
        if response.status_code != 200:
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

    def refresh_temporal_layer(self, layer: TemporalCacheLayer) -> bool:
        """Replace every cached tile for one temporal layer after publication.

        The unparameterized truncate removes all stale GWC variants first. The
        current mosaic times and effective GeoServer style are then used to
        rebuild precisely the cache keys served to WMS clients.
        """
        if not self.enabled:
            return True
        if not self.ensure_time_parameter_filter(layer.name):
            return False
        if not self.truncate(layer.name):
            return False

        times = self.get_granule_times(
            layer.name, store_name=layer.store_name, all_times=True
        )
        if not times:
            return False
        style_name = self.get_default_style(layer.name)
        if not style_name:
            return False
        return self.seed(layer.name, wait=True, times=times, style_name=style_name)

    @staticmethod
    def _normalize_time(value: str) -> str:
        """Use JavaScript Date.toISOString() form for matching Leaflet cache keys."""
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        )
