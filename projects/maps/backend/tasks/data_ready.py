from restapi.connectors.celery import CeleryExt
from restapi.utilities.logs import log
from typing import Optional
import os
import requests
import re
from datetime import datetime

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
}

COVERAGESTORE_PREFIX = "tiff_store"
DEFAULT_STORE_NAME = "tiff_store"
WORKSPACE = "meteohub"
BASE_DIRECTORY: str = "/meteo"

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
    # Update geoserver layers
    process_tiff_files(BASE_DIRECTORY, sld_directory, GEOSERVER_URL, USERNAME, PASSWORD, run)
    create_ready_file(BASE_DIRECTORY, run, date)

def create_ready_file(base_path, run: str, date: str) -> None:
    """Create a ready file to indicate that the process is complete."""
    data_path = os.path.join(base_path, f"Windy-{run}-ICON_2I_all2km.web/Italia")
    ready_file_path = os.path.join(data_path, f"{date}{run}.GEOSERVER.READY")
    with open(ready_file_path, "w") as f:
        f.write(f"Run: {run}\nDate: {date}\n")
    log.info(f"Ready file created at {ready_file_path}")


def create_workspace(GEOSERVER_URL, USERNAME, PASSWORD):
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

def upload_geotiff(GEOSERVER_URL, file_path, store_name, USERNAME, PASSWORD):
    """Upload a GeoTIFF file to GeoServer."""
    url = f"{GEOSERVER_URL}/rest/workspaces/{WORKSPACE}/coveragestores/{store_name}/file.geotiff"
    headers = {"Content-Type": "image/tiff"}

    try:
        with open(file_path, "rb") as file:
            response = requests.put(url, data=file, auth=(USERNAME, PASSWORD))
    except Exception as e:
        log.error(f"An error occurred while uploading GeoTIFF: {e}")

    if response.status_code in [201, 202]:
        print(f"Uploaded {file_path} as {store_name}.")
    else:
        print(f"Failed to upload {file_path}: {response.text}")

def sanitize_layer_name(layer_name):
    """Sanitize the layer name to only contain valid characters (alphanumeric and underscores)."""
    return re.sub(r'[^a-zA-Z0-9_]', '_', layer_name)


def upload_sld(GEOSERVER_URL, sld, layer_name, USERNAME, PASSWORD):
    """Upload the SLD to GeoServer."""
    style_name = f"{WORKSPACE}:{layer_name}"
    url = f"{GEOSERVER_URL}/rest/styles"
    headers = {"Content-Type": "application/vnd.ogc.sld+xml"}
    params = {"name": layer_name}

    response = requests.post(url, auth=(USERNAME, PASSWORD), headers=headers, params=params, data=sld)

    print(f"Response Code: {response.status_code}")
    print(f"Response Text: {response.text}")

    if response.status_code == 201:
        print(f"SLD for layer {layer_name} uploaded successfully.")
    else:
        print(f"Failed to upload SLD for {layer_name}: {response.text}")

    return style_name

def associate_sld_with_layer(GEOSERVER_URL, layer_name, style_name, USERNAME, PASSWORD):
    """Associate the SLD with the layer."""
    layer_url = f"{GEOSERVER_URL}/rest/layers/{WORKSPACE}:{layer_name}"
    data = {
        "layer": {
            "defaultStyle": {"name": f"{style_name}"}
        }
    }
    headers = {"Content-Type": "application/json"}

    response = requests.put(layer_url, auth=(USERNAME, PASSWORD), headers=headers, json=data)

    if response.status_code == 200:
        print(f"SLD associated with layer {layer_name} successfully.")
    else:
        print(f"Failed to associate SLD '{style_name}' with layer {layer_name}: {response.text}")

def publish_layer(GEOSERVER_URL, store_name, file_path, layer_name, USERNAME, PASSWORD, sld=None):
    """Publish a GeoTIFF layer and print full response for debugging."""
    sanitized_layer_name = layer_name.strip()  # Ensure no extra spaces
    url = f"{GEOSERVER_URL}/rest/workspaces/{WORKSPACE}/coveragestores/{store_name}/coverages"
    headers = {"Content-Type": "application/json"}
    data = {
        "coverage": {
            "name": store_name,
            "nativeName": store_name,
            "title": sanitized_layer_name,
            "srs": "EPSG:4326"
        }
    }

    response = requests.post(url, json=data, headers=headers, auth=(USERNAME, PASSWORD))
    print(f"Publishing Layer: {sanitized_layer_name}")
    print(f"Response Code: {response.status_code}")
    print(f"Response Text: {response.text}")

    if response.status_code == 201:
        print(f"Published layer {sanitized_layer_name}.")
    if sld is not None:
        associate_sld_with_layer(GEOSERVER_URL, store_name, sld, USERNAME, PASSWORD)
        # Create and upload SLD, then associate it with the layer
    elif response.status_code == 409:
        print(f"Layer {sanitized_layer_name} already exists.")
    else:
        # # Delete the existing layer and coverage store
        delete_url = f"{GEOSERVER_URL}/rest/workspaces/{WORKSPACE}/coveragestores/{store_name}?recurse=true"
        delete_response = requests.delete(delete_url, auth=(USERNAME, PASSWORD))
        if delete_response.status_code == 200:
            print(f"Deleted existing store {store_name}.")
            # Re-upload the GeoTIFF
            upload_geotiff(GEOSERVER_URL, file_path, store_name, USERNAME, PASSWORD)
            print(f"Re-uploaded {file_path} as {store_name}.")
            response = requests.post(url, json=data, headers=headers, auth=(USERNAME, PASSWORD))
            print(f"Publishing Layer: {sanitized_layer_name}")
            print(f"Response Code: {response.status_code}")
            print(f"Response Text: {response.text}")
            if response.status_code == 201:
                print(f"Published layer {sanitized_layer_name}.")
                if sld is not None:
                    associate_sld_with_layer(GEOSERVER_URL, sanitized_layer_name, sld, USERNAME, PASSWORD)
                # Create and upload SLD, then associate it with the layer
        else:
            print(f"Failed to delete store {store_name}: {delete_response.text}")
        print(f"Failed to publish {sanitized_layer_name}: {response.text}")

def process_tiff_files(base_path, sld_directory, GEOSERVER_URL, USERNAME, PASSWORD, run):
    """Iterate over TIFF files and upload them to GeoServer."""
    create_workspace(GEOSERVER_URL, USERNAME, PASSWORD)
    data_path = os.path.join(base_path, f"Windy-{run}-ICON_2I_all2km.web/Italia")
    # Read SLD files from the specified directory
    sld_files = {}
    if sld_directory is not None:
        for root, _, files in os.walk(sld_directory):
            for file in files:
                if file.endswith(".sld"):
                    sld_path = os.path.join(root, file)
                    with open(sld_path, "r") as sld_file:
                        sld_content = sld_file.read()
                        sld_name = file.replace(".sld", "")
                        sld_files[sld_name] = sld_content
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