from restapi.connectors.celery import CeleryExt
from restapi.utilities.logs import log
from typing import Optional
import os
import requests
import re
from datetime import datetime
from .geoserver_utils import (
    create_ready_file_generic,
    create_workspace_generic,
    upload_sld_generic,
    process_sld_files,
    upload_geotiff_generic,
    publish_layer_generic,
    associate_sld_with_layer_generic
)

sld_dir_mapping = {
    "hcc": ["cloud_hml-hcc"],
    "lcc": ["cloud_hml-lcc"],
    "mcc": ["cloud_hml-mcc"],
    "tcc": ["cloud-tcc"],
    "prp_1_3": ["prec1-tp", "prec3-tp"],
    "prp_6_12_24": ["prec6-tp", "prec12-tp", "prec24-tp"],
    "prs": ["pressure-pmsl"],
    "rh": ["humidity-r"],
    "sf_1_3": ["snow1-snow", "snow3-snow"],
    "sf_6_12_24": ["snow6-snow", "snow12-snow", "snow24-snow"],
    "t2m": ["t2m-t2m"],
    "ws10m": ["wind-10u", "wind-10v", "wind-vmax_10m"],
    "temp_anomaly": ["seasonal_ano_max_TM", "seasonal_ano_min_Tm"],
    "precip_anomaly": ["seasonal_ano_P"],
    "precip_sum": ["seasonal_sum_P"],
}

COVERAGESTORE_PREFIX = "tiff_store"
DEFAULT_STORE_NAME = "tiff_store"
WORKSPACE = "meteohub"
WINDY_BASE_DIRECTORY: str = "/windy"

@CeleryExt.task(idempotent=True)
def update_geoserver_layers(
    self,
    GEOSERVER_URL: str,
    USERNAME: str,
    PASSWORD: str,
    run: str,
    date: str = datetime.now().strftime("%Y%m%d"),
    sld_directory: Optional[str] = None,
) -> None:
    log.info("Updating geoserver layers")
    
    # Clean up old windy stores first
    from .geoserver_utils import cleanup_old_windy_stores
    cleanup_old_windy_stores(GEOSERVER_URL, USERNAME, PASSWORD, date)
    
    # Update geoserver layers
    process_tiff_files(WINDY_BASE_DIRECTORY, sld_directory, GEOSERVER_URL, USERNAME, PASSWORD, run)
    create_ready_file(WINDY_BASE_DIRECTORY, run, date)

def create_ready_file(base_path, run: str, date: str) -> None:
    """Create a ready file to indicate that the process is complete."""
    data_path = os.path.join(base_path, f"Windy-{run}-ICON_2I_all2km.web/Italia")
    identifier = f"{date}{run}"
    create_ready_file_generic(data_path, identifier, "windy")


def create_workspace(GEOSERVER_URL, USERNAME, PASSWORD):
    """Create a workspace if it doesn't exist."""
    return create_workspace_generic(GEOSERVER_URL, USERNAME, PASSWORD)

def upload_geotiff(GEOSERVER_URL, file_path, store_name, USERNAME, PASSWORD):
    """Upload a GeoTIFF file to GeoServer."""
    return upload_geotiff_generic(GEOSERVER_URL, file_path, store_name, USERNAME, PASSWORD)

def sanitize_layer_name(layer_name):
    """Sanitize the layer name to only contain valid characters (alphanumeric and underscores)."""
    return re.sub(r'[^a-zA-Z0-9_]', '_', layer_name)


def upload_sld(GEOSERVER_URL, sld, layer_name, USERNAME, PASSWORD):
    """Upload the SLD to GeoServer."""
    return upload_sld_generic(GEOSERVER_URL, sld, layer_name, USERNAME, PASSWORD)

def associate_sld_with_layer(GEOSERVER_URL, layer_name, style_name, USERNAME, PASSWORD):
    """Associate the SLD with the layer."""
    return associate_sld_with_layer_generic(GEOSERVER_URL, layer_name, style_name, USERNAME, PASSWORD)

def publish_layer(GEOSERVER_URL, store_name, file_path, layer_name, USERNAME, PASSWORD, sld=None):
    """Publish a GeoTIFF layer with clean names."""
    # Use the generic function with clean layer name (remove tiff_store_ prefix from final layer name)
    clean_layer_name = layer_name
    
    # Publish using generic function
    success = publish_layer_generic(GEOSERVER_URL, store_name, clean_layer_name, USERNAME, PASSWORD, coverage_name=clean_layer_name)
    
    # Associate SLD if provided
    if success and sld is not None:
        associate_sld_with_layer(GEOSERVER_URL, clean_layer_name, sld, USERNAME, PASSWORD)
    
    return success

def process_tiff_files(base_path, sld_directory, GEOSERVER_URL, USERNAME, PASSWORD, run):
    """Iterate over TIFF files and upload them to GeoServer."""
    create_workspace(GEOSERVER_URL, USERNAME, PASSWORD)
    data_path = os.path.join(base_path, f"Windy-{run}-ICON_2I_all2km.web/Italia")
    
    # Process SLD files using generic function
    sld_files = process_sld_files(sld_directory)
    for sld_name, sld_content in sld_files.items():
        upload_sld(GEOSERVER_URL, sld_content, sld_name, USERNAME, PASSWORD)
    for root, _, files in os.walk(data_path):
        for file in files:
            if file.endswith(".tif"):
                file_path = os.path.join(root, file)
                parent_dir = os.path.dirname(file_path)
                dirs = parent_dir.split("/")
                store_name = f"{COVERAGESTORE_PREFIX}_{dirs[-1]}_{file.replace('.tif', '')}"
                layer_name = file.replace(".tif", "")

                upload_geotiff(GEOSERVER_URL, file_path, store_name, USERNAME, PASSWORD)
                for sld_name, sld_layers in sld_dir_mapping.items():
                    if any(layer in file_path for layer in sld_layers):
                        # sld = sld_files[sld_name]
                        publish_layer(GEOSERVER_URL, store_name, file_path, layer_name, USERNAME, PASSWORD, sld_name)
                        break


# === SEASONAL DATA FUNCTIONS ===
def process_seasonal_data(seasonal_path: str, geoserver_url: str, username: str, password: str, date_identifier: str, sld_directory: str = "/geoserver_data/SLDs") -> None:
    """Process seasonal data and upload to GeoServer."""
    log.info(f"Processing seasonal data from {seasonal_path}")
    
    # Create workspace
    if not create_workspace_generic(geoserver_url, username, password):
        log.error("Failed to create workspace for seasonal data")
        return
    
    # Upload SLD files first
    log.info("Uploading SLD files for seasonal data")
    sld_files = process_sld_files(sld_directory)
    for sld_name, sld_content in sld_files.items():
        upload_sld_generic(geoserver_url, sld_content, sld_name, username, password)
    
    # Clean up old seasonal stores first
    from .geoserver_utils import cleanup_old_seasonal_stores
    cleanup_old_seasonal_stores(geoserver_url, username, password, date_identifier)
    
    # Process each subdirectory in seasonal data
    seasonal_subdirs = ['ano_max_TM', 'ano_min_Tm', 'ano_P', 'mean_TM', 'mean_Tm', 'sum_P']
    
    for subdir in seasonal_subdirs:
        subdir_path = os.path.join(seasonal_path, subdir)
        if os.path.exists(subdir_path):
            log.info(f"Processing seasonal subdirectory: {subdir}")
            process_seasonal_subdir(subdir_path, subdir, geoserver_url, username, password)
        else:
            log.warning(f"Seasonal subdirectory not found: {subdir_path}")


def find_seasonal_sld(layer_name: str) -> Optional[str]:
    """Find the appropriate SLD for a seasonal layer based on its name."""
    for sld_name, sld_layers in sld_dir_mapping.items():
        for pattern in sld_layers:
            if pattern in layer_name:
                log.info(f"Found SLD '{sld_name}' for layer '{layer_name}' (pattern: '{pattern}')")
                return sld_name
    log.info(f"No SLD found for seasonal layer: {layer_name}")
    return None


def process_seasonal_subdir(subdir_path: str, subdir_name: str, geoserver_url: str, username: str, password: str) -> None:
    """Process a single seasonal data subdirectory."""
    # Find TIFF files in the subdirectory
    tiff_files = []
    for root, _, files in os.walk(subdir_path):
        for file in files:
            if file.endswith(".tif") or file.endswith(".tiff"):
                tiff_files.append(os.path.join(root, file))
    
    if not tiff_files:
        log.warning(f"No TIFF files found in {subdir_path}")
        return
    
    log.info(f"Found {len(tiff_files)} TIFF files in {subdir_name}")
    
    # Process each TIFF file
    for tiff_file in tiff_files:
        file_name = os.path.splitext(os.path.basename(tiff_file))[0]
        # Keep store_name with prefix for internal GeoServer management
        store_name = f"{COVERAGESTORE_PREFIX}_seasonal_{subdir_name}_{file_name}"
        # Use clean layer name without "tiff_store_" prefix
        layer_name = f"seasonal_{subdir_name}_{file_name}"
        
        # Upload GeoTIFF using generic function
        if upload_geotiff_generic(geoserver_url, tiff_file, store_name, username, password):
            # Publish layer with clean name (coverage name will be the clean layer_name)
            if publish_layer_generic(geoserver_url, store_name, layer_name, username, password, coverage_name=layer_name):
                # Find and associate appropriate SLD
                sld_name = find_seasonal_sld(layer_name)
                if sld_name:
                    if associate_sld_with_layer_generic(geoserver_url, layer_name, sld_name, username, password):
                        log.info(f"Successfully associated SLD '{sld_name}' with layer '{layer_name}'")
                    else:
                        log.warning(f"Failed to associate SLD '{sld_name}' with layer '{layer_name}'")
                
                log.info(f"Successfully processed seasonal data: {layer_name}")
            else:
                log.warning(f"Failed to publish layer for: {layer_name}")


@CeleryExt.task(idempotent=True)
def update_geoserver_seasonal_data(
    self,
    geoserver_url: str,
    date_identifier: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
    seasonal_path: str = "/data/seasonal-aim",
) -> None:
    """
    Update GeoServer with seasonal data.
    """
    log.info(f"Starting seasonal data update for {date_identifier}")
    
    # Get credentials from environment if not provided
    if username is None:
        username = os.getenv("GEOSERVER_ADMIN_USER")
    if password is None:
        password = os.getenv("GEOSERVER_ADMIN_PASSWORD")
    
    if not username or not password:
        log.error("GeoServer credentials not provided")
        return
    
    try:
        # Process seasonal data with SLD directory
        sld_directory = "/SLDs/seasonal"  # Path inside container
        process_seasonal_data(seasonal_path, geoserver_url, username, password, date_identifier, sld_directory)
        
        # Create ready file
        create_ready_file_generic(seasonal_path, date_identifier, "seasonal")
        
        log.info(f"Seasonal data update completed for {date_identifier}")
        
    except Exception as e:
        log.error(f"Error updating seasonal data: {e}")
        raise