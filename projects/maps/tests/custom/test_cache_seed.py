"""Tests for GWC caching and seed completion in cache.py."""

from unittest.mock import MagicMock, patch

from maps.datasets.cache import GWCInvalidator, TemporalCacheLayer
import requests as requests_lib


class TestGWCSeedCompletion:
    """Test the synchronous GWC seed completion mechanism."""

    def setup_method(self):
        self.invalidator = GWCInvalidator(
            geoserver_url="http://localhost:8080/geoserver",
            username="admin",
            password="password",
            workspace="meteohub",
        )

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
