"""Tests for GWC caching and seed completion in cache.py."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from unittest.mock import MagicMock, patch

from datasets.cache import GWCInvalidator
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
        assert "<string>STYLES</string>" in first_payload
        assert "<string>ww3_hs-hs</string>" in first_payload
        assert "<string>2024-01-01T00:00:00Z</string>" in first_payload
        assert "<string>2024-01-01T06:00:00Z</string>" in second_payload

    @patch('datasets.cache.requests.get')
    @patch('datasets.cache.requests.post')
    def test_truncate_queues_all_times_before_waiting(self, mock_post, mock_get):
        """All stale variants are queued before waiting to start any seed work."""
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
        assert mock_get.call_count == 1
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
