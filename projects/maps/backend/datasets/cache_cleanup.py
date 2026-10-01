"""Remove stale file-blobstore parameter metadata without truncating tiles."""

import logging
import os
import time
from pathlib import Path
from typing import Dict, Optional

log = logging.getLogger(__name__)
PARAMETER_MAX_AGE_SECONDS = 3 * 24 * 60 * 60


def cleanup_parameter_files(
    cache_root: Path, *, now: Optional[float] = None
) -> Dict[str, int]:
    """Delete metadata older than three days or lacking a sibling cache folder.

    GWC stores ``parameters-<hash>.properties`` beside directories named
    ``<gridset>_<zoom>_<hash>``. Any matching directory keeps recent metadata
    associated, even if the directory is empty. Only metadata files are removed;
    tile directories and ImageMosaic granules are never modified.
    """
    counts = {"scanned": 0, "expired": 0, "orphaned": 0, "errors": 0}
    cutoff = (time.time() if now is None else now) - PARAMETER_MAX_AGE_SECONDS
    try:
        with os.scandir(cache_root) as layers:
            for layer in layers:
                try:
                    if not layer.is_dir(follow_symlinks=False):
                        continue
                    with os.scandir(layer.path) as children:
                        entries = list(children)
                    hashes = {
                        entry.name.rpartition("_")[2]
                        for entry in entries
                        if "_" in entry.name and entry.is_dir(follow_symlinks=False)
                    }
                    for entry in entries:
                        if not (
                            entry.name.startswith("parameters-")
                            and entry.name.endswith(".properties")
                        ):
                            continue
                        try:
                            if not entry.is_file(follow_symlinks=False):
                                continue
                            parameter_hash = entry.name[
                                len("parameters-") : -len(".properties")
                            ]
                            if not parameter_hash:
                                continue
                            counts["scanned"] += 1
                            expired = (
                                entry.stat(follow_symlinks=False).st_mtime < cutoff
                            )
                            if expired or parameter_hash not in hashes:
                                os.unlink(entry.path)
                                counts["expired" if expired else "orphaned"] += 1
                        except FileNotFoundError:
                            # Truncation or another cleanup may remove it concurrently.
                            continue
                        except OSError:
                            counts["errors"] += 1
                            log.exception(
                                "Unable to remove GWC metadata %s", entry.path
                            )
                except FileNotFoundError:
                    continue
                except OSError:
                    counts["errors"] += 1
                    log.exception(
                        "Unable to inspect GWC layer directory %s", layer.path
                    )
    except FileNotFoundError:
        log.warning("GWC cache directory does not exist: %s", cache_root)
    except OSError:
        counts["errors"] += 1
        log.exception("Unable to inspect GWC cache directory %s", cache_root)
    log.info(
        "GWC parameter cleanup: %(scanned)d scanned, %(expired)d expired and "
        "%(orphaned)d orphaned files removed, %(errors)d errors",
        counts,
    )
    return counts
