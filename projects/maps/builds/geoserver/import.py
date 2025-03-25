import os
import requests
import re

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

def sanitize_layer_name(layer_name):
    """Sanitize the layer name to only contain valid characters (alphanumeric and underscores)."""
    return re.sub(r'[^a-zA-Z0-9_]', '_', layer_name)

# def create_sld(layer_name):
#     """Generate an SLD string for the layer."""
#     sld = f"""
# <StyledLayerDescriptor version="1.0.0"
#     xsi:schemaLocation="http://www.opengis.net/sld http://schemas.opengis.net/sld/1.0.0/StyledLayerDescriptor.xsd"
#     xmlns="http://www.opengis.net/sld"
#     xmlns:ogc="http://www.opengis.net/ogc"
#     xmlns:xlink="http://www.w3.org/1999/xlink"
#     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
#     <NamedLayer>
#         <Name>Temperature Color Map</Name>
#         <UserStyle>
#             <Title>Temperature Color Map</Title>
#             <FeatureTypeStyle>
#                 <Rule>
#                     <RasterSymbolizer>
#                         <ColorMap type="ramp">
#                             <ColorMapEntry color="#64007F" quantity="-30"/>
#                             <ColorMapEntry color="#78048D" quantity="-28"/>
#                             <ColorMapEntry color="#870898" quantity="-26"/>
#                             <ColorMapEntry color="#B414B9" quantity="-24"/>
#                             <ColorMapEntry color="#D41DD1" quantity="-22"/>
#                             <ColorMapEntry color="#F627EB" quantity="-20"/>
#                             <ColorMapEntry color="#57007F" quantity="-18"/>
#                             <ColorMapEntry color="#3E007F" quantity="-16"/>
#                             <ColorMapEntry color="#00287F" quantity="-14"/>
#                             <ColorMapEntry color="#003C7F" quantity="-12"/>
#                             <ColorMapEntry color="#00467F" quantity="-10"/>
#                             <ColorMapEntry color="#00528F" quantity="-8"/>
#                             <ColorMapEntry color="#0062AF" quantity="-6"/>
#                             <ColorMapEntry color="#0082EF" quantity="-4"/>
#                             <ColorMapEntry color="#259AFF" quantity="-2"/>
#                             <ColorMapEntry color="#5BB4FF" quantity="0"/>
#                             <ColorMapEntry color="#BBFFE2" quantity="2"/>
#                             <ColorMapEntry color="#9FEEC8" quantity="4"/>
#                             <ColorMapEntry color="#87D3AB" quantity="6"/>
#                             <ColorMapEntry color="#62AF88" quantity="8"/>
#                             <ColorMapEntry color="#07A127" quantity="10"/>
#                             <ColorMapEntry color="#21BB0E" quantity="12"/>
#                             <ColorMapEntry color="#52CA0B" quantity="14"/>
#                             <ColorMapEntry color="#9CE106" quantity="16"/>
#                             <ColorMapEntry color="#CEF003" quantity="18"/>
#                             <ColorMapEntry color="#F3FB01" quantity="20"/>
#                             <ColorMapEntry color="#F4D90B" quantity="22"/>
#                             <ColorMapEntry color="#F4BD0B" quantity="24"/>
#                             <ColorMapEntry color="#F4880B" quantity="26"/>
#                             <ColorMapEntry color="#F46D0B" quantity="28"/>
#                             <ColorMapEntry color="#E83709" quantity="30"/>
#                             <ColorMapEntry color="#C41A0A" quantity="32"/>
#                             <ColorMapEntry color="#AF0F14" quantity="34"/>
#                             <ColorMapEntry color="#7C0000" quantity="36"/>
#                             <ColorMapEntry color="#640000" quantity="38"/>
#                             <ColorMapEntry color="#B46464" quantity="40"/>
#                             <ColorMapEntry color="#F0A0A0" quantity="42"/>
#                             <ColorMapEntry color="#FFB4B4" quantity="44"/>
#                             <ColorMapEntry color="#FFDCDC" quantity="46"/>
#                         </ColorMap>
#                     </RasterSymbolizer>
#                 </Rule>
#             </FeatureTypeStyle>
#         </UserStyle>
#     </NamedLayer>
# </StyledLayerDescriptor>


#     """
#     return sld

import time

def upload_sld(sld, layer_name):
    """Upload the SLD to GeoServer."""
    style_name = f"{WORKSPACE}:{layer_name}"
    url = f"{GEOSERVER_URL}/rest/styles"
    headers = {"Content-Type": "application/vnd.ogc.sld+xml"}

    response = requests.post(url, auth=(USERNAME, PASSWORD), headers=headers, data=sld)

    print(f"Response Code: {response.status_code}")
    print(f"Response Text: {response.text}")

    if response.status_code == 201:
        print(f"SLD for layer {layer_name} uploaded successfully.")
    else:
        print(f"Failed to upload SLD for {layer_name}: {response.text}")

    return style_name

def associate_sld_with_layer(layer_name, style_name):
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

def publish_layer(store_name, file_path, layer_name, sld=None):
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
        associate_sld_with_layer(store_name, sld)
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
            upload_geotiff(file_path, store_name)
            print(f"Re-uploaded {file_path} as {store_name}.")
            response = requests.post(url, json=data, headers=headers, auth=(USERNAME, PASSWORD))
    
            print(f"Publishing Layer: {sanitized_layer_name}")
            print(f"Response Code: {response.status_code}")
            print(f"Response Text: {response.text}")
            if response.status_code == 201:
                print(f"Published layer {sanitized_layer_name}.")
                if sld is not None:
                    associate_sld_with_layer(sanitized_layer_name, sld)
                # Create and upload SLD, then associate it with the layer
        else:
            print(f"Failed to delete store {store_name}: {delete_response.text}")
        print(f"Failed to publish {sanitized_layer_name}: {response.text}")

# def delete_store(STORE_NAME):
#     delete_url = f"{GEOSERVER_URL}/rest/workspaces/{WORKSPACE}/coveragestores/{STORE_NAME}?recurse=true"
#     res = requests.delete(delete_url, auth=(USERNAME, PASSWORD))
#     print(f"Response Code: {res.status_code}")
#     print(f"Response Text: {res.text}")
    
# def create_store(STORE_NAME):
#     create_url = f"{GEOSERVER_URL}/rest/workspaces/{WORKSPACE}/coveragestores"
#     headers = {"Content-Type": "application/json"}
#     data = {
#         "coverageStore": {
#             "name": STORE_NAME,
#             "type": "GeoTIFF",
#             "enabled": True,
#             # "url": "file:///your-path-to-geotiff.tif"
#         }
#     }

#     res = requests.post(create_url, json=data, auth=(USERNAME, PASSWORD), headers=headers)
#     print(f"Response Code: {res.status_code}")
#     print(f"Response Text: {res.text}")
    
    
def process_tiff_files(base_path):
    """Iterate over TIFF files and upload them to GeoServer."""
    create_workspace()
    
    # delete_store(DEFAULT_STORE_NAME)
    # create_store(DEFAULT_STORE_NAME)
    
    # Read SLD files from the specified directory
    sld_files = {}
    for root, _, files in os.walk(sld_directory):
        for file in files:
            if file.endswith(".sld"):
                sld_path = os.path.join(root, file)
                with open(sld_path, "r") as sld_file:
                    sld_content = sld_file.read()
                    sld_name = file.replace(".sld", "")
                    sld_files[sld_name] = sld_content
    for sld_name, sld_content in sld_files.items():
        upload_sld(sld_content, sld_name)
    # sld = create_sld("Temperature Color Map")
    # upload_sld(sld, "Temperature Color Map")
    # print(sld)
    for root, _, files in os.walk(base_path):
        for file in files:
            if file.endswith(".tif"):
                file_path = os.path.join(root, file)
                store_name = f"{COVERAGESTORE_PREFIX}_{file.replace('.tif', '')}"
                layer_name = file.replace(".tif", "")

                upload_geotiff(file_path, store_name)
                for sld_name, sld_layers in sld_dir_mapping.items():
                    if any(layer in file_path for layer in sld_layers):
                        # sld = sld_files[sld_name]
                        print(sld_name)
                        publish_layer(store_name, file_path, layer_name, sld_name)
                        break

# Run the script
base_directory = "/home/dcrisant/Documents/MISTRAL/meteo-hub-maps/data/maps"  # Adjust this path as needed
sld_directory = "/home/dcrisant/Documents/MISTRAL/meteo-hub-maps/projects/maps/builds/geoserver/SLDs"  # Adjust this path as needed
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
    "sf_6_12_24": ["snow6-snow", "snow12-snow"],
    "t2m": ["t2m-t2m"],
    "tcc": ["cloud-tcc"],
    "ws10m": ["wind-10u", "wind-10v"],
}
DEFAULT_STORE_NAME = "tiff_store"
process_tiff_files(base_directory)
