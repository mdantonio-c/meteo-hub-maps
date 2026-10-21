"""Seasonal mosaic publication and shared ready-file helpers."""

from restapi.env import Env
from restapi.utilities.logs import log
from typing import Optional
import os
import requests
from datetime import datetime
from .geoserver_utils import (
    create_ready_file_generic,
    update_slds_from_local_folders,
    upload_geotiff_generic,
    publish_layer_generic,
    associate_sld_with_layer_generic,
    check_style_exists,
)
from .windy_processing import enable_time_dimension
from maps.datasets.cache import TemporalCacheLayer
from maps.tasks.cache_control import schedule_cache_refresh_chord
from maps.utils.geoserver import GEOSERVER_REQUEST_TIMEOUT

# Get GeoServer credentials for seasonal task
GEOSERVER_URL = "http://geoserver.dockerized.io:8080/geoserver"
USERNAME = Env.get("GEOSERVER_ADMIN_USER", None)
PASSWORD = Env.get("GEOSERVER_ADMIN_PASSWORD", None)
WORKSPACE = "meteohub"

# Mapping of seasonal directories to their corresponding names in copies
seasonal_to_copies_mapping = {
    "ano_max_TM": "seasonal-ano-max-TM",
    "ano_min_Tm": "seasonal-ano-min-Tm",
    "ano_P": "seasonal-ano-P",
    "mean_TM": "seasonal-mean-TM",
    "mean_Tm": "seasonal-mean-Tm",
    "sum_P": "seasonal-sum-P",
}


def create_seasonal_ready_file(base_path, date_identifier: str) -> None:
    """Create a ready file to indicate that the seasonal process is complete."""
    create_ready_file_generic(base_path, date_identifier, "seasonal")


def process_seasonal_tiff_files(
    base_path: str, sld_directory, geoserver_url, username, password, date_identifier
) -> list:
    """Iterate over seasonal TIFF files and upload them to GeoServer with temporal dimension.
    
    Args:
        base_path: Base path for seasonal data directory
        sld_directory: SLD directory path
        geoserver_url: GeoServer URL
        username: GeoServer admin username
        password: GeoServer admin password
        date_identifier: Date identifier for the run
    """
    create_workspace_generic(geoserver_url, username, password)

    # Clean up old seasonal stores first
    from .geoserver_utils import cleanup_old_seasonal_stores

    cleanup_old_seasonal_stores(geoserver_url, username, password, date_identifier)

    # Update SLD files from local folders to GeoServer BEFORE processing layers
    log.info(f"Updating seasonal SLD files from directory: {sld_directory}")
    sld_update_success = update_slds_from_local_folders(
        sld_directory, geoserver_url, username, password
    )
    if not sld_update_success:
        log.warning("Some SLD updates failed, but continuing with processing")
    else:
        log.info("Successfully updated all seasonal SLD files")

    # Process each seasonal subdirectory
    seasonal_subdirs = [
        "ano_max_TM",
        "ano_min_Tm",
        "ano_P",
        "mean_TM",
        "mean_Tm",
        "sum_P",
    ]

    cache_layers = []
    for subdir in seasonal_subdirs:
        subdir_path = os.path.join(base_path, subdir)
        if not os.path.exists(subdir_path):
            log.warning(f"Seasonal subdirectory not found: {subdir_path}")
            continue

        log.info(f"Processing seasonal subdirectory: {subdir}")

        # Create copies directory for temporal mosaics
        copies_base = "/geoserver_data/copies"
        seasonal_copies_name = seasonal_to_copies_mapping.get(subdir)
        if not seasonal_copies_name:
            log.warning(f"No copies mapping found for seasonal directory: {subdir}")
            continue

        copies_target = os.path.join(copies_base, seasonal_copies_name)

        # Remove old files from copies directory before copying new ones
        import shutil

        if os.path.exists(copies_target):
            log.info(f"Cleaning existing copies directory: {copies_target}")
            shutil.rmtree(copies_target)

        os.makedirs(copies_target, exist_ok=True)
        log.info(f"Created clean copies directory: {copies_target}")

        # Copy TIFF files to copies directory for mosaic creation
        tiff_files_copied = 0
        for file in os.listdir(subdir_path):
            if file.endswith((".tif", ".tiff")):
                source_file = os.path.join(subdir_path, file)
                target_file = os.path.join(copies_target, file)

                try:
                    shutil.copy2(source_file, target_file)
                    tiff_files_copied += 1
                    log.debug(f"Copied seasonal file: {file}")
                except Exception as e:
                    log.error(f"Failed to copy seasonal file {file}: {e}")

        if tiff_files_copied > 0:
            log.info(
                f"Copied {tiff_files_copied} seasonal TIFF files to {seasonal_copies_name}"
            )

            # Create temporal mosaic configuration files
            create_seasonal_temporal_config(copies_target, seasonal_copies_name)

            # Create and publish temporal mosaic in GeoServer
            store_name = f"mosaic_{seasonal_copies_name}"
            layer_name = seasonal_copies_name

            # Upload as ImageMosaic (temporal) - use generic function directly to preserve path handling
            if upload_geotiff_generic(
                geoserver_url, copies_target, store_name, username, password
            ):
                # Publish the temporal layer
                if publish_layer_generic(
                    geoserver_url,
                    store_name,
                    layer_name,
                    username,
                    password,
                    coverage_name=layer_name,
                ):
                    # Enable temporal dimension using custom function for seasonal data
                    enable_seasonal_time_dimension(
                        geoserver_url, store_name, layer_name, username, password
                    )

                    # Find and associate appropriate SLD
                    sld_name = find_seasonal_sld_mapping(subdir)
                    if sld_name:
                        log.info(
                            f"Found SLD mapping: '{subdir}' -> '{sld_name}' for layer '{layer_name}'"
                        )

                        # Check if the SLD style exists in GeoServer
                        style_exists = check_style_exists(
                            geoserver_url, sld_name, username, password
                        )
                        if style_exists:
                            log.info(
                                f"SLD style '{sld_name}' exists in GeoServer, proceeding with association"
                            )
                            sld_success = associate_sld_with_layer(
                                geoserver_url, layer_name, sld_name, username, password
                            )
                            if sld_success:
                                log.info(
                                    f"Successfully processed seasonal temporal layer: {layer_name} with SLD: {sld_name}"
                                )
                                cache_layers.append(
                                    TemporalCacheLayer(
                                        layer_name, store_name=store_name
                                    )
                                )
                            else:
                                log.error(
                                    f"Failed to associate SLD '{sld_name}' with layer '{layer_name}'"
                                )
                        else:
                            log.error(
                                f"SLD style '{sld_name}' does not exist in GeoServer - check SLD upload process"
                            )
                    else:
                        log.warning(
                            f"No SLD mapping found for seasonal directory: {subdir}, layer: {layer_name}"
                        )
                else:
                    log.error(
                        f"Failed to publish seasonal temporal layer: {layer_name}"
                    )
            else:
                log.error(f"Failed to upload seasonal temporal mosaic: {store_name}")
        else:
            log.warning(f"No TIFF files found in seasonal directory: {subdir_path}")

    log.info(
        f"Completed processing all seasonal subdirectories for date: {date_identifier}"
    )
    return cache_layers


def create_seasonal_temporal_config(target_dir: str, layer_name: str) -> None:
    """Create temporal mosaic configuration files for seasonal data."""

    # Create indexer.properties with temporal dimension
    #     indexer_content = f"""PropertyCollectors=TimestampFileNameExtractorSPI[timeregex](time)
    # TimeAttribute=time
    # Schema=*the_geom:Polygon,location:String,time:java.util.Date
    # Name={layer_name}
    # TypeName={layer_name}
    # Levels=1.0
    # LevelsNum=1
    # Heterogeneous=false
    # AbsolutePath=false
    # LocationAttribute=location
    # SuggestedSPI=it.geosolutions.imageioimpl.plugins.tiff.TIFFImageReaderSpi
    # CheckAuxiliaryMetadata=false
    # """
    indexer_content = f"""PropertyCollectors=TimestampFileNameExtractorSPI[timeregex](time)
    TimeAttribute=time
    Schema=*the_geom:Polygon,location:String,time:java.util.Date
"""

    indexer_path = os.path.join(target_dir, "indexer.properties")
    try:
        with open(indexer_path, "w") as f:
            f.write(indexer_content)
        log.info(f"Created temporal indexer.properties for {layer_name}")
    except Exception as e:
        log.error(f"Failed to create temporal indexer.properties for {layer_name}: {e}")

    # Create timeregex.properties for seasonal date extraction
    # Seasonal files typically have format: ano_P_20251028.tif (YYYYMMDD)
    timeregex_content = "regex=.*([0-9]{8}).*,format=yyyyMMdd\n"

    timeregex_path = os.path.join(target_dir, "timeregex.properties")
    try:
        with open(timeregex_path, "w") as f:
            f.write(timeregex_content)
        log.info(f"Created timeregex.properties for {layer_name}")
    except Exception as e:
        log.error(f"Failed to create timeregex.properties for {layer_name}: {e}")

    # Create layer properties file


#     properties_content = f"""Name={layer_name}
# TypeName={layer_name}
# AbsolutePath=false
# Caching=false
# ExpandToRGB=false
# LocationAttribute=location
# TimeAttribute=time
# """

#     properties_path = os.path.join(target_dir, f"{layer_name}.properties")
#     try:
#         with open(properties_path, 'w') as f:
#             f.write(properties_content)
#         log.info(f"Created temporal {layer_name}.properties")
#     except Exception as e:
#         log.error(f"Failed to create temporal {layer_name}.properties: {e}")


def enable_seasonal_time_dimension(
    geoserver_url: str, store_name: str, layer_name: str, username: str, password: str
) -> bool:
    """Enable temporal dimension for seasonal layers."""
    # The URL needs to use the store name for the coverage store and layer name for the coverage
    url = f"{geoserver_url}/rest/workspaces/{WORKSPACE}/coveragestores/{store_name}/coverages/{layer_name}"
    headers = {"Content-Type": "application/xml", "Accept": "application/xml"}
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
                        <strategy>MINIMUM</strategy>
                    </defaultValue>
                </dimensionInfo>
            </entry>
        </metadata>
    </coverage>
    """.strip()

    response = requests.put(
        url,
        data=data,
        headers=headers,
        auth=(username, password),
        timeout=GEOSERVER_REQUEST_TIMEOUT,
    )
    if response.status_code not in [200, 201]:
        log.error(f"Failed to enable time dimension for {layer_name}: {response.text}")
        return False
    log.info(f"Successfully enabled time dimension for seasonal layer: {layer_name}")
    return True


def find_seasonal_sld_mapping(seasonal_dir: str) -> Optional[str]:
    """Find the appropriate SLD for a seasonal directory."""
    seasonal_sld_mapping = {
        "ano_max_TM": "temp_anomaly",
        "ano_min_Tm": "temp_anomaly",
        "ano_P": "precip_anomaly",
        "mean_TM": "t2m",
        "mean_Tm": "t2m",
        "sum_P": "precip_sum",
    }

    sld_name = seasonal_sld_mapping.get(seasonal_dir)
    if sld_name:
        log.info(f"Found SLD '{sld_name}' for seasonal directory '{seasonal_dir}'")
        return sld_name

    log.warning(f"No SLD mapping found for seasonal directory: {seasonal_dir}")
    return None


def update_slds_from_local(
    self,
    geoserver_url: str = GEOSERVER_URL,
    username: str = USERNAME,
    password: str = PASSWORD,
    sld_base_directory: Optional[str] = "/SLDs",
) -> None:
    """Update GeoServer SLD styles from local folder structure."""
    log.info(f"Updating GeoServer SLD styles from local folders: {sld_base_directory}")

    if not sld_base_directory:
        log.error("No SLD base directory specified")
        return

    # Update SLD files from local folders to GeoServer
    success = update_slds_from_local_folders(
        sld_base_directory, geoserver_url, username, password
    )

    if success:
        log.info("Successfully updated all SLD styles from local folders")
    else:
        log.warning("Some SLD updates failed - check logs for details")


def update_geoserver_seasonal_layers(
    self=None,
    date: str = datetime.now().strftime("%Y%m%d"),
    geoserver_url: str = GEOSERVER_URL,
    username: str = USERNAME,
    password: str = PASSWORD,
    sld_directory: Optional[str] = None,
    cache_config=None,
    base_path: Optional[str] = None,
) -> None:
    """Update GeoServer with seasonal layers following the same pattern as windy layers.
    
    Args:
        date: Run date identifier
        geoserver_url: GeoServer URL
        username: GeoServer admin username
        password: GeoServer admin password
        sld_directory: SLD directory path
        cache_config: GeoServer cache configuration
        base_path: Base path for seasonal data. If None, uses env var or default.
    """
    if base_path is None:
        base_path = Env.get("SEASONAL_DATA_PATH", "/seasonal-aim")
    
    log.info(
        f"Updating GeoServer seasonal layers with temporal dimension for date: {date}"
    )

    # Set default SLD directory if not provided
    if not sld_directory:
        # Try to find the SLD directory in the typical locations
        possible_paths = [
            "/SLDs/seasonal",
            "/projects/maps/builds/geoserver/SLDs/seasonal",
            os.path.join(os.getcwd(), "projects/maps/builds/geoserver/SLDs/seasonal"),
        ]

        sld_directory = None
        for path in possible_paths:
            if os.path.exists(path):
                sld_directory = path
                break

        if not sld_directory:
            sld_directory = "/SLDs/seasonal"  # Use default as fallback

    log.info(f"Using SLD directory: {sld_directory}")

    # Verify SLD directory exists and list contents
    if os.path.exists(sld_directory):
        sld_files = [f for f in os.listdir(sld_directory) if f.endswith(".sld")]
        log.info(f"Found {len(sld_files)} SLD files in {sld_directory}: {sld_files}")
    else:
        log.warning(f"SLD directory does not exist: {sld_directory}")

    # Process seasonal TIFF files with temporal dimension
    cache_layers = process_seasonal_tiff_files(
        base_path, sld_directory, geoserver_url, username, password, date
    )
    schedule_cache_refresh_chord(
        [
            {
                "layer_name": layer.name,
                "geoserver_url": geoserver_url,
                "username": username,
                "password": password,
                "workspace": WORKSPACE,
                "store_name": layer.store_name,
                "zoom_start": (cache_config or {}).get("zoom_start"),
                "zoom_stop": (cache_config or {}).get("zoom_stop"),
            }
            for layer in cache_layers
        ],
        ready_file=os.path.join(base_path, f"{date}.GEOSERVER.READY"),
        ready_contents=(
            f"Seasonal Data: {date}\nProcessed: {datetime.now().isoformat()}\n"
        ),
    )
