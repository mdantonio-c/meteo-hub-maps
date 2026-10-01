"""Tests for GeoServer/GWC startup initialization."""

from unittest.mock import MagicMock, patch

from maps.datasets.cache import GWCInvalidator
from maps.tasks.startup import (
    _get_all_layers,
    initialize_geoserver,
    GEOSERVER_URL,
    GEOSERVER_USER,
    GEOSERVER_PASSWORD,
    GEOSERVER_WORKSPACE,
)


class TestStartupInitialization:
    """Test GeoServer/GWC startup initialization tasks."""

    def test_get_all_layers_parses_workspace_layers(self):
        """Should return only layers in the specified workspace."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "layers": {
                "layer": [
                    {"name": "meteohub:layer1"},
                    {"name": "meteohub:layer2"},
                    {"name": "other:layer3"},
                ]
            }
        }

        with patch("maps.tasks.startup.requests.get", return_value=mock_response):
            layers = _get_all_layers(
                GEOSERVER_URL, GEOSERVER_USER, GEOSERVER_PASSWORD, GEOSERVER_WORKSPACE
            )

        assert layers == ["layer1", "layer2"]

    def test_get_all_layers_handles_single_layer_dict(self):
        """Should handle response with single layer as dict instead of list."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "layers": {"layer": {"name": "meteohub:single"}}
        }

        with patch("maps.tasks.startup.requests.get", return_value=mock_response):
            layers = _get_all_layers(
                GEOSERVER_URL, GEOSERVER_USER, GEOSERVER_PASSWORD, GEOSERVER_WORKSPACE
            )

        assert layers == ["single"]

    def test_get_all_layers_returns_empty_on_error(self):
        """Should return empty list when GeoServer returns error."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal error"

        with patch("maps.tasks.startup.requests.get", return_value=mock_response):
            layers = _get_all_layers(
                GEOSERVER_URL, GEOSERVER_USER, GEOSERVER_PASSWORD, GEOSERVER_WORKSPACE
            )

        assert layers == []

    def test_get_all_layers_returns_empty_on_exception(self):
        """Should return empty list when request fails."""
        with patch("maps.tasks.startup.requests.get", side_effect=Exception("Network error")):
            layers = _get_all_layers(
                GEOSERVER_URL, GEOSERVER_USER, GEOSERVER_PASSWORD, GEOSERVER_WORKSPACE
            )

        assert layers == []

    @patch("maps.tasks.startup._get_all_layers")
    @patch("maps.tasks.startup.GWCInvalidator")
    def test_initialize_geoserver_configures_all_layers(
        self, mock_invalidator_class, mock_get_layers
    ):
        """Should call ensure_time_parameter_filter for each layer."""
        mock_get_layers.return_value = ["layer1", "layer2", "layer3"]
        mock_invalidator = MagicMock()
        mock_invalidator.ensure_time_parameter_filter.return_value = True
        mock_invalidator_class.return_value = mock_invalidator

        result = initialize_geoserver()

        assert result is True
        assert mock_get_layers.call_count == 1
        mock_invalidator.ensure_disk_quota.assert_called_once_with(
            ["layer1", "layer2", "layer3"]
        )
        assert mock_invalidator.ensure_time_parameter_filter.call_count == 3
        mock_invalidator.ensure_time_parameter_filter.assert_any_call("layer1")
        mock_invalidator.ensure_time_parameter_filter.assert_any_call("layer2")
        mock_invalidator.ensure_time_parameter_filter.assert_any_call("layer3")

    @patch("maps.tasks.startup._get_all_layers")
    @patch("maps.tasks.startup.GWCInvalidator")
    def test_initialize_geoserver_returns_false_on_failures(
        self, mock_invalidator_class, mock_get_layers
    ):
        """Should return False when any layer configuration fails."""
        mock_get_layers.return_value = ["layer1", "layer2"]
        mock_invalidator = MagicMock()
        mock_invalidator.ensure_time_parameter_filter.side_effect = [True, False]
        mock_invalidator_class.return_value = mock_invalidator

        result = initialize_geoserver()

        assert result is False

    @patch("maps.tasks.startup._get_all_layers")
    @patch("maps.tasks.startup.GWCInvalidator")
    def test_initialize_geoserver_handles_exceptions_gracefully(
        self, mock_invalidator_class, mock_get_layers
    ):
        """Should continue processing other layers when one raises exception."""
        mock_get_layers.return_value = ["layer1", "layer2", "layer3"]
        mock_invalidator = MagicMock()
        mock_invalidator.ensure_time_parameter_filter.side_effect = [
            True,
            Exception("Failed"),
            True,
        ]
        mock_invalidator_class.return_value = mock_invalidator

        result = initialize_geoserver()

        assert result is False
        assert mock_invalidator.ensure_time_parameter_filter.call_count == 3

    @patch("maps.tasks.startup._get_all_layers")
    def test_initialize_geoserver_skips_when_no_layers(
        self, mock_get_layers
    ):
        """Should succeed without calling GWC when no layers exist."""
        mock_get_layers.return_value = []

        with patch("maps.tasks.startup.GWCInvalidator") as mock_invalidator_class:
            result = initialize_geoserver()

        assert result is True
        mock_invalidator_class.return_value.ensure_disk_quota.assert_not_called()

    @patch("maps.tasks.startup.initialize_geoserver")
    @patch("maps.tasks.startup.celery")
    def test_worker_init_sends_task(self, mock_celery, mock_init_task):
        """Worker init hook should send initialization task asynchronously."""
        from maps.tasks.startup import on_worker_init

        mock_app = MagicMock()
        mock_result = MagicMock()
        mock_result.id = "test-task-id"
        mock_init_task.apply_async.return_value = mock_result
        mock_celery.get_instance.return_value.celery_app = mock_app

        on_worker_init(sender=None)

        mock_init_task.apply_async.assert_called_once_with(queue="ingest")
