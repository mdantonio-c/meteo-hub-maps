"""Regression test for repeat Windy ImageMosaic ingestion."""

from unittest.mock import MagicMock, patch

from maps.datasets import windy_processing


@patch.object(windy_processing.requests, "post")
def test_publish_layer_accepts_existing_mosaic_coverage(mock_post):
    """A repeat run must refresh GWC even when GeoServer returns 409."""
    mock_post.return_value = MagicMock(status_code=409, text="Coverage already exists")

    assert windy_processing.publish_layer(
        "t2m-t2m", "t2m-t2m", "http://geoserver"
    ) is True
