"""Tests for GWC caching and seed completion in cache.py."""

import sys
import types
from xml.etree import ElementTree
from unittest.mock import MagicMock, patch

from maps.datasets import cache
from maps.datasets.cache import GWCInvalidator, TemporalCacheLayer

# Legacy mock targets in this suite use ``datasets.cache``. Keep that alias
# while the application package is namespaced as ``maps.datasets``.
datasets_module = types.ModuleType("datasets")
datasets_module.__path__ = []
sys.modules.setdefault("datasets", datasets_module)
sys.modules.setdefault("datasets.cache", cache)
import requests as requests_lib


class TestGWCSeedCompletion:
    """Test the synchronous GWC seed completion mechanism."""

    def setup_method(self):
        self.global_quota_patch = patch.object(cache, "GWC_GLOBAL_QUOTA_MIB", 1024)
        self.global_quota_patch.start()
        self.invalidator = GWCInvalidator(
            geoserver_url="http://localhost:8080/geoserver",
            username="admin",
            password="password",
            workspace="meteohub",
        )

    def teardown_method(self):
        self.global_quota_patch.stop()

    def test_radar_cache_policy_and_seed_zoom_range(self):
        from maps.datasets.manifest import load_manifest

        radar = next(
            config for config in load_manifest(self.invalidator.manifest_path)
            if config.identifier == "radar"
        )
        policy = radar.geoserver["cache"]
        invalidator = GWCInvalidator(
            "http://geoserver", "user", "password", "meteohub",
            enabled=True, zoom_start=policy["zoom_start"], zoom_stop=policy["zoom_stop"],
        )
        assert invalidator._cache_expiry_seconds("radar-sri") == 259200
        assert invalidator._cache_expiry_seconds("radar-srt") == 259200
        assert invalidator._cache_expiry_seconds("t2m-t2m") == 86400
        with patch.object(cache.requests, "post", return_value=MagicMock(status_code=200)) as post:
            assert invalidator.seed("radar-sri", times=["2026-09-18T10:00:00Z"], wait=False)
        payload = post.call_args.kwargs["data"]
        assert "<zoomStart>5</zoomStart>" in payload
        assert "<zoomStop>9</zoomStop>" in payload

    def test_direct_wms_integration_preserves_settings_and_reloads(self):
        response = MagicMock(
            status_code=200,
            content=b"""<GeoServerGWCConfig>
            <directWMSIntegrationEnabled>true</directWMSIntegrationEnabled>
            <requireTiledParameter>true</requireTiledParameter>
            </GeoServerGWCConfig>""",
        )
        with patch.object(cache.requests, "get", return_value=response), patch.object(
            cache.requests, "put", return_value=MagicMock(status_code=200)
        ) as update, patch.object(
            cache.requests, "post", return_value=MagicMock(status_code=200)
        ) as reload:
            assert self.invalidator.disable_direct_wms_integration()
        payload = update.call_args.kwargs["data"]
        assert b"<directWMSIntegrationEnabled>false</directWMSIntegrationEnabled>" in payload
        assert b"<requireTiledParameter>true</requireTiledParameter>" in payload
        assert reload.call_args.args[0].endswith("/rest/reload")

    def test_direct_wms_integration_already_disabled_needs_no_reload(self):
        response = MagicMock(
            status_code=200,
            content=b"""<GeoServerGWCConfig>
            <directWMSIntegrationEnabled>false</directWMSIntegrationEnabled>
            </GeoServerGWCConfig>""",
        )
        with patch.object(cache.requests, "get", return_value=response), patch.object(
            cache.requests, "put"
        ) as update, patch.object(cache.requests, "post") as reload:
            assert self.invalidator.disable_direct_wms_integration()
        update.assert_not_called()
        reload.assert_not_called()

    def test_parallel_seed_bounds_batches_and_preserves_every_time(self):
        events = []
        times = [f"time-{index}" for index in range(9)]

        def submit(layer, seed_type, time_value, **kwargs):
            events.append(time_value)
            assert kwargs["thread_count"] == 1
            return True

        def wait(layer):
            events.append("wait")
            return True

        with patch.object(self.invalidator, "_seed_request", side_effect=submit), patch.object(
            self.invalidator, "_wait_for_seed_completion", side_effect=wait
        ):
            assert self.invalidator.seed("radar-sri", times=times, parallelism=4)
        assert events == times[:4] + ["wait"] + times[4:8] + ["wait"] + times[8:] + ["wait"]

    def test_existing_radar_layer_gets_three_day_expiry(self):
        response = MagicMock(
            status_code=200,
            content=b"""<GeoServerLayer><expireCache>86400</expireCache>
            <parameterFilters><regexParameterFilter><key>TIME</key>
            </regexParameterFilter></parameterFilters></GeoServerLayer>""",
        )
        with patch.object(cache.requests, "get", return_value=response), patch.object(
            cache.requests, "put", return_value=MagicMock(status_code=200)
        ) as update, patch.object(self.invalidator, "_ensure_grid_set", return_value=True):
            with patch.object(self.invalidator, "ensure_disk_quota", return_value=True):
                assert self.invalidator.ensure_time_parameter_filter("radar-sri")
        assert b"<expireCache>259200</expireCache>" in update.call_args.kwargs["data"]

    def test_disk_quota_creates_persistent_independent_layer_limits(self):
        with patch.object(cache.requests, "get", return_value=MagicMock(status_code=404)), patch.object(
            cache.requests, "put", return_value=MagicMock(status_code=201)
        ) as update, patch.object(
            cache.requests, "post", return_value=MagicMock(status_code=200)
        ) as reload:
            assert self.invalidator.ensure_disk_quota(["radar-sri", "radar-srt"])
        assert update.call_args.args[0].endswith("/rest/resource/gwc/geowebcache-diskquota.xml")
        config = ElementTree.fromstring(update.call_args.kwargs["data"])
        assert config.findtext("enabled") == "true"
        assert config.findtext("globalQuota/value") == "1024"
        assert config.findtext("globalQuota/units") == "MiB"
        entries = config.findall("layerQuotas/LayerQuota")
        assert {q.findtext("layer") for q in entries} == {"meteohub:radar-sri", "meteohub:radar-srt"}
        for entry in entries:
            assert entry.findtext("expirationPolicyName") == "LRU"
            assert entry.findtext("quota/value") == "1024"
            assert entry.findtext("quota/units") == "MiB"
        reload.assert_called_once()

    def test_disk_quota_preserves_other_layers_and_cleanup_settings(self):
        config_xml = b"""<gwcQuotaConfiguration xmlns="http://geowebcache.org/diskquota">
        <enabled>false</enabled><cacheCleanUpFrequency>30</cacheCleanUpFrequency>
        <globalQuota><value>20</value><units>GiB</units></globalQuota>
        <layerQuotas><LayerQuota><layer>other:layer</layer><expirationPolicyName>LFU</expirationPolicyName>
        <quota><value>2</value><units>GiB</units></quota></LayerQuota>
        <LayerQuota><layer>meteohub:radar-sri</layer><expirationPolicyName>LFU</expirationPolicyName>
        <quota><value>5</value><units>GiB</units></quota></LayerQuota></layerQuotas>
        </gwcQuotaConfiguration>"""
        with patch.object(cache.requests, "get", return_value=MagicMock(status_code=200, content=config_xml)), patch.object(
            cache.requests, "put", return_value=MagicMock(status_code=200)
        ) as update, patch.object(cache.requests, "post", return_value=MagicMock(status_code=200)):
            assert self.invalidator.ensure_disk_quota(["radar-sri"])
        config = ElementTree.fromstring(update.call_args.kwargs["data"])
        assert config.findtext("cacheCleanUpFrequency") == "30"
        assert config.findtext("globalQuota/value") == "1024"
        entries = {q.findtext("layer"): q for q in config.find("layerQuotas")}
        assert entries["other:layer"].findtext("quota/value") == "2"
        assert entries["meteohub:radar-sri"].findtext("quota/value") == "1024"

    def test_disk_quota_uses_configured_mib_limit(self):
        with patch.object(cache, "GWC_LAYER_QUOTA_MIB", 512), patch.object(
            cache.requests, "get", return_value=MagicMock(status_code=404)
        ), patch.object(
            cache.requests, "put", return_value=MagicMock(status_code=201)
        ) as update, patch.object(
            cache.requests, "post", return_value=MagicMock(status_code=200)
        ):
            assert self.invalidator.ensure_disk_quota(["radar-sri"])
        config = ElementTree.fromstring(update.call_args.kwargs["data"])
        assert config.findtext("layerQuotas/LayerQuota/quota/value") == "512"
        assert config.findtext("layerQuotas/LayerQuota/quota/units") == "MiB"

    def test_disk_quota_already_configured_is_noop(self):
        xml = b"""<gwcQuotaConfiguration><enabled>true</enabled>
        <globalQuota><value>1</value><units>GiB</units></globalQuota><layerQuotas>
        <LayerQuota><layer>meteohub:radar-sri</layer><expirationPolicyName>LRU</expirationPolicyName>
        <quota><value>1</value><units>GiB</units></quota></LayerQuota>
        </layerQuotas></gwcQuotaConfiguration>"""
        with patch.object(cache.requests, "get", return_value=MagicMock(status_code=200, content=xml)), patch.object(
            cache.requests, "put"
        ) as update, patch.object(cache.requests, "post") as reload:
            assert self.invalidator.ensure_disk_quota(["radar-sri"])
        update.assert_not_called()
        reload.assert_not_called()

    def test_global_quota_explicit_override_skips_layer_count_lookup(self):
        with patch.object(cache, "GWC_GLOBAL_QUOTA_MIB", 8192), patch.object(
            cache.requests, "get", return_value=MagicMock(status_code=404)
        ) as lookup, patch.object(
            cache.requests, "put", return_value=MagicMock(status_code=201)
        ) as update, patch.object(cache.requests, "post", return_value=MagicMock(status_code=200)):
            assert self.invalidator.ensure_disk_quota(["radar-sri"])
        lookup.assert_called_once()
        config = ElementTree.fromstring(update.call_args.kwargs["data"])
        assert config.findtext("globalQuota/value") == "8192"

    def test_global_quota_auto_counts_live_layers_during_single_layer_update(self):
        existing = b"""<gwcQuotaConfiguration><enabled>true</enabled>
        <globalQuota><value>500</value><units>MiB</units></globalQuota><layerQuotas>
        <LayerQuota><layer>meteohub:deleted</layer><expirationPolicyName>LRU</expirationPolicyName>
        <quota><value>512</value><units>MiB</units></quota></LayerQuota>
        </layerQuotas></gwcQuotaConfiguration>"""
        listing = b"""<layers><layer><name>meteohub:radar-sri</name></layer>
        <layer><name>meteohub:radar-srt</name></layer>
        <layer><name>other:layer</name></layer></layers>"""
        with patch.object(cache, "GWC_GLOBAL_QUOTA_MIB", None), patch.object(
            cache, "GWC_LAYER_QUOTA_MIB", 512
        ), patch.object(cache.requests, "get", side_effect=[
            MagicMock(status_code=200, content=existing),
            MagicMock(status_code=200, content=listing),
        ]) as lookup, patch.object(
            cache.requests, "put", return_value=MagicMock(status_code=200)
        ) as update, patch.object(cache.requests, "post", return_value=MagicMock(status_code=200)):
            assert self.invalidator.ensure_disk_quota(["radar-sri"])
        assert lookup.call_args.args[0].endswith("/gwc/rest/layers.xml")
        config = ElementTree.fromstring(update.call_args.kwargs["data"])
        assert config.findtext("globalQuota/value") == "1536"
        assert config.findtext("globalQuota/units") == "MiB"

    def test_global_quota_auto_empty_catalog(self):
        with patch.object(cache, "GWC_GLOBAL_QUOTA_MIB", None), patch.object(
            cache.requests, "get", side_effect=[
                MagicMock(status_code=404),
                MagicMock(status_code=200, content=b"<layers/>"),
            ]
        ), patch.object(cache.requests, "put", return_value=MagicMock(status_code=201)) as update, patch.object(
            cache.requests, "post", return_value=MagicMock(status_code=200)
        ):
            assert self.invalidator.ensure_disk_quota([])
        config = ElementTree.fromstring(update.call_args.kwargs["data"])
        assert config.findtext("globalQuota/value") == "0"

    def test_global_quota_auto_lookup_failure_does_not_persist(self):
        for response in [
            MagicMock(status_code=500),
            MagicMock(status_code=200, content=b"invalid"),
            MagicMock(status_code=200, content=b"<unexpected/>"),
        ]:
            with patch.object(cache, "GWC_GLOBAL_QUOTA_MIB", None), patch.object(
                cache.requests, "get", side_effect=[MagicMock(status_code=404), response]
            ), patch.object(cache.requests, "put") as update:
                assert not self.invalidator.ensure_disk_quota(["radar-sri"])
            update.assert_not_called()

    def test_disk_quota_lookup_failure_does_not_overwrite_configuration(self):
        for response in [MagicMock(status_code=500), MagicMock(status_code=200, content=b"invalid")]:
            with patch.object(cache.requests, "get", return_value=response), patch.object(cache.requests, "put") as update:
                assert not self.invalidator.ensure_disk_quota(["radar-sri"])
            update.assert_not_called()

    def test_disk_quota_update_failure_does_not_reload(self):
        with patch.object(cache.requests, "get", return_value=MagicMock(status_code=404)), patch.object(
            cache.requests, "put", return_value=MagicMock(status_code=500)
        ), patch.object(cache.requests, "post") as reload:
            assert not self.invalidator.ensure_disk_quota(["radar-sri"])
        reload.assert_not_called()

    def test_disk_quota_disabled_is_noop(self):
        self.invalidator.enabled = False
        with patch.object(cache.requests, "get") as lookup:
            assert self.invalidator.ensure_disk_quota(["radar-sri"])
        lookup.assert_not_called()

    def test_parallel_no_wait_drains_earlier_batches(self):
        with patch.object(self.invalidator, "_seed_request", return_value=True) as submit, patch.object(
            self.invalidator, "_wait_for_seed_completion", return_value=True
        ) as wait:
            assert self.invalidator.seed("radar-sri", times=list(range(9)), parallelism=4, wait=False)
        assert submit.call_count == 9
        assert wait.call_count == 2

    def test_parallel_seed_stops_on_failed_batch(self):
        with patch.object(self.invalidator, "_seed_request", return_value=True) as submit, patch.object(
            self.invalidator, "_wait_for_seed_completion", return_value=False
        ):
            assert not self.invalidator.seed("radar-sri", times=list(range(9)), parallelism=4)
        assert submit.call_count == 4

    @patch('datasets.cache.requests.get')
    @patch('datasets.cache.requests.post')
    def test_wait_for_completion_succeeds_immediately(
        self, mock_post, mock_get
    ):
        """When seed request completes instantly, _wait should return True."""
        mock_post.return_value = MagicMock(status_code=200)
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "seedQueue": {
                    "inQueue": False,
                    "inProgress": False,
                    "tasks": [],
                }
            },
        )
        assert self.invalidator.seed("test_layer", wait=True) is True

    @patch('datasets.cache.requests.get')
    @patch('datasets.cache.requests.post')
    def test_wait_for_completion_drains_after_polls(
        self, mock_post, mock_get
    ):
        """When seed queue drains after several polls, _wait should return True."""
        mock_post.return_value = MagicMock(status_code=200)

        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                return MagicMock(
                    status_code=200,
                    json=lambda: {
                        "seedQueue": {
                            "inQueue": True,
                            "inProgress": True,
                            "tasks": [],
                        }
                    },
                )
            return MagicMock(
                status_code=200,
                json=lambda: {
                    "seedQueue": {
                        "inQueue": False,
                        "inProgress": False,
                        "tasks": [],
                    }
                },
            )

        mock_get.side_effect = side_effect

        with patch("datasets.cache.time.sleep") as ms:
            assert self.invalidator.seed("test_layer", wait=True) is True
            assert ms.call_count == 2

    @patch('datasets.cache.requests.get')
    @patch('datasets.cache.requests.post')
    def test_wait_for_completion_fails_on_task_failure(
        self, mock_post, mock_get
    ):
        """If a seed task fails, _wait should return False."""
        mock_post.return_value = MagicMock(status_code=200)
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "seedQueue": {
                    "inQueue": False,
                    "inProgress": False,
                    "tasks": [
                        {"status": "completed"},
                        {"status": "failed"},
                    ],
                }
            },
        )
        assert self.invalidator.seed("test_layer", wait=True) is False

    @patch('datasets.cache.requests.get')
    @patch('datasets.cache.requests.post')
    def test_wait_for_completion_timeout(self, mock_post, mock_get):
        """If seed queue never drains, _wait should return False after timeout."""
        mock_post.return_value = MagicMock(status_code=200)
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "seedQueue": {
                    "inQueue": True,
                    "inProgress": True,
                    "tasks": [],
                }
            },
        )
        with patch("datasets.cache.time.sleep"):
            result = self.invalidator._wait_for_seed_completion(
                "test_layer", timeout=1, poll_interval=1
            )
            assert result is False

    @patch('datasets.cache.requests.get')
    @patch('datasets.cache.requests.post')
    def test_wait_handles_flat_json_structure(
        self, mock_post, mock_get
    ):
        """GWC may return flat JSON without 'seedQueue' wrapper."""
        mock_post.return_value = MagicMock(status_code=200)
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "inQueue": False,
                "inProgress": False,
                "tasks": [],
            },
        )
        assert self.invalidator.seed("test_layer", wait=True) is True

    @patch('datasets.cache.requests.get')
    @patch('datasets.cache.requests.post')
    def test_wait_handles_http_error(self, mock_post, mock_get):
        """If poll returns non-200, it should keep polling."""
        mock_post.return_value = MagicMock(status_code=200)

        def side_effect(*args, **kwargs):
            if not hasattr(side_effect, 'called'):
                side_effect.called = True
                return MagicMock(status_code=500)
            return MagicMock(
                status_code=200,
                json=lambda: {
                    "inQueue": False,
                    "inProgress": False,
                    "tasks": [],
                },
            )

        mock_get.side_effect = side_effect
        side_effect.called = False

        with patch("datasets.cache.time.sleep"):
            assert self.invalidator._wait_for_seed_completion(
                "test_layer", timeout=3, poll_interval=1
            ) is True

    @patch('datasets.cache.requests.get')
    @patch('datasets.cache.requests.post')
    def test_wait_handles_json_parse_error(self, mock_post, mock_get):
        """If poll returns invalid JSON, it should keep polling."""
        mock_post.return_value = MagicMock(status_code=200)

        def side_effect(*args, **kwargs):
            if not hasattr(side_effect, 'called'):
                side_effect.called = True
                resp = MagicMock()
                resp.status_code = 200
                resp.json.side_effect = ValueError("Invalid JSON")
                return resp
            return MagicMock(
                status_code=200,
                json=lambda: {
                    "inQueue": False,
                    "inProgress": False,
                    "tasks": [],
                },
            )

        mock_get.side_effect = side_effect
        side_effect.called = False

        with patch("datasets.cache.time.sleep"):
            assert self.invalidator._wait_for_seed_completion(
                "test_layer", timeout=3, poll_interval=1
            ) is True

    @patch('datasets.cache.requests.get')
    @patch('datasets.cache.requests.post')
    def test_wait_handles_request_exception(self, mock_post, mock_get):
        """If poll raises RequestException, it should keep polling."""
        mock_post.return_value = MagicMock(status_code=200)

        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise requests_lib.RequestException("Network error")
            return MagicMock(
                status_code=200,
                json=lambda: {
                    "inQueue": False,
                    "inProgress": False,
                    "tasks": [],
                },
            )

        mock_get.side_effect = side_effect

        with patch("datasets.cache.time.sleep"):
            assert self.invalidator._wait_for_seed_completion(
                "test_layer", timeout=3, poll_interval=1
            ) is True

    def test_seed_without_wait_returns_true_on_accepted(self):
        """When wait=False, seed should return True if request accepted."""
        with patch(
            'datasets.cache.requests.post'
        ) as mock_post, patch(
            'datasets.cache.requests.get'
        ):
            mock_post.return_value = MagicMock(status_code=200)
            assert self.invalidator.seed("test_layer", wait=False) is True

    def test_seed_returns_false_on_failed_request(self):
        """When seed request fails, seed() should return False."""
        with patch(
            'datasets.cache.requests.post'
        ) as mock_post, patch(
            'datasets.cache.requests.get'
        ):
            mock_post.return_value = MagicMock(status_code=500)
            assert self.invalidator.seed("test_layer", wait=True) is False

    def test_normalizes_time_for_leaflet_cache_key(self):
        """Granule timestamps match JavaScript Date.toISOString() precision."""
        assert self.invalidator._normalize_time("2024-01-01T06:00:00Z") == (
            "2024-01-01T06:00:00.000Z"
        )
        assert self.invalidator._normalize_time("2024-01-01T07:30:15.25+01:00") == (
            "2024-01-01T06:30:15.250Z"
        )

    @patch('datasets.cache.requests.get')
    def test_get_granule_times_uses_explicit_coverage_store(self, mock_get):
        """WW3 can query its mosaic store rather than its published layer name."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "features": [
                    {"properties": {"time": "2024-01-01T06:00:00Z"}},
                ]
            },
        )

        assert self.invalidator.get_granule_times(
            "ww3_hs-hs", store_name="mosaic_ww3_hs-hs", all_times=True
        ) == ["2024-01-01T06:00:00.000Z"]
        assert "/coveragestores/mosaic_ww3_hs-hs/" in mock_get.call_args.args[0]

    @patch('datasets.cache.requests.get')
    @patch('datasets.cache.requests.post')
    def test_seed_submits_one_request_per_time_value(self, mock_post, mock_get):
        """GWC gets one serial seed request for each TIME cache key."""
        mock_post.return_value = MagicMock(status_code=200)
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "seedQueue": {
                    "inQueue": False,
                    "inProgress": False,
                    "tasks": [],
                }
            },
        )

        times = [
            "2024-01-01T00:00:00Z",
            "2024-01-01T06:00:00Z",
        ]
        assert self.invalidator.seed(
            "test_layer", wait=True, times=times, style_name="ww3_hs-hs"
        ) is True
        assert mock_post.call_count == 2
        first_payload = mock_post.call_args_list[0].kwargs["data"]
        second_payload = mock_post.call_args_list[1].kwargs["data"]
        assert "<format>image/png</format>" in first_payload
        assert "<string>STYLES</string>" in first_payload
        assert "<string>ww3_hs-hs</string>" in first_payload
        assert "<string>2024-01-01T00:00:00Z</string>" in first_payload
        assert "<string>2024-01-01T06:00:00Z</string>" in second_payload

    @patch('datasets.cache.requests.get')
    @patch('datasets.cache.requests.post')
    def test_truncate_waits_for_each_time_before_next_request(self, mock_post, mock_get):
        """Each temporal variant is deleted before the next one is submitted."""
        mock_post.return_value = MagicMock(status_code=200)
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"seedQueue": {"inQueue": False, "inProgress": False}},
        )

        assert self.invalidator.truncate(
            "test_layer",
            times=["2024-01-01T00:00:00.000Z", "2024-01-01T06:00:00.000Z"],
            style_name="test_style",
        ) is True
        assert mock_post.call_count == 2
        assert mock_get.call_count == 2
        assert all(
            "<type>truncate</type>" in call.kwargs["data"]
            for call in mock_post.call_args_list
        )

    @patch('datasets.cache.requests.get')
    @patch('datasets.cache.requests.post')
    def test_full_layer_truncate_has_no_parameter_map(self, mock_post, mock_get):
        """An unparameterized truncate removes all stale time/style variants."""
        mock_post.return_value = MagicMock(status_code=200)
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"seedQueue": {"inQueue": False, "inProgress": False}},
        )

        assert self.invalidator.truncate("test_layer") is True
        payload = mock_post.call_args.kwargs["data"]
        assert "<type>truncate</type>" in payload
        assert "<parameters>" not in payload

    @patch('datasets.cache.requests.get')
    def test_get_default_style(self, mock_get):
        """The effective WMS default style is used in the GWC cache key."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"layer": {"defaultStyle": {"name": "ww3_hs-hs"}}},
        )

        assert self.invalidator.get_default_style("ww3_hs-hs") == "ww3_hs-hs"
        assert "/rest/layers/meteohub:ww3_hs-hs.json" in mock_get.call_args.args[0]

    def test_refresh_temporal_layer_uses_full_refresh_lifecycle(self):
        """Published layers use one ordered cache lifecycle through the seam."""
        layer = TemporalCacheLayer("t2m-t2m", store_name="t2m-t2m")
        with patch.object(
            self.invalidator, "ensure_time_parameter_filter", return_value=True
        ) as filter_, patch.object(
            self.invalidator, "truncate", return_value=True
        ) as truncate, patch.object(
            self.invalidator,
            "get_granule_times",
            return_value=["2024-01-01T00:00:00.000Z"],
        ) as times, patch.object(
            self.invalidator, "get_default_style", return_value="t2m"
        ) as style, patch.object(
            self.invalidator, "seed", return_value=True
        ) as seed:
            assert self.invalidator.refresh_temporal_layer(layer) is True

        filter_.assert_called_once_with("t2m-t2m")
        times.assert_called_once_with("t2m-t2m", store_name="t2m-t2m", all_times=True)
        style.assert_called_once_with("t2m-t2m")
        truncate.assert_called_once_with(
            "t2m-t2m",
            times=["2024-01-01T00:00:00.000Z"],
            style_name="t2m",
        )
        seed.assert_called_once_with(
            "t2m-t2m",
            wait=True,
            times=["2024-01-01T00:00:00.000Z"],
            style_name="t2m",
        )

    @patch("datasets.cache.requests.get")
    @patch("datasets.cache.requests.put")
    def test_ensure_grid_set_declares_1024px_tiles(self, mock_put, mock_get):
        mock_get.return_value = MagicMock(
            status_code=500,
            text='Failed to get GridSet. A GridSet with name "EPSG:900913_1024" does not exist.',
        )
        mock_put.return_value = MagicMock(status_code=201)

        assert self.invalidator._ensure_grid_set() is True
        payload = mock_put.call_args.kwargs["data"]
        assert "<tileWidth>1024</tileWidth>" in payload
        assert "<tileHeight>1024</tileHeight>" in payload
        assert "<name>EPSG:900913_1024</name>" in payload
