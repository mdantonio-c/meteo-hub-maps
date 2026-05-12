#!/usr/bin/env python3
"""Generate zoom-grouped MER WMS BBOX dictionaries from a URL manifest file.

Default input:
- marine.txt (in the same folder as this script)

Default output:
- mer_wms_bboxes.py (in the same folder as this script)
"""

from __future__ import annotations

import argparse
import math
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ZOOM_HEADER_RE = re.compile(r"^\[zoom\s+(\d+)\]")
WEB_MERCATOR_WORLD_WIDTH = 40075016.68557849


def _derive_zoom_from_bbox(bbox: tuple[float, float, float, float]) -> int:
    """Derive the likely web-mercator zoom level from tile width."""
    tile_width = abs(bbox[2] - bbox[0])
    if tile_width <= 0:
        raise ValueError(f"Invalid bbox width for {bbox}")
    return int(round(math.log2(WEB_MERCATOR_WORLD_WIDTH / tile_width)))


def parse_manifest(manifest_path: Path) -> dict[int, list[tuple[float, float, float, float]]]:
    """Extract and deduplicate BBOX tuples from manifest URLs, grouped by zoom."""
    by_zoom: dict[int, list[tuple[float, float, float, float]]] = {}
    seen_per_zoom: dict[int, set[tuple[float, float, float, float]]] = {}

    current_zoom: int | None = None
    for raw_line in manifest_path.read_text().splitlines():
        line = raw_line.strip()
        if not line:
            continue

        zoom_match = ZOOM_HEADER_RE.match(line)
        if zoom_match:
            current_zoom = int(zoom_match.group(1))
            by_zoom.setdefault(current_zoom, [])
            seen_per_zoom.setdefault(current_zoom, set())
            continue

        if not line.startswith("http"):
            continue

        query = parse_qs(urlparse(line).query)
        bbox_values = query.get("bbox")
        if not bbox_values:
            continue

        parts = bbox_values[0].split(",")
        if len(parts) != 4:
            continue

        bbox = tuple(float(value) for value in parts)

        zoom = current_zoom if current_zoom is not None else _derive_zoom_from_bbox(bbox)
        by_zoom.setdefault(zoom, [])
        seen_per_zoom.setdefault(zoom, set())

        if bbox in seen_per_zoom[zoom]:
            continue

        seen_per_zoom[zoom].add(bbox)
        by_zoom[zoom].append(bbox)

    return by_zoom


def render_python_module(
    bboxes_by_zoom: dict[int, list[tuple[float, float, float, float]]],
    source_name: str,
) -> str:
    """Render module text for mer_wms_bboxes.py."""
    lines: list[str] = []
    lines.append('"""')
    lines.append("Static BBOX tile lists for MER WMS cache population, grouped by zoom level.")
    lines.append("")
    lines.append(f"Generated from {source_name} using generate_mer_wms_bboxes.py.")
    lines.append("Edit this file to add, remove, or adjust tile coverage.")
    lines.append('"""')
    lines.append("")
    lines.append("BBOXES_BY_ZOOM: dict[int, list[tuple[float, float, float, float]]] = {")

    for zoom in sorted(bboxes_by_zoom):
        bboxes = bboxes_by_zoom[zoom]
        lines.append(f"    # zoom {zoom} - {len(bboxes)} tiles")
        lines.append(f"    {zoom}: [")
        for min_x, min_y, max_x, max_y in bboxes:
            lines.append(f"        ({min_x!r}, {min_y!r}, {max_x!r}, {max_y!r}),")
        lines.append("    ],")

    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parents[3]

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help=(
            "Path to the manifest text file with GetMap URLs. "
            "If omitted, the script tries common repository locations."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=script_dir / "mer_wms_bboxes.py",
        help="Path to the generated Python output file.",
    )
    args = parser.parse_args()

    if args.input is not None:
        input_path = args.input.resolve()
    else:
        candidates = [
            script_dir / "marine.txt",
            repo_root / "projects/maps/confs/marine-wms-getmap-manifest.txt",
            repo_root / "data/MER/marine-wms-getmap-manifest.txt",
        ]
        existing_candidate = next((candidate for candidate in candidates if candidate.exists()), None)
        if existing_candidate is None:
            candidate_lines = "\n".join(f"- {candidate}" for candidate in candidates)
            raise FileNotFoundError(
                "No default manifest found. Provide --input explicitly. "
                f"Checked:\n{candidate_lines}"
            )
        input_path = existing_candidate

    output_path = args.output.resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"Input manifest not found: {input_path}")

    bboxes_by_zoom = parse_manifest(input_path)
    module_text = render_python_module(bboxes_by_zoom, input_path.name)

    output_path.write_text(module_text)
    print(f"Wrote {output_path}")
    for zoom in sorted(bboxes_by_zoom):
        print(f"zoom {zoom}: {len(bboxes_by_zoom[zoom])}")


if __name__ == "__main__":
    main()
