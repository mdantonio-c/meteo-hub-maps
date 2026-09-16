"""Small orchestration boundary around the existing GeoServer adapters."""

from pathlib import Path
from typing import List, Optional, Union
import os
import shutil
import requests


def atomic_copy_to_mosaic(target_dir: str, source_files: List[str], copy_fn=shutil.copy2) -> str:
    """Copy files to a temporary directory then atomically rename into place.

    This prevents GeoServer from reading a partially populated mosaic.  The
    caller should populate the temporary directory, write any index / temporal
    config files there, then call ``finalize_atomic_copy`` which renames the
    temp directory into *target_dir* in a single atomic ``os.rename`` call.
    All paths must reside on the same filesystem so ``rename`` is atomic on
    Linux.

    Returns the path of the temporary directory.  The caller is responsible
    for cleaning it up (via ``finalize_atomic_copy``) on success or on
    failure.
    """
    target_path = Path(target_dir).resolve()
    tmp_dir = str(target_path.parent / (target_path.name + ".tmp"))
    os.makedirs(tmp_dir, exist_ok=True)
    # Remove stale contents if temp dir already existed from a crashed run.
    for entry in os.listdir(tmp_dir):
        entry_path = os.path.join(tmp_dir, entry)
        if entry_path == str(target_path):
            continue
        if os.path.isfile(entry_path):
            os.remove(entry_path)
        elif os.path.isdir(entry_path):
            shutil.rmtree(entry_path)
    for src in source_files:
        copy_fn(src, os.path.join(tmp_dir, os.path.basename(src)))
    return tmp_dir


def finalize_atomic_copy(tmp_dir: str, target_dir: str) -> None:
    """Replace *target_dir* with *tmp_dir* using same-filesystem renames.

    A directory cannot be renamed over an existing non-empty directory. Move
    the prior target aside first, then restore it if installing the new copy
    fails. All paths reside on the same filesystem, so each individual rename
    is atomic.
    """
    target_path = Path(target_dir).resolve()
    tmp_path = Path(tmp_dir).resolve()
    backup_path = target_path.with_name(f"{target_path.name}.previous")
    try:
        if backup_path.exists():
            shutil.rmtree(backup_path)
        if target_path.exists():
            os.rename(str(target_path), str(backup_path))
        os.rename(str(tmp_path), str(target_path))
    except OSError as exc:
        try:
            if backup_path.exists() and not target_path.exists():
                os.rename(str(backup_path), str(target_path))
            shutil.rmtree(tmp_path, ignore_errors=True)
        except OSError:
            pass
        raise RuntimeError(f"atomic move {tmp_dir!r} -> {target_dir!r} failed: {exc}") from exc
    shutil.rmtree(backup_path, ignore_errors=True)


class GeoServerPublisher:
    """Publish one configured coverage without exposing HTTP details to datasets."""

    def __init__(self, url: str, username: str, password: str, workspace: str) -> None:
        self.url = url.rstrip("/")
        self.username = username
        self.password = password
        self.workspace = workspace

    def ensure_workspace(self) -> bool:
        from maps.tasks.geoserver_utils import create_workspace_generic

        return create_workspace_generic(
            self.url, self.username, self.password, self.workspace
        )

    def publish_mosaic(
        self,
        mosaic_path: str,
        store_name: str,
        layer_name: str,
        style_name: Optional[str] = None,
    ) -> bool:
        from maps.tasks.geoserver_utils import (
            associate_sld_with_layer_generic,
            publish_layer_generic,
            upload_geotiff_generic,
        )

        if not upload_geotiff_generic(
            self.url,
            mosaic_path,
            store_name,
            self.username,
            self.password,
            self.workspace,
        ):
            return False
        if not publish_layer_generic(
            self.url,
            store_name,
            layer_name,
            self.username,
            self.password,
            self.workspace,
        ):
            return False
        if style_name and not associate_sld_with_layer_generic(
            self.url,
            layer_name,
            style_name,
            self.username,
            self.password,
            self.workspace,
        ):
            return False
        return True

    def associate_slds(
        self,
        layer_name: str,
        sld_names: Union[str, List[str], None],
    ) -> bool:
        """Assign one or more SLDs (primary + alias) to a layer.

        Returns True when all applicable associations succeed (or no SLDs given).
        """
        from maps.tasks.geoserver_utils import associate_sld_with_layer_generic

        if not sld_names:
            return True

        styles = sld_names if isinstance(sld_names, list) else [sld_names]
        for style_name in styles:
            if not associate_sld_with_layer_generic(
                self.url,
                layer_name,
                style_name,
                self.username,
                self.password,
                self.workspace,
            ):
                return False
        return True

    def enable_time_dimension(
        self,
        store_name: str,
        layer_name: str,
        default_strategy: str = "MAXIMUM",
    ) -> bool:
        url = (
            f"{self.url}/rest/workspaces/{self.workspace}/coveragestores/"
            f"{store_name}/coverages/{layer_name}"
        )
        data = f"""
        <coverage>
            <enabled>true</enabled>
            <metadata>
                <entry key="time">
                    <dimensionInfo>
                        <enabled>true</enabled>
                        <presentation>LIST</presentation>
                        <units>ISO8601</units>
                        <defaultValue>
                            <strategy>{default_strategy}</strategy>
                        </defaultValue>
                    </dimensionInfo>
                </entry>
            </metadata>
        </coverage>
        """.strip()
        response = requests.put(
            url,
            data=data,
            headers={"Content-Type": "application/xml", "Accept": "application/xml"},
            auth=(self.username, self.password),
            timeout=30,
        )
        return response.status_code in (200, 201)
