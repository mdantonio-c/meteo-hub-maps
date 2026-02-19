from restapi.env import Env
from restapi.connectors.celery import CeleryExt
from restapi.utilities.logs import log
from typing import Optional
import os
import requests
import re
from datetime import datetime
from maps.tasks.geoserver_utils import (
    create_ready_file_generic,
    create_celery_checked_ready_file_generic,
    create_workspace_generic,
    upload_sld_generic,
    process_sld_files,
    update_slds_from_local_folders,
    upload_geotiff_generic,
    publish_layer_generic,
    associate_sld_with_layer_generic,
    check_style_exists
)
from .upload_image_mosaic import enable_time_dimension

# Get GeoServer credentials for seasonal task
GEOSERVER_URL = "http://geoserver.dockerized.io:8080/geoserver"
USERNAME = Env.get("GEOSERVER_ADMIN_USER", None)
PASSWORD = Env.get("GEOSERVER_ADMIN_PASSWORD", None)


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
    "temp_anomaly": ["seasonal-ano-max-TM", "seasonal-ano-min-Tm"],
    "temperature": ["seasonal-mean-TM", "seasonal-mean-Tm"],
    "precip_anomaly": ["seasonal-ano-P"],
    "precip_sum": ["seasonal-sum-P"],
    "zerot": ["zerot-hzerocl"],
    "sf_tot": ["tot_snow-snow"],
    "prec_tot": ["tot_prec-tp"]
}

# Mapping of seasonal directories to their corresponding names in copies
seasonal_to_copies_mapping = {
    "ano_max_TM": "seasonal-ano-max-TM",
    "ano_min_Tm": "seasonal-ano-min-Tm", 
    "ano_P": "seasonal-ano-P",
    "mean_TM": "seasonal-mean-TM",
    "mean_Tm": "seasonal-mean-Tm",
    "sum_P": "seasonal-sum-P",
}

COVERAGESTORE_PREFIX = "tiff_store"
DEFAULT_STORE_NAME = "tiff_store"
WORKSPACE = "meteohub"
WINDY_BASE_DIRECTORY: str = "/windy"

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
    # Clean the file_path by removing 'geoserver_data/' prefix if present
    if file_path.startswith('/geoserver_data/'):
        file_path = file_path[len('/geoserver_data/'):]
    elif file_path.startswith('geoserver_data/'):
        file_path = file_path[len('geoserver_data/'):]
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
    
    # Update SLD files from local folders to GeoServer
    sld_update_success = update_slds_from_local_folders(sld_directory, GEOSERVER_URL, USERNAME, PASSWORD)
    if not sld_update_success:
        log.warning("Some SLD updates failed, but continuing with processing")
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

SEASONAL_BASE_DIRECTORY: str = "/seasonal-aim"

def create_seasonal_ready_file(base_path, date_identifier: str) -> None:
    """Create a ready file to indicate that the seasonal process is complete."""
    create_ready_file_generic(base_path, date_identifier, "seasonal")

def process_seasonal_tiff_files(base_path, sld_directory, geoserver_url, username, password, date_identifier):
    """Iterate over seasonal TIFF files and upload them to GeoServer with temporal dimension."""
    create_workspace(geoserver_url, username, password)
    
    # Clean up old seasonal stores first
    from maps.tasks.geoserver_utils import cleanup_old_seasonal_stores
    cleanup_old_seasonal_stores(geoserver_url, username, password, date_identifier)
    
    # Update SLD files from local folders to GeoServer BEFORE processing layers
    log.info(f"Updating seasonal SLD files from directory: {sld_directory}")
    sld_update_success = update_slds_from_local_folders(sld_directory, geoserver_url, username, password)
    if not sld_update_success:
        log.warning("Some SLD updates failed, but continuing with processing")
    else:
        log.info("Successfully updated all seasonal SLD files")
    
    # Process each seasonal subdirectory
    seasonal_subdirs = ['ano_max_TM', 'ano_min_Tm', 'ano_P', 'mean_TM', 'mean_Tm', 'sum_P']
    
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
            if file.endswith(('.tif', '.tiff')):
                source_file = os.path.join(subdir_path, file)
                target_file = os.path.join(copies_target, file)
                
                try:
                    shutil.copy2(source_file, target_file)
                    tiff_files_copied += 1
                    log.debug(f"Copied seasonal file: {file}")
                except Exception as e:
                    log.error(f"Failed to copy seasonal file {file}: {e}")
        
        if tiff_files_copied > 0:
            log.info(f"Copied {tiff_files_copied} seasonal TIFF files to {seasonal_copies_name}")
            
            # Create temporal mosaic configuration files
            create_seasonal_temporal_config(copies_target, seasonal_copies_name)
            
            # Create and publish temporal mosaic in GeoServer
            store_name = f"mosaic_{seasonal_copies_name}"
            layer_name = seasonal_copies_name
            
            # Upload as ImageMosaic (temporal) - use generic function directly to preserve path handling
            if upload_geotiff_generic(geoserver_url, copies_target, store_name, username, password):
                # Publish the temporal layer
                if publish_layer_generic(geoserver_url, store_name, layer_name, username, password, coverage_name=layer_name):
                    # Enable temporal dimension using custom function for seasonal data
                    enable_seasonal_time_dimension(geoserver_url, store_name, layer_name, username, password)
                    
                    # Find and associate appropriate SLD
                    sld_name = find_seasonal_sld_mapping(subdir)
                    if sld_name:
                        log.info(f"Found SLD mapping: '{subdir}' -> '{sld_name}' for layer '{layer_name}'")
                        
                        # Check if the SLD style exists in GeoServer
                        style_exists = check_style_exists(geoserver_url, sld_name, username, password)
                        if style_exists:
                            log.info(f"SLD style '{sld_name}' exists in GeoServer, proceeding with association")
                            sld_success = associate_sld_with_layer(geoserver_url, layer_name, sld_name, username, password)
                            if sld_success:
                                log.info(f"Successfully processed seasonal temporal layer: {layer_name} with SLD: {sld_name}")
                            else:
                                log.error(f"Failed to associate SLD '{sld_name}' with layer '{layer_name}'")
                        else:
                            log.error(f"SLD style '{sld_name}' does not exist in GeoServer - check SLD upload process")
                    else:
                        log.warning(f"No SLD mapping found for seasonal directory: {subdir}, layer: {layer_name}")
                else:
                    log.error(f"Failed to publish seasonal temporal layer: {layer_name}")
            else:
                log.error(f"Failed to upload seasonal temporal mosaic: {store_name}")
        else:
            log.warning(f"No TIFF files found in seasonal directory: {subdir_path}")
    
    log.info(f"Completed processing all seasonal subdirectories for date: {date_identifier}")

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
        with open(indexer_path, 'w') as f:
            f.write(indexer_content)
        log.info(f"Created temporal indexer.properties for {layer_name}")
    except Exception as e:
        log.error(f"Failed to create temporal indexer.properties for {layer_name}: {e}")
    
    # Create timeregex.properties for seasonal date extraction
    # Seasonal files typically have format: ano_P_20251028.tif (YYYYMMDD)
    timeregex_content = "regex=.*([0-9]{8}).*,format=yyyyMMdd\n"
    
    timeregex_path = os.path.join(target_dir, "timeregex.properties")
    try:
        with open(timeregex_path, 'w') as f:
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



def enable_seasonal_time_dimension(geoserver_url: str, store_name: str, layer_name: str, username: str, password: str) -> bool:
    """Enable temporal dimension for seasonal layers."""
    # The URL needs to use the store name for the coverage store and layer name for the coverage
    url = f"{geoserver_url}/rest/workspaces/{WORKSPACE}/coveragestores/{store_name}/coverages/{layer_name}"
    headers = {
        "Content-Type": "application/xml",
        "Accept": "application/xml"
    }
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

    response = requests.put(url, data=data, headers=headers, auth=(username, password))
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
        "mean_TM": "temperature",
        "mean_Tm": "temperature",
        "sum_P": "precip_sum"
    }
    
    sld_name = seasonal_sld_mapping.get(seasonal_dir)
    if sld_name:
        log.info(f"Found SLD '{sld_name}' for seasonal directory '{seasonal_dir}'")
        return sld_name
    
    log.warning(f"No SLD mapping found for seasonal directory: {seasonal_dir}")
    return None

@CeleryExt.task(idempotent=True)
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
    success = update_slds_from_local_folders(sld_base_directory, geoserver_url, username, password)
    
    if success:
        log.info("Successfully updated all SLD styles from local folders")
    else:
        log.warning("Some SLD updates failed - check logs for details")

@CeleryExt.task(idempotent=True)
def update_geoserver_seasonal_layers(
    self = None,
    date: str = datetime.now().strftime("%Y%m%d"),
    geoserver_url: str = GEOSERVER_URL,
    username: str = USERNAME,
    password: str = PASSWORD,
    sld_directory: Optional[str] = None,
) -> None:
    """Update GeoServer with seasonal layers following the same pattern as windy layers."""
    log.info(f"Updating GeoServer seasonal layers with temporal dimension for date: {date}")
    
    # Set default SLD directory if not provided
    if not sld_directory:
        # Try to find the SLD directory in the typical locations
        possible_paths = [
            "/SLDs/seasonal",
            "/projects/maps/builds/geoserver/SLDs/seasonal",
            os.path.join(os.getcwd(), "projects/maps/builds/geoserver/SLDs/seasonal")
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
        sld_files = [f for f in os.listdir(sld_directory) if f.endswith('.sld')]
        log.info(f"Found {len(sld_files)} SLD files in {sld_directory}: {sld_files}")
    else:
        log.warning(f"SLD directory does not exist: {sld_directory}")
    
    # Process seasonal TIFF files with temporal dimension
    process_seasonal_tiff_files(SEASONAL_BASE_DIRECTORY, sld_directory, geoserver_url, username, password, date)
    
    # Create final ready file
    create_seasonal_ready_file(SEASONAL_BASE_DIRECTORY, date)