"""Filesystem marker lifecycle shared by dataset adapters."""

from datetime import datetime
from pathlib import Path
from typing import Optional


class MarkerStore:
    """Read and write the marker files used to coordinate ingestion."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def path(self, identifier: str, suffix: str) -> Path:
        return self.directory / f"{identifier}{suffix}"

    def exists(self, identifier: str, suffix: str) -> bool:
        return self.path(identifier, suffix).is_file()

    def create(self, identifier: str, suffix: str, message: Optional[str] = None) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        marker = self.path(identifier, suffix)
        content = message or f"Processed: {datetime.now().isoformat()}\n"
        marker.write_text(content, encoding="utf-8")
        return marker

    def remove(self, identifier: str, suffix: str) -> None:
        marker = self.path(identifier, suffix)
        try:
            marker.unlink()
        except FileNotFoundError:
            pass

    def latest(self, suffix: str) -> Optional[Path]:
        if not self.directory.is_dir():
            return None
        markers = [
            path
            for path in self.directory.iterdir()
            if path.is_file() and path.name.endswith(suffix)
        ]
        return max(markers, key=lambda path: path.stat().st_mtime) if markers else None
