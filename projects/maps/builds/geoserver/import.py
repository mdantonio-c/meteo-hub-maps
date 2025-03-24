import os
import requests

# GeoServer configuration
GEOSERVER_URL = "http://localhost:8081/geoserver"
USERNAME = "admin"
PASSWORD = "D3vMode!"
WORKSPACE = "meteohub"
COVERAGESTORE_PREFIX = "tiff_store"

def create_workspace():
    """Create a workspace if it doesn't exist."""
    url = f"{GEOSERVER_URL}/rest/workspaces"
    headers = {"Content-Type": "application/json"}
    data = {"workspace": {"name": WORKSPACE}}

    response = requests.post(url, json=data, auth=(USERNAME, PASSWORD))
    if response.status_code == 201:
        print(f"Workspace '{WORKSPACE}' created successfully.")
    elif response.status_code == 409:
        print(f"Workspace '{WORKSPACE}' already exists.")
    else:
        print(f"Failed to create workspace: {response.text}")

def upload_geotiff(file_path, store_name):
    """Upload a GeoTIFF file to GeoServer."""
    url = f"{GEOSERVER_URL}/rest/workspaces/{WORKSPACE}/coveragestores/{store_name}/file.geotiff"
    headers = {"Content-Type": "image/tiff"}

    with open(file_path, "rb") as file:
        response = requests.put(url, data=file, auth=(USERNAME, PASSWORD))

    if response.status_code in [201, 202]:
        print(f"Uploaded {file_path} as {store_name}.")
    else:
        print(f"Failed to upload {file_path}: {response.text}")

import re

def sanitize_layer_name(layer_name):
    """Sanitize the layer name to only contain valid characters (alphanumeric and underscores)."""
    return re.sub(r'[^a-zA-Z0-9_]', '_', layer_name)

def publish_layer(store_name, layer_name):
    """Publish a GeoTIFF layer and print full response for debugging."""
    sanitized_layer_name = layer_name.strip()  # Ensure no extra spaces
    url = f"{GEOSERVER_URL}/rest/workspaces/{WORKSPACE}/coveragestores/{store_name}/coverages"
    headers = {"Content-Type": "application/json"}
    data = {
        "coverage": {
            "name": sanitized_layer_name,
            "nativeName": sanitized_layer_name,
            "srs": "EPSG:4326"
        }
    }

    response = requests.post(url, json=data, auth=(USERNAME, PASSWORD))
    
    print(f"Publishing Layer: {sanitized_layer_name}")
    print(f"Response Code: {response.status_code}")
    print(f"Response Text: {response.text}")

    if response.status_code == 201:
        print(f"Published layer {sanitized_layer_name}.")
    elif response.status_code == 409:
        print(f"Layer {sanitized_layer_name} already exists.")
    else:
        print(f"Failed to publish {sanitized_layer_name}: {response.text}")


def process_tiff_files(base_path):
    """Iterate over TIFF files and upload them to GeoServer."""
    create_workspace()

    for root, _, files in os.walk(base_path):
        for file in files:
            if file.endswith(".tif"):
                file_path = os.path.join(root, file)
                store_name = f"{COVERAGESTORE_PREFIX}_{file.replace('.tif', '')}"
                layer_name = file.replace(".tif", "")

                upload_geotiff(file_path, store_name)
                publish_layer(store_name, layer_name)

# Run the script
base_directory = "/home/dcrisant/Documents/MISTRAL/meteo-hub-maps/data/maps"  # Adjust this path as needed
process_tiff_files(base_directory)
