"""GeoServer ImageMosaic temporal configuration generation."""

from pathlib import Path


INDEXER_TEMPLATE = (
    "PropertyCollectors=TimestampFileNameExtractorSPI[timeregex](time)\n"
    "TimeAttribute=time\n"
    "Schema=*the_geom:Polygon,location:String,time:java.util.Date\n"
)


def write_temporal_config(target_dir: Path, regex: str, date_format: str) -> None:
    """Write the two ImageMosaic temporal configuration files atomically enough for local use."""

    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "indexer.properties").write_text(INDEXER_TEMPLATE, encoding="utf-8")
    (target_dir / "timeregex.properties").write_text(
        f"regex={regex},format={date_format}\n", encoding="utf-8"
    )
