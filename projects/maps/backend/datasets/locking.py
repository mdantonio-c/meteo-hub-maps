"""Process and container safe locks for shared ingestion resources."""

import fcntl
import time
from pathlib import Path
from typing import Optional


class DatasetLock:
    """Advisory lock backed by a file on the shared GeoServer volume."""

    def __init__(self, directory: Path, name: str, timeout_seconds: float = 30.0) -> None:
        self.path = directory / f".{name}.lock"
        self.timeout_seconds = timeout_seconds
        self._handle: Optional[object] = None

    def __enter__(self) -> "DatasetLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+")
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._handle = handle
                return self
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    handle.close()
                    raise TimeoutError(f"timed out acquiring dataset lock {self.path}")
                time.sleep(0.1)

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self._handle is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None
