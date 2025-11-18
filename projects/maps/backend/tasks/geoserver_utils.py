"""
Common GeoServer utilities for data processing tasks.
"""
from restapi.utilities.logs import log
from typing import Optional
import os
import requests
from datetime import datetime

WORKSPACE = "meteohub"

def create_celery_checked_ready_file_generic(data_path: str, identifier: str, data_type: str = "windy") -> None:
    """Create a checked ready file to indicate that the process is complete and verified."""
    if data_type == "seasonal":
        ready_file_path = os.path.join(data_path, f"{identifier}.CELERY.CHECKED")
        with open(ready_file_path, "w") as f:
            f.write(f"Seasonal Data Checked: {identifier}\nProcessed: {datetime.now().isoformat()}\n")
    else:  # windy or other types
        ready_file_path = os.path.join(data_path, f"{identifier}.CELERY.CHECKED")
        with open(ready_file_path, "w") as f:
            f.write(f"Data Checked: {identifier}\nProcessed: {datetime.now().isoformat()}\n")
    log.info(f"Checked ready file created at {ready_file_path}")

def create_ready_file_generic(data_path: str, identifier: str, data_type: str = "windy") -> None:
    """Create a ready file to indicate that the process is complete."""
    if data_type == "seasonal":
        ready_file_path = os.path.join(data_path, f"{identifier}.GEOSERVER.READY")
        with open(ready_file_path, "w") as f:
            f.write(f"Seasonal Data: {identifier}\nProcessed: {datetime.now().isoformat()}\n")
    else:  # windy or other types
        ready_file_path = os.path.join(data_path, f"{identifier}.GEOSERVER.READY")
        with open(ready_file_path, "w") as f:
            f.write(f"Data: {identifier}\nProcessed: {datetime.now().isoformat()}\n")
    log.info(f"Ready file created at {ready_file_path}")


def create_workspace_generic(geoserver_url: str, username: str, password: str, workspace: str = WORKSPACE) -> bool:
    """Create a workspace if it doesn't exist."""
    url = f"{geoserver_url}/rest/workspaces"
    headers = {"Content-Type": "application/json"}
    data = {"workspace": {"name": workspace}}

    response = requests.post(url, json=data, auth=(username, password))
    if response.status_code == 201:
        log.info(f"Workspace '{workspace}' created successfully.")
        return True
    elif response.status_code == 409:
        log.info(f"Workspace '{workspace}' already exists.")
        return True
    else:
        log.error(f"Failed to create workspace: {response.text}")
        return False


def upload_sld_generic(geoserver_url: str, sld_content: str, layer_name: str, username: str, password: str) -> bool:
    """Upload the SLD to GeoServer. Returns True if successful, False otherwise."""
    
    # Skip upload for default GeoServer styles and invalid content
    if not sld_content or not sld_content.strip():
        log.warning(f"Skipping upload of empty SLD for layer {layer_name}")
        return False
    
    # Skip default GeoServer styles that might cause conflicts
    default_styles = ["default_line", "default_point", "default_polygon", "default_generic", 
                     "simpleRoads", "NamedPlaces", "Lakes", "popshade", "grass_poly", 
                     "default_line2", "pophatch"]
    if layer_name in default_styles:
        log.info(f"Skipping upload of default GeoServer style: {layer_name}")
        return True  # Return True since this is intentionally skipped
    
    url = f"{geoserver_url}/rest/styles"
    headers = {"Content-Type": "application/vnd.ogc.sld+xml"}
    params = {"name": layer_name}

    try:
        response = requests.post(url, auth=(username, password), headers=headers, params=params, data=sld_content.encode('utf-8'))
        
        if response.status_code == 201:
            log.info(f"SLD for layer {layer_name} created successfully.")
            return True
        elif response.status_code == 409 or (response.status_code >= 400 and "already exists" in response.text):
            log.info(f"SLD for layer {layer_name} already exists. Updating it.")
            # Update existing SLD
            update_url = f"{geoserver_url}/rest/styles/{layer_name}"
            response = requests.put(update_url, auth=(username, password), headers=headers, data=sld_content.encode('utf-8'))
            
            if response.status_code == 200:
                log.info(f"SLD for layer {layer_name} updated successfully.")
                return True
            else:
                log.error(f"Failed to update SLD for {layer_name}: {response.status_code} - {response.text}")
                return False
        else:
            log.error(f"Failed to upload SLD for {layer_name}: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        log.error(f"Exception during SLD upload for {layer_name}: {e}")
        return False


def process_sld_files(sld_directory: str) -> dict:
    """Read SLD files from the specified directory."""
    sld_files = {}
    if sld_directory and os.path.exists(sld_directory):
        for root, _, files in os.walk(sld_directory):
            for file in files:
                if file.endswith(".sld"):
                    sld_path = os.path.join(root, file)
                    try:
                        with open(sld_path, "r", encoding='utf-8') as sld_file:
                            sld_content = sld_file.read().strip()
                            sld_name = file.replace(".sld", "")
                            # Only include non-empty SLD files
                            if sld_content:
                                sld_files[sld_name] = sld_content
                                log.debug(f"Successfully read SLD file: {sld_name}")
                            else:
                                log.warning(f"SLD file is empty: {sld_path}")
                    except PermissionError as e:
                        log.warning(f"Permission denied reading SLD file {sld_path}: {e}")
                    except Exception as e:
                        log.error(f"Error reading SLD file {sld_path}: {e}")
    else:
        log.warning(f"SLD directory does not exist or is None: {sld_directory}")
    
    log.info(f"Successfully loaded {len(sld_files)} SLD files from {sld_directory}")
    return sld_files

def update_slds_from_local_folders(sld_base_directory: str, geoserver_url: str, username: str, password: str) -> bool:
    """
    Scan local SLD folders and update GeoServer with any changes.
    This looks for SLD files in local directories and uploads/updates them in GeoServer.
    """
    log.info(f"Scanning local SLD directories in: {sld_base_directory}")
    
    if not os.path.exists(sld_base_directory):
        log.warning(f"SLD base directory does not exist: {sld_base_directory}")
        return False
    
    updated_count = 0
    error_count = 0
    
    # Walk through all subdirectories looking for SLD files
    for root, dirs, files in os.walk(sld_base_directory):
        sld_files_in_dir = [f for f in files if f.endswith(".sld")]
        if sld_files_in_dir:
            log.info(f"Found {len(sld_files_in_dir)} SLD files in directory: {root}")
            
        for file in files:
            if file.endswith(".sld"):
                sld_path = os.path.join(root, file)
                sld_name = file.replace(".sld", "")
                
                # Get file modification time for change detection
                try:
                    file_stat = os.stat(sld_path)
                    file_mtime = file_stat.st_mtime
                    
                    log.info(f"Processing SLD file: {sld_name} from {sld_path}")
                    
                    # Read SLD content
                    with open(sld_path, "r", encoding='utf-8') as sld_file:
                        sld_content = sld_file.read().strip()
                        
                    if not sld_content:
                        log.warning(f"SLD file is empty, skipping: {sld_path}")
                        continue
                    
                    log.debug(f"SLD content length for {sld_name}: {len(sld_content)} characters")
                    
                    # Upload/update the SLD to GeoServer
                    success = upload_sld_generic(geoserver_url, sld_content, sld_name, username, password)
                    
                    if success:
                        updated_count += 1
                        log.info(f"Successfully updated SLD: {sld_name}")
                    else:
                        error_count += 1
                        log.error(f"Failed to update SLD: {sld_name}")
                        
                except PermissionError as e:
                    log.warning(f"Permission denied reading SLD file {sld_path}: {e}")
                    error_count += 1
                except Exception as e:
                    log.error(f"Error processing SLD file {sld_path}: {e}")
                    error_count += 1
    
    log.info(f"SLD update completed: {updated_count} updated, {error_count} errors")
    return error_count == 0


def check_coverage_store_exists(geoserver_url: str, store_name: str, username: str, password: str, workspace: str = WORKSPACE) -> bool:
    """Check if a coverage store already exists."""
    url = f"{geoserver_url}/rest/workspaces/{workspace}/coveragestores/{store_name}"
    response = requests.get(url, auth=(username, password))
    return response.status_code == 200


def delete_coverage_store(geoserver_url: str, store_name: str, username: str, password: str, workspace: str = WORKSPACE) -> bool:
    """Delete a coverage store and all its resources."""
    url = f"{geoserver_url}/rest/workspaces/{workspace}/coveragestores/{store_name}?recurse=true"
    response = requests.delete(url, auth=(username, password))
    if response.status_code in [200, 404]:  # 404 means already deleted
        log.info(f"Deleted coverage store {store_name}.")
        return True
    else:
        log.error(f"Failed to delete coverage store {store_name}: {response.text}")
        return False


def check_coverage_exists(geoserver_url: str, store_name: str, coverage_name: str, username: str, password: str, workspace: str = WORKSPACE) -> bool:
    """Check if a coverage already exists within a store."""
    url = f"{geoserver_url}/rest/workspaces/{workspace}/coveragestores/{store_name}/coverages/{coverage_name}"
    response = requests.get(url, auth=(username, password))
    return response.status_code == 200


def get_all_coverage_stores(geoserver_url: str, username: str, password: str, workspace: str = WORKSPACE) -> list:
    """Get all coverage stores in the workspace."""
    url = f"{geoserver_url}/rest/workspaces/{workspace}/coveragestores"
    response = requests.get(url, auth=(username, password), headers={"Accept": "application/json"})
    
    if response.status_code == 200:
        data = response.json()
        if 'coverageStores' in data and 'coverageStore' in data['coverageStores']:
            stores = data['coverageStores']['coverageStore']
            # Handle single store case (not a list)
            if isinstance(stores, dict):
                stores = [stores]
            return [store['name'] for store in stores]
    return []


def cleanup_old_windy_stores(geoserver_url: str, username: str, password: str, current_date: str, workspace: str = WORKSPACE) -> None:
    """Remove old windy coverage stores, keeping only current ones."""
    log.info("Starting cleanup of old windy stores")
    
    all_stores = get_all_coverage_stores(geoserver_url, username, password, workspace)
    old_stores_deleted = 0
    
    for store_name in all_stores:
        # Check if it's a windy store (tiff_store_ prefix but not seasonal)
        if store_name.startswith("tiff_store_") and not store_name.startswith("tiff_store_seasonal_"):
            # Try to extract date from store name if possible
            parts = store_name.split('_')
            if len(parts) >= 3:
                try:
                    # Look for date pattern in the store name
                    store_date = None
                    for part in parts:
                        if len(part) == 8 and part.isdigit():  # YYYYMMDD format
                            store_date = part
                            break
                    
                    # If we found a date and it's not the current date, delete it
                    if store_date and store_date != current_date.replace('-', ''):
                        if delete_coverage_store(geoserver_url, store_name, username, password, workspace):
                            old_stores_deleted += 1
                            log.info(f"Deleted old windy store: {store_name}")
                except (ValueError, IndexError):
                    log.warning(f"Could not parse date from store name: {store_name}")
    
    log.info(f"Cleanup completed. Deleted {old_stores_deleted} old windy stores.")


def cleanup_old_seasonal_stores(geoserver_url: str, username: str, password: str, current_date: str, workspace: str = WORKSPACE) -> None:
    """Remove old seasonal coverage stores, keeping only current ones."""
    log.info("Starting cleanup of old seasonal stores")
    
    all_stores = get_all_coverage_stores(geoserver_url, username, password, workspace)
    old_stores_deleted = 0
    
    for store_name in all_stores:
        # Check if it's a seasonal store
        if store_name.startswith("seasonal-"):
            # Extract date from store name if possible
            # Assuming format like: tiff_store_seasonal_mean_Tm_mean_Tm_2025_12
            parts = store_name.split('_')
            if len(parts) >= 6:
                try:
                    # Look for year pattern (4 digits)
                    year_month = None
                    for i, part in enumerate(parts):
                        if len(part) == 4 and part.isdigit():  # Found year
                            if i + 1 < len(parts) and parts[i + 1].isdigit():  # Next part is month
                                year_month = f"{part}_{parts[i + 1]:0>2}"  # Ensure 2-digit month
                                break
                    
                    # If we found a date and it's not the current date, delete it
                    if year_month and year_month != current_date.replace('-', '_'):
                        if delete_coverage_store(geoserver_url, store_name, username, password, workspace):
                            old_stores_deleted += 1
                            log.info(f"Deleted old seasonal store: {store_name}")
                except (ValueError, IndexError):
                    log.warning(f"Could not parse date from store name: {store_name}")
    
    log.info(f"Cleanup completed. Deleted {old_stores_deleted} old seasonal stores.")


def refresh_imagemosaic_store(geoserver_url: str, store_name: str, username: str, password: str, workspace: str = WORKSPACE) -> bool:
    """Refresh an existing ImageMosaic store to pick up new files."""
    log.info(f"Refreshing ImageMosaic store: {store_name}")
    
    # First, try to harvest new files
    harvest_url = f"{geoserver_url}/rest/workspaces/{workspace}/coveragestores/{store_name}/harvester"
    harvest_data = """<harvest>
        <path>.</path>
        <recursive>true</recursive>
        <purge>NONE</purge>
    </harvest>"""
    
    headers = {"Content-Type": "application/xml"}
    response = requests.post(harvest_url, data=harvest_data, headers=headers, auth=(username, password))
    
    if response.status_code == 202:
        log.info(f"Successfully initiated harvest for ImageMosaic store: {store_name}")
        return True
    elif response.status_code == 404:
        log.warning(f"Harvest endpoint not available for store: {store_name}")
        # Fallback to index reset
        return reset_imagemosaic_index(geoserver_url, store_name, username, password, workspace)
    else:
        log.warning(f"Harvest failed with status {response.status_code}: {response.text}")
        return reset_imagemosaic_index(geoserver_url, store_name, username, password, workspace)

def reset_imagemosaic_index(geoserver_url: str, store_name: str, username: str, password: str, workspace: str = WORKSPACE) -> bool:
    """Reset the ImageMosaic index to pick up new files."""
    log.info(f"Resetting ImageMosaic index for store: {store_name}")
    
    # Reset the index
    reset_url = f"{geoserver_url}/rest/workspaces/{workspace}/coveragestores/{store_name}/reset"
    response = requests.post(reset_url, auth=(username, password))
    
    if response.status_code in [200, 202]:
        log.info(f"Successfully reset ImageMosaic index for store: {store_name}")
        return True
    else:
        log.warning(f"Failed to reset ImageMosaic index for {store_name}: {response.status_code} - {response.text}")
        return False

def upload_geotiff_generic(geoserver_url: str, file_path: str, store_name: str, username: str, password: str, workspace: str = WORKSPACE) -> bool:
    """Upload a GeoTIFF file or directory (for mosaics) to GeoServer."""
    
    # Ensure the path exists and convert to absolute path if needed
    # Check both the given path and the absolute version with /geoserver_data prefix
    actual_path = file_path
    if not os.path.exists(file_path):
        # Try with absolute /geoserver_data prefix
        if not file_path.startswith('/'):
            alt_path = f"/{file_path}"
            if os.path.exists(alt_path):
                actual_path = alt_path
    
    # Check if actual_path is a directory (for mosaics) or a file
    if os.path.isdir(actual_path):
        # Handle ImageMosaic stores
        if check_coverage_store_exists(geoserver_url, store_name, username, password, workspace):
            # Store exists - try to refresh/update it instead of recreating
            log.info(f"ImageMosaic store {store_name} already exists. Attempting to refresh content.")
            
            # Try to refresh the mosaic content
            if refresh_imagemosaic_store(geoserver_url, store_name, username, password, workspace):
                log.info(f"Successfully refreshed ImageMosaic store: {store_name}")
                return True
            else:
                # If refresh fails, fall back to recreating the store
                log.warning(f"Failed to refresh ImageMosaic store {store_name}. Recreating it.")
                if not delete_coverage_store(geoserver_url, store_name, username, password, workspace):
                    return False
                return upload_mosaic_generic(geoserver_url, actual_path, store_name, username, password, workspace)
        else:
            # Store doesn't exist - create new mosaic
            return upload_mosaic_generic(geoserver_url, actual_path, store_name, username, password, workspace)
    else:
        # Handle single GeoTIFF files
        if check_coverage_store_exists(geoserver_url, store_name, username, password, workspace):
            log.info(f"Coverage store {store_name} already exists. Deleting it first.")
            if not delete_coverage_store(geoserver_url, store_name, username, password, workspace):
                return False
        
        # Upload as single GeoTIFF
        url = f"{geoserver_url}/rest/workspaces/{workspace}/coveragestores/{store_name}/file.geotiff"
        headers = {"Content-Type": "image/tiff"}

        try:
            with open(actual_path, "rb") as file:
                response = requests.put(url, data=file, auth=(username, password))
        except Exception as e:
            log.error(f"An error occurred while uploading GeoTIFF: {e}")
            return False

        if response.status_code in [201, 202]:
            log.info(f"Uploaded {actual_path} as {store_name}.")
            return True
        else:
            log.error(f"Failed to upload {actual_path}: {response.text}")
            return False


def upload_mosaic_generic(geoserver_url: str, mosaic_dir: str, store_name: str, username: str, password: str, workspace: str = WORKSPACE) -> bool:
    """Upload a mosaic directory to GeoServer."""
    log.info(f"Uploading mosaic from directory: {mosaic_dir}")
    
    # Convert absolute path to relative path for GeoServer data directory
    if mosaic_dir.startswith('/geoserver_data/'):
        relative_path = mosaic_dir[len('/geoserver_data/'):]
        geoserver_url_path = f"file:{relative_path}"
    elif mosaic_dir.startswith('geoserver_data/'):
        relative_path = mosaic_dir[len('geoserver_data/'):]
        geoserver_url_path = f"file:{relative_path}"
    else:
        # Fallback to absolute path if not in geoserver_data
        geoserver_url_path = f"file://{mosaic_dir}"
    
    log.info(f"Using GeoServer URL path: {geoserver_url_path}")
    
    # Create the coverage store for the mosaic
    url = f"{geoserver_url}/rest/workspaces/{workspace}/coveragestores"
    headers = {"Content-Type": "application/json"}
    data = {
        "coverageStore": {
            "name": store_name,
            "workspace": {
                "name": workspace
            },
            "type": "ImageMosaic",
            "url": geoserver_url_path,
            "enabled": True
        }
    }

    response = requests.post(url, json=data, headers=headers, auth=(username, password))
    
    if response.status_code in [201, 202]:
        log.info(f"Created mosaic coverage store {store_name}.")
        return True
    elif response.status_code == 409:
        log.info(f"Mosaic coverage store {store_name} already exists.")
        return True
    else:
        log.error(f"Failed to create mosaic coverage store {store_name}: {response.text}")
        return False


def publish_layer_generic(geoserver_url: str, store_name: str, layer_name: str, username: str, password: str, workspace: str = WORKSPACE, coverage_name: Optional[str] = None) -> bool:
    """Publish a GeoTIFF layer with custom coverage name."""
    sanitized_layer_name = layer_name.strip()
    coverage_name = coverage_name or layer_name  # Use layer_name as coverage name if not specified
    
    # For mosaic stores, check if GeoServer auto-created any coverages
    if store_name.startswith("mosaic_"):
        import time
        # Wait a moment for GeoServer to process the mosaic
        time.sleep(2)
        
        # List available coverages in the mosaic store
        list_url = f"{geoserver_url}/rest/workspaces/{workspace}/coveragestores/{store_name}/coverages"
        list_response = requests.get(list_url, auth=(username, password))
        
        if list_response.status_code == 200:
            import xml.etree.ElementTree as ET
            try:
                # Parse the XML response to get available coverages
                root = ET.fromstring(list_response.text)
                coverages = root.findall('.//coverage/name')
                if coverages:
                    # Use the first available coverage as the native name
                    native_coverage_name = coverages[0].text
                    if native_coverage_name:
                        log.info(f"Found auto-created coverage in mosaic: {native_coverage_name}")
                        
                        # Check if it already has the desired name
                        if native_coverage_name == coverage_name:
                            log.info(f"Coverage {coverage_name} already exists with correct name.")
                            return True
                        else:
                            # Update the coverage to use our desired name
                            return update_mosaic_coverage_name(geoserver_url, store_name, native_coverage_name, coverage_name, sanitized_layer_name, username, password, workspace)
                    else:
                        log.warning(f"Found coverage entry but name is empty in mosaic store {store_name}")
                else:
                    log.warning(f"No auto-created coverages found in mosaic store {store_name}")
            except Exception as e:
                log.warning(f"Failed to parse coverage list response: {e}")
        else:
            log.warning(f"Failed to list coverages from mosaic store {store_name}: {list_response.status_code} - {list_response.text}")
    
    # Check if coverage already exists (GeoTIFF upload often creates it automatically)
    if check_coverage_exists(geoserver_url, store_name, store_name, username, password, workspace):
        log.info(f"Coverage {store_name} already exists. Updating its name to {coverage_name}.")
        # Update the existing coverage to use the desired layer name
        return update_coverage_name(geoserver_url, store_name, coverage_name, sanitized_layer_name, username, password, workspace)
    
    url = f"{geoserver_url}/rest/workspaces/{workspace}/coveragestores/{store_name}/coverages"
    headers = {"Content-Type": "application/json"}
    data = {
        "coverage": {
            "name": coverage_name,
            "nativeName": coverage_name,  # For mosaics, use coverage_name as nativeName
            "title": sanitized_layer_name,
            "srs": "EPSG:4326"
        }
    }

    response = requests.post(url, json=data, headers=headers, auth=(username, password))
    log.info(f"Publishing Layer: {sanitized_layer_name} with coverage name: {coverage_name}")
    log.info(f"Response Code: {response.status_code}")

    if response.status_code == 201:
        log.info(f"Published layer {sanitized_layer_name}.")
        return True
    elif response.status_code == 409:
        log.info(f"Layer {sanitized_layer_name} already exists.")
        return True
    elif response.status_code == 500 and "already exists" in response.text:
        log.info(f"Coverage {store_name} was already created (likely during GeoTIFF upload).")
        return True
    else:
        log.error(f"Failed to publish {sanitized_layer_name}: {response.text}")
        return False


def update_coverage_name(geoserver_url: str, store_name: str, coverage_name: str, layer_title: str, username: str, password: str, workspace: str = WORKSPACE) -> bool:
    """Update an existing coverage to use a custom name."""
    # First, try to update the existing coverage (which is typically named same as store)
    url = f"{geoserver_url}/rest/workspaces/{workspace}/coveragestores/{store_name}/coverages/{store_name}"
    headers = {"Content-Type": "application/json"}
    data = {
        "coverage": {
            "name": coverage_name,
            "title": layer_title,
            "srs": "EPSG:4326"
        }
    }

    response = requests.put(url, json=data, headers=headers, auth=(username, password))
    
    if response.status_code == 200:
        log.info(f"Updated coverage name from {store_name} to {coverage_name}.")
        return True
    else:
        log.warning(f"Could not update coverage name: {response.text}")
        # If update fails, the coverage exists with the store name, which is still functional
        return True


def update_mosaic_coverage_name(geoserver_url: str, store_name: str, native_coverage_name: str, new_coverage_name: str, layer_title: str, username: str, password: str, workspace: str = WORKSPACE) -> bool:
    """Update an existing mosaic coverage to use a custom name."""
    # For mosaic stores, the URL should reference the actual native coverage name
    url = f"{geoserver_url}/rest/workspaces/{workspace}/coveragestores/{store_name}/coverages/{native_coverage_name}"
    headers = {"Content-Type": "application/json"}
    data = {
        "coverage": {
            "name": new_coverage_name,
            "title": layer_title,
            "srs": "EPSG:4326"
        }
    }

    response = requests.put(url, json=data, headers=headers, auth=(username, password))
    
    if response.status_code == 200:
        log.info(f"Updated mosaic coverage name from {native_coverage_name} to {new_coverage_name}.")
        return True
    else:
        log.warning(f"Could not update mosaic coverage name: {response.text}")
        # If update fails, the coverage still exists with the native name, which is functional
        log.info(f"Coverage {native_coverage_name} is available with its original name.")
        return True


def check_style_exists(geoserver_url: str, style_name: str, username: str, password: str, workspace: str = WORKSPACE) -> bool:
    """Check if a style exists in GeoServer."""
    url = f"{geoserver_url}/rest/styles/{style_name}"
    response = requests.get(url, auth=(username, password))
    
    if response.status_code == 200:
        log.debug(f"Style '{style_name}' exists in GeoServer")
        return True
    else:
        log.debug(f"Style '{style_name}' does not exist in GeoServer: {response.status_code}")
        return False


def associate_sld_with_layer_generic(geoserver_url: str, layer_name: str, style_name: str, username: str, password: str, workspace: str = WORKSPACE) -> bool:
    """Associate the SLD with the layer."""
    layer_url = f"{geoserver_url}/rest/layers/{workspace}:{layer_name}"
    data = {
        "layer": {
            "defaultStyle": {"name": f"{style_name}"}
        }
    }
    headers = {"Content-Type": "application/json"}

    response = requests.put(layer_url, auth=(username, password), headers=headers, json=data)

    if response.status_code == 200:
        log.info(f"SLD associated with layer {layer_name} successfully.")
        return True
    else:
        log.error(f"Failed to associate SLD '{style_name}' with layer {layer_name}: {response.text}")
        return False