"""
Common GeoServer utilities for data processing tasks.
"""
from restapi.utilities.logs import log
from typing import Optional
import os
import requests
from datetime import datetime

WORKSPACE = "meteohub"


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


def upload_sld_generic(geoserver_url: str, sld_content: str, layer_name: str, username: str, password: str) -> str:
    """Upload the SLD to GeoServer."""
    style_name = f"{WORKSPACE}:{layer_name}"
    url = f"{geoserver_url}/rest/styles"
    headers = {"Content-Type": "application/vnd.ogc.sld+xml"}
    params = {"name": layer_name}

    response = requests.post(url, auth=(username, password), headers=headers, params=params, data=sld_content)
    if response.status_code == 201:
        log.info(f"SLD for layer {layer_name} created successfully.")
    elif response.status_code >= 400 and "already exists" in response.text:
        log.info(f"SLD for layer {layer_name} already exists. Updating it.")
        # Update existing SLD
        url = f"{geoserver_url}/rest/styles/{layer_name}"
    
        response = requests.put(url, auth=(username, password), headers=headers, params=params, data=sld_content)

    log.info(f"SLD upload response - Code: {response.status_code} - auth: {username}/{password} - URL: {url}")
    
    if response.status_code == 201:
        log.info(f"SLD for layer {layer_name} uploaded successfully.")
    else:
        log.error(f"Failed to upload SLD for {layer_name}: {response.text}")

    return style_name


def process_sld_files(sld_directory: str) -> dict:
    """Read SLD files from the specified directory."""
    sld_files = {}
    if sld_directory and os.path.exists(sld_directory):
        for root, _, files in os.walk(sld_directory):
            for file in files:
                if file.endswith(".sld"):
                    sld_path = os.path.join(root, file)
                    try:
                        with open(sld_path, "r") as sld_file:
                            sld_content = sld_file.read()
                            sld_name = file.replace(".sld", "")
                            sld_files[sld_name] = sld_content
                    except Exception as e:
                        log.error(f"Error reading SLD file {sld_path}: {e}")
    return sld_files


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


def cleanup_old_seasonal_stores(geoserver_url: str, username: str, password: str, current_date: str, workspace: str = WORKSPACE) -> None:
    """Remove old seasonal coverage stores, keeping only current ones."""
    log.info("Starting cleanup of old seasonal stores")
    
    all_stores = get_all_coverage_stores(geoserver_url, username, password, workspace)
    old_stores_deleted = 0
    
    for store_name in all_stores:
        # Check if it's a seasonal store
        if store_name.startswith("tiff_store_seasonal_"):
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


def upload_geotiff_generic(geoserver_url: str, file_path: str, store_name: str, username: str, password: str, workspace: str = WORKSPACE) -> bool:
    """Upload a GeoTIFF file to GeoServer."""
    # Check if store already exists and delete it if it does
    if check_coverage_store_exists(geoserver_url, store_name, username, password, workspace):
        log.info(f"Coverage store {store_name} already exists. Deleting it first.")
        if not delete_coverage_store(geoserver_url, store_name, username, password, workspace):
            return False
    
    url = f"{geoserver_url}/rest/workspaces/{workspace}/coveragestores/{store_name}/file.geotiff"
    headers = {"Content-Type": "image/tiff"}

    try:
        with open(file_path, "rb") as file:
            response = requests.put(url, data=file, auth=(username, password))
    except Exception as e:
        log.error(f"An error occurred while uploading GeoTIFF: {e}")
        return False

    if response.status_code in [201, 202]:
        log.info(f"Uploaded {file_path} as {store_name}.")
        return True
    else:
        log.error(f"Failed to upload {file_path}: {response.text}")
        return False


def publish_layer_generic(geoserver_url: str, store_name: str, layer_name: str, username: str, password: str, workspace: str = WORKSPACE, coverage_name: str = None) -> bool:
    """Publish a GeoTIFF layer with custom coverage name."""
    sanitized_layer_name = layer_name.strip()
    coverage_name = coverage_name or layer_name  # Use layer_name as coverage name if not specified
    
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
            "nativeName": store_name,
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