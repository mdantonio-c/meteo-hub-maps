from restapi.connectors.celery import CeleryExt
from restapi.utilities.logs import log
from restapi.env import Env
from typing import Optional, List, Dict, Any
import os
import shutil
import requests
from datetime import datetime
from maps.tasks.geoserver_utils import (
    create_ready_file_generic,
    create_workspace_generic,
    update_slds_from_local_folders,
    upload_geotiff_generic,
    publish_layer_generic,
    associate_sld_with_layer_generic,
    check_style_exists
)

# Configuration
GEOSERVER_URL = "http://geoserver.dockerized.io:8080/geoserver"
USERNAME = Env.get("GEOSERVER_ADMIN_USER", None)
PASSWORD = Env.get("GEOSERVER_ADMIN_PASSWORD", None)
GRANULE_RETENTION_HOURS = int(Env.get("RADAR_RETENTION_HOURS", 72))
WORKSPACE = "meteohub"
RADAR_BASE_DIRECTORY = "/radar"
COPIES_BASE_DIRECTORY = "/geoserver_data/copies"

# HTTP Status Codes
HTTP_OK = 200
HTTP_CREATED = 201
HTTP_ACCEPTED = 202
HTTP_NO_CONTENT = 204

# Mapping for SLDs
RADAR_SLD_MAPPING = {
    "vmi": "radar-vmi", 
    "sri": "radar-sri",
    "hail": "radar-hail",
    "srt": "radar-srt" 
}

@CeleryExt.task(idempotent=True)
def update_geoserver_radar_layers(
    self,
    variable: str,
    filenames,  # Can be str or List[str]
    dates,  # Can be string, datetime, or List of either
    geoserver_url: str = GEOSERVER_URL,
    username: str = USERNAME,
    password: str = PASSWORD,
    sld_directory: Optional[str] = None,
) -> None:
    """Update GeoServer with radar layers incrementally.
    
    Args:
        variable: Radar variable (sri, srt, etc.)
        filenames: Single filename or list of filenames to process
        dates: Single date or list of dates (can be string YYYYMMDDHHMM or datetime)
        geoserver_url: GeoServer base URL
        username: GeoServer admin username
        password: GeoServer admin password
        sld_directory: Optional path to SLD directory
    """
    # Normalize inputs to lists for batch processing
    if isinstance(filenames, str):
        filenames = [filenames]
    if not isinstance(dates, list):
        dates = [dates]
    
    # Convert dates to datetime objects
    date_dts = []
    for date in dates:
        if isinstance(date, str):
            try:
                date_dts.append(datetime.strptime(date, "%Y%m%d%H%M"))
            except ValueError:
                log.error(f"Invalid date format: {date}")
                return
        else:
            date_dts.append(date)
    
    if len(filenames) != len(date_dts):
        log.error(f"Mismatch between filenames ({len(filenames)}) and dates ({len(date_dts)})")
        return
    
    log.info(f"Updating GeoServer radar layer for {variable} with {len(filenames)} file(s)")

    # Set default SLD directory if not provided
    if not sld_directory:
        possible_paths = [
            "/SLDs/radar",
            "/projects/maps/builds/geoserver/SLDs/radar",
            os.path.join(os.getcwd(), "projects/maps/builds/geoserver/SLDs/radar")
        ]
        for path in possible_paths:
            if os.path.exists(path):
                sld_directory = path
                break
        if not sld_directory:
            log.warning("SLD directory not found, skipping SLD update")

    # Update SLDs (only once per batch)
    if os.path.exists(sld_directory):
        update_slds_from_local_folders(sld_directory, geoserver_url, username, password)
    
    # Process all files in the batch
    all_success = True
    for filename, date_dt in zip(filenames, date_dts):
        log.info(f"Processing file: {filename}, date: {date_dt}")
        success = process_radar_file(variable, filename, date_dt, geoserver_url, username, password)
        if not success:
            log.warning(f"Failed to process {filename}")
            all_success = False
    
    layer_name = f"radar-{variable}"
    store_name = f"mosaic_{layer_name}"
    copies_target_dir = os.path.join(COPIES_BASE_DIRECTORY, layer_name)
    # Batch-level cleanup after all files are processed
    if all_success and len(filenames) > 0:
        
        # Get all .tif files to determine time range
        all_tif_files = [f for f in os.listdir(copies_target_dir) if f.endswith('.tif')]
        
        if all_tif_files:
            # Parse timestamps from filenames
            file_dates = []
            for tif_file in all_tif_files:
                try:
                    day = tif_file[0:2]
                    month = tif_file[3:5]
                    year = tif_file[6:10]
                    hour = tif_file[11:13]
                    minute = tif_file[14:16]
                    file_dt = datetime(int(year), int(month), int(day), int(hour), int(minute))
                    if file_dt <= max(date_dts):
                        file_dates.append(file_dt)
                except (ValueError, IndexError) as e:
                    log.warning(f"Could not parse date from filename {tif_file}: {e}")
            
            if file_dates:
                min_date = min(file_dates)
                max_date = max(file_dates)
                time_range_hours = (max_date - min_date).total_seconds() / 3600
                
                log.info(f"Current time range in GeoServer: {time_range_hours:.1f} hours ({min_date} to {max_date})")
                
                # Only remove oldest granules/files if we're exceeding the 72-hour window
                if time_range_hours > GRANULE_RETENTION_HOURS:
                    log.info(f"Time range exceeds {GRANULE_RETENTION_HOURS} hours, cleaning up old data")
                    
                    # Remove old files (older than 72 hours from latest date)
                    remove_old_tif_files(copies_target_dir, GRANULE_RETENTION_HOURS, max_date)
                    # force_update_geoserver_radar_layers_index(copies_target_dir, layer_name, store_name, geoserver_url, username, password, variable)
                    
                    # Remove oldest granule to maintain rolling window
                    # log.info(f"Removing oldest granule from {store_name}")
                    # remove_oldest_granule(geoserver_url, WORKSPACE, store_name, layer_name, username, password)
                else:
                    log.info(f"Time range ({time_range_hours:.1f}h) within {GRANULE_RETENTION_HOURS}-hour window, skipping cleanup")
    force_update_geoserver_radar_layers_index(copies_target_dir, layer_name, store_name, geoserver_url, username, password, variable)
    
    
    # Create single .GEOSERVER.READY file with date range if all files processed successfully
    if all_success:
        var_path = os.path.join(RADAR_BASE_DIRECTORY, variable)
        layer_name = f"radar-{variable}"
        copies_target_dir = os.path.join(COPIES_BASE_DIRECTORY, layer_name)
        
        # Determine the full time range of files available in GeoServer
        # by scanning all .tif files in the copies directory
        all_tif_files = [f for f in os.listdir(copies_target_dir) if f.endswith('.tif')]
        
        if all_tif_files:
            # Parse timestamps from filenames (format: DD-MM-YYYY-HH-MM.tif)
            file_dates = []
            for tif_file in all_tif_files:
                try:
                    # Extract date parts from filename
                    day = tif_file[0:2]
                    month = tif_file[3:5]
                    year = tif_file[6:10]
                    hour = tif_file[11:13]
                    minute = tif_file[14:16]
                    file_dt = datetime(int(year), int(month), int(day), int(hour), int(minute))
                    file_dates.append(file_dt)
                except (ValueError, IndexError) as e:
                    log.warning(f"Could not parse date from filename {tif_file}: {e}")
            
            if file_dates:
                # Use the full range of available files in GeoServer
                overall_min_date = min(file_dates)
                overall_max_date = max(file_dates)
                
                date_range = f"{overall_min_date.strftime('%Y%m%d%H%M')}-{overall_max_date.strftime('%Y%m%d%H%M')}"
                # Delete all existing .GEOSERVER.READY files before creating new one
                existing_ready_files = [f for f in os.listdir(var_path) if f.endswith('.GEOSERVER.READY') and not f.startswith(date_range)]
                
                # Create date range filename representing the full 72-hour window
                geoserver_ready_path = os.path.join(var_path, f"{date_range}.GEOSERVER.READY")
                try:
                    with open(geoserver_ready_path, "w") as f:
                        f.write(f"Processed by GeoServer at {datetime.now().isoformat()}\n")
                        f.write(f"Files in batch: {len(filenames)}\n")
                        f.write(f"Total files in GeoServer: {len(file_dates)}\n")
                        f.write(f"Time range: {overall_min_date.isoformat()} to {overall_max_date.isoformat()}\n")
                        f.write(f"Coverage: {(overall_max_date - overall_min_date).total_seconds() / 3600:.1f} hours\n")
                    log.info(f"Created {geoserver_ready_path}")
                    log.info(f"GeoServer time range: {overall_min_date} to {overall_max_date} ({len(file_dates)} files)")
                    
                    # Delete all .CELERY.CHECKED files now that processing is complete
                    existing_checked_files = [f for f in os.listdir(var_path) if f.endswith('.CELERY.CHECKED')]
                    for checked_file in existing_checked_files:
                        try:
                            os.remove(os.path.join(var_path, checked_file))
                            log.info(f"Deleted CELERY.CHECKED file: {checked_file}")
                        except Exception as e:
                            log.warning(f"Failed to delete CELERY.CHECKED file {checked_file}: {e}")
                            
                    for old_file in existing_ready_files:
                        old_path = os.path.join(var_path, old_file)
                        try:
                            os.remove(old_path)
                            log.info(f"Deleted old GEOSERVER.READY file: {old_file}")
                        except Exception as e:
                            log.warning(f"Failed to delete old GEOSERVER.READY file {old_file}: {e}")
                except Exception as e:
                    log.error(f"Failed to create GEOSERVER.READY file: {e}")
            else:
                log.warning(f"No valid dates found in .tif files for {variable}")
        else:
            log.warning(f"No .tif files found in {copies_target_dir} after processing")

def force_update_geoserver_radar_layers_index(copies_target_dir, layer_name, store_name, geoserver_url, username, password, variable) -> bool:
    """Force update GeoServer radar layers."""
    # Remove index files to force reinitialization
    log.info(f"Removing index files from {copies_target_dir}")
    index_extensions = ['.shp', '.shx', '.dbf', '.prj', '.qix', '.fix', '.db', '.properties']
    removed_files = []
    for ext in index_extensions:
        for file_path in [f for f in os.listdir(copies_target_dir) if f.endswith(ext)]:
            full_path = os.path.join(copies_target_dir, file_path)
            try:
                os.remove(full_path)
                removed_files.append(file_path)
            except Exception as e:
                log.warning(f"Failed to remove index file {full_path}: {e}")
    
    if removed_files:
        log.info(f"Removed {len(removed_files)} index files: {', '.join(removed_files[:5])}...")

    
    # Recreate temporal config
    create_radar_temporal_config(copies_target_dir, layer_name)
    
    # Reinitialize the mosaic by uploading the directory
    log.info(f"Reinitializing mosaic {store_name} with all files")
    if upload_geotiff_generic(geoserver_url, copies_target_dir, store_name, username, password):
        log.info(f"Successfully reinitialized mosaic {store_name}")
        # Reapply time dimension and SLD
        enable_radar_time_dimension(geoserver_url, store_name, layer_name, username, password)
        
        sld_name = RADAR_SLD_MAPPING.get(variable)
        if sld_name:
            associate_sld_with_layer_generic(geoserver_url, layer_name, sld_name, username, password)
        
        return True
    else:
        log.error(f"Failed to reinitialize mosaic {store_name}")
        return False


def process_radar_file(variable, filename, date, geoserver_url, username, password):
    """Process a single radar file and update GeoServer."""
    create_workspace_generic(geoserver_url, username, password)

    layer_name = f"radar-{variable}"
    store_name = f"mosaic_{layer_name}"
    copies_target_dir = os.path.join(COPIES_BASE_DIRECTORY, layer_name)
    
    os.makedirs(copies_target_dir, exist_ok=True)
    
    # Check if this is initial setup or incremental update
    indexer_path = os.path.join(copies_target_dir, "indexer.properties")
    existing_tif_files = [f for f in os.listdir(copies_target_dir) if f.endswith('.tif')] if os.path.exists(copies_target_dir) else []
    
    # Initial setup: indexer.properties doesn't exist AND no .tif files in copies directory
    is_initial_setup = not os.path.exists(indexer_path) and len(existing_tif_files) == 0
    
    if is_initial_setup:
        # Initial setup: copy ALL files from the source directory
        log.info(f"Initializing mosaic store for {layer_name} - copying all files")
        
        source_dir = os.path.join(RADAR_BASE_DIRECTORY, variable, "files")
        if not os.path.exists(source_dir):
            log.error(f"Source directory not found: {source_dir}")
            return False
        
        # Copy all .tif files
        # files_copied = 0
        # for file in os.listdir(source_dir):
        #     if file.endswith('.tif'):
        source_file = os.path.join(source_dir, filename)
        target_file = os.path.join(copies_target_dir, filename)
        shutil.copy2(source_file, target_file)
                # files_copied += 1
        
        # log.info(f"Copied {files_copied} files to {copies_target_dir}")
        
        # Create temporal config
        create_radar_temporal_config(copies_target_dir, layer_name)
        
        # Initial upload to create the store
        if upload_geotiff_generic(geoserver_url, copies_target_dir, store_name, username, password):
             if publish_layer_generic(geoserver_url, store_name, layer_name, username, password, coverage_name=layer_name):
                enable_radar_time_dimension(geoserver_url, store_name, layer_name, username, password)
                log.info(f"Successfully created layer {layer_name}")
             else:
                 log.warning(f"Layer {layer_name} might already exist or failed to publish")
             
             # Always try to assign SLD, even if layer already exists
             sld_name = RADAR_SLD_MAPPING.get(variable)
             if sld_name:
                 log.info(f"Attempting to assign SLD '{sld_name}' to layer '{layer_name}'")
                 # Always try to assign - the associate function will handle if it doesn't exist
                 associate_sld_with_layer_generic(geoserver_url, layer_name, sld_name, username, password)
                 log.info(f"SLD assignment attempted for '{sld_name}' to layer '{layer_name}'")
             return True
        else:
            log.error(f"Failed to upload mosaic {store_name}")
            return False
    else:
        # Incremental update: copy new file, remove index files, and reinitialize
        source_file = os.path.join(RADAR_BASE_DIRECTORY, variable, "files", filename)
        
        log.info(f"Processing incremental update for {filename}")
        log.info(f"Source file path: {source_file}")
        
        if not os.path.exists(source_file):
            log.error(f"Source file not found: {source_file}")
            return False
        
        target_file = os.path.join(copies_target_dir, filename)
        log.info(f"Target file path: {target_file}")
        
        # Copy the new file
        try:
            if os.path.exists(target_file):
                log.info(f"File {filename} already exists in {copies_target_dir}. Skipping copy.")
                return True
            shutil.copy2(source_file, target_file)
            if os.path.exists(target_file):
                log.info(f"Successfully copied {filename} to {copies_target_dir}. Size: {os.path.getsize(target_file)} bytes")
            else:
                log.error(f"File copy failed: Target file {target_file} does not exist after copy operation")
                return False
        except Exception as e:
            log.error(f"Exception during file copy: {e}")
            return False
        
        return True
        # return force_update_geoserver_radar_layers_index(copies_target_dir, layer_name, store_name, geoserver_url, username, password, variable)



def remove_old_tif_files(directory: str, hours: int = 72, reference_date: Optional[datetime] = None):
    """Remove TIF files older than the specified number of hours from a directory."""
    from datetime import timedelta
    
    if reference_date is None:
        reference_date = datetime.now()
        
    cutoff_time = reference_date - timedelta(hours=hours)
    removed_count = 0
    
    tif_names = [
        f for f in os.listdir(directory) if f.endswith('.tif')
    ]

    for tif_name in tif_names:
        log.info(f"Processing file: {tif_name}, cutoff time: {cutoff_time}, {datetime.strptime(tif_name[0:16], '%d-%m-%Y-%H-%M')} {datetime.strptime(tif_name[0:16], '%d-%m-%Y-%H-%M') >= cutoff_time}")    
        if datetime.strptime(tif_name[0:16], "%d-%m-%Y-%H-%M") >= cutoff_time:
            continue
        file_path = os.path.join(directory, tif_name)
        try:
            os.remove(file_path)
            removed_count += 1
            log.info(f"Removed old file: {tif_name}")
        except Exception as e:
            log.warning(f"Failed to process file {tif_name}: {e}")
    
    if removed_count > 0:
        log.info(f"Removed {removed_count} TIF files older than {hours} hours")


def validate_granule_file(file_path: str) -> bool:

    """
    Validate that a file exists and is accessible before adding to mosaic.
    
    Args:
        file_path: Absolute path to the file to validate
        
    Returns:
        True if file is valid and accessible, False otherwise
    """
    if not os.path.exists(file_path):
        log.error(f"File does not exist: {file_path}")
        return False
    
    if not os.access(file_path, os.R_OK):
        log.error(f"File is not readable: {file_path}")
        return False
    
    if not file_path.endswith('.tif'):
        log.warning(f"File does not have .tif extension: {file_path}")
        return False
    
    return True


def add_granule_to_mosaic(
    geoserver_url: str,
    workspace: str,
    store_name: str,
    file_path: str,
    username: str,
    password: str
) -> bool:
    """
    Add a new granule to an existing ImageMosaic using the external.imagemosaic endpoint.
    
    This function uses the GeoServer REST API to harvest a single file into an existing
    ImageMosaic store and update the mosaic index. The file must be accessible from the
    GeoServer container's file system.
    
    Reference: https://docs.geoserver.org/2.26.x/en/user/rest/imagemosaic.html#updating-an-image-mosaic-contents
    
    Args:
        geoserver_url: Base URL of the GeoServer instance (e.g., http://geoserver:8080/geoserver)
        workspace: GeoServer workspace name
        store_name: Name of the ImageMosaic coverage store
        file_path: Absolute path to the GeoTIFF file on the host system
        username: GeoServer admin username
        password: GeoServer admin password
        
    Returns:
        True if granule was successfully added, False otherwise
    """
    # Validate file exists before attempting to add
    if not validate_granule_file(file_path):
        log.error(f"Granule validation failed for {file_path}")
        return False
    
    # Construct the file URL for GeoServer
    # The path on the host is /geoserver_data/copies/...
    # The path in the container is /opt/geoserver_data/copies/...
    # GeoServer needs the absolute path from inside the container
    container_path = file_path.replace("/geoserver_data/", "/opt/geoserver_data/")
    file_url = f"file://{container_path}"
    
    log.info(
        f"Adding granule to mosaic. "
        f"Store: {workspace}:{store_name}, "
        f"File: {os.path.basename(file_path)}, "
        f"URL: {file_url}"
    )
    
    # Use external.imagemosaic endpoint to add the granule
    # POST /rest/workspaces/{workspace}/coveragestores/{store}/external.imagemosaic
    url = f"{geoserver_url}/rest/workspaces/{workspace}/coveragestores/{store_name}/external.imagemosaic"
    
    headers = {"Content-type": "text/plain"}
    
    try:
        response = requests.post(
            url,
            data=file_url,
            headers=headers,
            auth=(username, password),
            timeout=30
        )
        
        if response.status_code in [HTTP_OK, HTTP_CREATED, HTTP_ACCEPTED]:
            log.info(
                f"Successfully added granule to {store_name}. "
                f"File: {os.path.basename(file_path)}, "
                f"Status: {response.status_code}"
            )
            return True
        else:
            log.error(f"Failed to add granule {file_url} to {store_name}: {response.status_code} - {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        log.error(f"Request exception while adding granule to {store_name}. File: {file_url}, Error: {str(e)}")
        return False


def remove_oldest_granule(geoserver_url, workspace, store_name, layer_name, username, password):
    """Remove the oldest granule from the mosaic."""
    # First, we need to find the oldest granule.
    # We can query the granules index.
    # GET /geoserver/rest/workspaces/<ws>/coveragestores/<mosaic>/coverages/<mosaic>/index/granules.json
    
    index_url = f"{geoserver_url}/rest/workspaces/{workspace}/coveragestores/{store_name}/coverages/{layer_name}/index/granules.json"
    response = requests.get(index_url, auth=(username, password))
    log.info(f"Response: {response.status_code}, {response.text}")
    if response.status_code != 200:
        log.error(f"Failed to retrieve granules list for {store_name}: {response.status_code}")
        return

    try:
        granules_data = response.json()
        # Structure depends on GeoServer version, usually features list
        features = granules_data.get('features', [])
        
        if not features:
            log.info(f"No granules found in {store_name}")
            return
            
        # Sort by time. Assuming 'time' attribute exists in properties.
        # Or sort by ID if time is not easily available, but time is better.
        # Properties usually contain the time attribute if configured.
        # If not, we might need to rely on filename or ID.
        
        # Let's try to find the time attribute
        # Example feature: {'type': 'Feature', 'id': 'radar-sri.1', 'geometry': ..., 'properties': {'location': '...', 'time': '...'}}
        
        features.sort(key=lambda x: x.get('properties', {}).get('time', ''))
        
        if len(features) > 0:
            oldest_granule = features[0]
            # location is usually the filename or relative path
            location = oldest_granule.get('properties', {}).get('location')
            
            if location:
                # DELETE /geoserver/rest/workspaces/myws/coveragestores/mosaic/coverages/mosaic/index/granules?filter=location='oldfile_2025_11_20.tif'
                delete_url = f"{geoserver_url}/rest/workspaces/{workspace}/coveragestores/{store_name}/coverages/{layer_name}/index/granules"
                params = {'filter': f"location='{location}'"}
                
                del_response = requests.delete(delete_url, params=params, auth=(username, password))
                log.info(f"Deleted oldest granule: {location}, response: {del_response.status_code}")
                if del_response.status_code in [200, 202, 204]:
                    log.info(f"Successfully removed oldest granule: {location}")
                    
                    # Force GeoServer to recalculate the coverage metadata to update the time dimension
                    recalc_url = f"{geoserver_url}/rest/workspaces/{workspace}/coveragestores/{store_name}/coverages/{layer_name}.xml"
                    recalc_params = {'recalculate': 'nativebbox,latlonbbox'}
                    
                    recalc_response = requests.put(recalc_url, params=recalc_params, auth=(username, password))
                    
                    if recalc_response.status_code in [200, 201]:
                        log.info(f"Successfully recalculated time dimension for {layer_name}")
                    else:
                        log.warning(f"Failed to recalculate coverage metadata: {recalc_response.status_code} - {recalc_response.text}")
                    
                    # Also remove the file from disk to save space
                    # location might be relative.
                    full_path = os.path.join(COPIES_BASE_DIRECTORY, layer_name, os.path.basename(location))
                    if os.path.exists(full_path):
                        try:
                            os.remove(full_path)
                            log.info(f"Removed file from disk: {full_path}")
                        except Exception as e:
                            log.warning(f"Failed to remove file from disk {full_path}: {e}")
                else:
                    log.error(f"Failed to remove granule {location}: {del_response.status_code} - {del_response.text}")
            else:
                log.warning("Oldest granule has no location property")
                
    except Exception as e:
        log.error(f"Error processing granules list: {e}")


def remove_files_older_than_retention(
    copies_target_dir: str,
    retention_hours: int = GRANULE_RETENTION_HOURS,
    reference_date: Optional[datetime] = None
    ) -> int:
    """
    Remove all granules and files older than the specified retention period from the mosaic.
    
    This function queries the mosaic index, identifies granules older than the cutoff time,
    removes them from GeoServer, and optionally deletes the corresponding files from disk.
    
    Args:
        copies_target_dir: Directory where granule files are stored
        retention_hours: Number of hours to retain granules (default: 72)
        reference_date: Reference date for retention calculation (default: now)
        
    Returns:
        Number of granules successfully removed
    """
    from datetime import timedelta, timezone
    
    # Get all granules using the new helper function
    granules = list_mosaic_granules()
    
    if granules is None:
        log.error("Failed to retrieve granules list, aborting cleanup")
        return 0
    
    if not granules:
        log.info(f"No granules found in {store_name}, nothing to clean up")
        return 0
    
    removed_count = 0
    fail

    # Determine the cutoff time for retention
    if reference_date is None:
        # Find the latest granule time to set the reference for retention
        latest_granule_time = None
        for feature in granules:
            props = feature.get("properties", {})
            time_str = props.get("time")
            if time_str:
                try:
                    if time_str.endswith('Z'):
                        current_granule_time = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                    else:
                        current_granule_time = datetime.fromisoformat(time_str)
                        if current_granule_time.tzinfo is None:
                            current_granule_time = current_granule_time.replace(tzinfo=timezone.utc)
                    
                    if latest_granule_time is None or current_granule_time > latest_granule_time:
                        latest_granule_time = current_granule_time
                except ValueError:
                    log.warning(f"Could not parse time string '{time_str}' for granule {feature.get('id')}")
        
        if latest_granule_time:
            log.info(f"Latest granule time found: {latest_granule_time}")
            cutoff_time = latest_granule_time - timedelta(hours=retention_hours)
        else:
            log.warning("No valid granule times found, using current time as reference for retention.")
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=retention_hours)
    else:
        cutoff_time = reference_date - timedelta(hours=retention_hours)

    log.info(f"Retention cutoff time: {cutoff_time} (retaining {retention_hours} hours)")
    ed_count = 0
    
    for feature in granules:
        props = feature.get("properties", {})
        time_str = props.get("time")
        location = props.get("location")
        granule_id = feature.get("id")
        
        if not time_str or not location:
            log.warning(
                f"Granule {granule_id} missing time or location property, skipping. "
                f"Time: {time_str}, Location: {location}"
            )
            continue
        
        try:
            # Parse the time from the granule with timezone awareness
            # Format might be like "2025-11-25T14:45:00.000Z" or "2025-11-25T14:45:00Z"
            if time_str.endswith('Z'):
                granule_time = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            else:
                granule_time = datetime.fromisoformat(time_str)
                # If no timezone info, assume UTC
                if granule_time.tzinfo is None:
                    granule_time = granule_time.replace(tzinfo=timezone.utc)
            
            if granule_time < cutoff_time:
                # Remove this granule from GeoServer
                del_url = f"{geoserver_url}/rest/workspaces/{workspace}/coveragestores/{store_name}/coverages/{layer_name}/index/granules/{granule_id}.json"
                
                try:
                    del_response = requests.delete(
                        del_url,
                        auth=(username, password),
                        timeout=30
                    )
                    
                    if del_response.status_code in [HTTP_OK, HTTP_ACCEPTED, HTTP_NO_CONTENT]:
                        log.info(
                            f"Removed granule from GeoServer: {location} "
                            f"(time: {time_str}, age: {(datetime.now(timezone.utc) - granule_time).total_seconds() / 3600:.1f}h)"
                        )
                        removed_count += 1
                        
                        # Remove file from disk
                        full_path = os.path.join(copies_target_dir, os.path.basename(location))
                        if os.path.exists(full_path):
                            try:
                                os.remove(full_path)
                                log.info(f"Removed file from disk: {full_path}")
                            except Exception as e:
                                log.warning(f"Failed to remove file from disk {full_path}: {e}")
                        else:
                            log.debug(f"File already removed or not found: {full_path}")
                    else:
                        log.error(
                            f"Failed to remove granule {granule_id}. "
                            f"Status: {del_response.status_code}, "
                            f"Response: {del_response.text}"
                        )
                        failed_count += 1
                        
                except requests.exceptions.RequestException as e:
                    log.error(f"Request exception while removing granule {granule_id}: {str(e)}")
                    failed_count += 1
                    
        except (ValueError, TypeError) as e:
            log.error(f"Error parsing time for granule {location}: {time_str}, Error: {e}")
            failed_count += 1
    
    log.info(
        f"Cleanup complete for {store_name}. "
        f"Removed: {removed_count}, Failed: {failed_count}, "
        f"Total processed: {len(granules)}"
    )
    return removed_count


# Backward compatibility alias
def remove_files_older_than_72_hours(copies_target_dir: str) -> int:
    """
    Remove all granules and files older than 72 hours from the mosaic.
    
    This is a backward compatibility wrapper for remove_files_older_than_retention.
    
    Returns:
        Number of granules successfully removed
    """
    return remove_files_older_than_retention(
        copies_target_dir,
        retention_hours=72
    )




def create_radar_temporal_config(target_dir: str, layer_name: str) -> None:
    """Create temporal mosaic configuration."""
    indexer_content = f"""PropertyCollectors=TimestampFileNameExtractorSPI[timeregex](time)
TimeAttribute=time
Schema=*the_geom:Polygon,location:String,time:java.util.Date
"""
    with open(os.path.join(target_dir, "indexer.properties"), 'w') as f:
        f.write(indexer_content)

    # Regex to extract time from filename
    # Format: DD-MM-YYYY-HH-MM.tif (e.g., 25-11-2025-02-05.tif)
    # Using a simpler pattern that captures the whole date string
    # The format string tells GeoServer how to parse it
    timeregex_content = "regex=([0-9]{2}-[0-9]{2}-[0-9]{4}-[0-9]{2}-[0-9]{2}),format=dd-MM-yyyy-HH-mm\n"
    
    with open(os.path.join(target_dir, "timeregex.properties"), 'w') as f:
        f.write(timeregex_content)


def enable_radar_time_dimension(geoserver_url: str, store_name: str, layer_name: str, username: str, password: str) -> bool:
    """Enable time dimension."""
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
                        <strategy>MAXIMUM</strategy>
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
    return True
