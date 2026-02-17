from restapi.connectors.celery import CeleryExt
from restapi.utilities.logs import log
from restapi.env import Env
from typing import Optional
import os
import requests
import re
from datetime import datetime
from requests.auth import HTTPBasicAuth
from datetime import datetime, timedelta
import shutil
from maps.tasks.geoserver_utils import (
    create_ready_file_generic,
    create_workspace_generic,
    upload_sld_generic,
    process_sld_files
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
    "isobars": ["pressure-isob"],
    "zerot": ["zerot-hzerocl"]
}

# === CONFIGURATION ===
# GEOSERVER_URL = "http://localhost:8081/geoserver"
GEOSERVER_USERNAME = Env.get("GEOSERVER_ADMIN_USER", None)
GEOSERVER_PASSWORD = Env.get("GEOSERVER_ADMIN_PASSWORD", None)
GEOSERVER_URL = "http://geoserver.dockerized.io:8080/geoserver"
WORKSPACE = "meteohub"
RENAMED_FILES = "copies"
BASE_PATH = "/windy"
# TIFF_DIR = f"{BASE_PATH}/Windy-12-ICON_2I_all2km.web/Italia"  # Local path containing .tiff files
GEOSERVER_HOST_PATH = f"/geoserver_data/{RENAMED_FILES}"
GEOSERVER_DATA_DIR = f"geoserver_data/{RENAMED_FILES}/"  # Path where GeoServer can access TIFFs

@CeleryExt.task(idempotent=True)
def update_geoserver_image_mosaic(
    self,
    GEOSERVER_URL: str,
    run: str,
    date: str = datetime.now().strftime("%Y-%m-%d"),
    sld_directory: str = "/SLDs",
) -> None:
    # Ensure workspace exists before uploading
    create_workspace_generic(GEOSERVER_URL, GEOSERVER_USERNAME, GEOSERVER_PASSWORD, WORKSPACE)
    
    sld_directory = os.path.join(sld_directory, "windy")
    update_styles(sld_directory)
    TIFF_DIR = f"{BASE_PATH}/Windy-{run}-ICON_2I_all2km.web/Italia"
    date_edit = datetime.strptime(date, "%Y%m%d").strftime("%Y-%m-%d")
    for folder in os.listdir(TIFF_DIR):
        folder_path = os.path.join(TIFF_DIR, folder)
        if os.path.isdir(folder_path):
            flat_sld_dirs = [item for sublist in sld_dir_mapping.values() for item in sublist]
            if folder in flat_sld_dirs:
                print(f"📂 Processing folder: {folder}")
                process_and_rename_tiffs(date_edit, run, folder, TIFF_DIR)
            else:
                continue
            if ensure_tiff_files_exist(folder, TIFF_DIR):
                create_image_mosaic_store(folder, GEOSERVER_URL)
            publish_layer(folder, GEOSERVER_URL)
            bind_sld(folder, GEOSERVER_URL)
            enable_time_dimension(folder, GEOSERVER_URL)
    create_ready_file(TIFF_DIR, run, date)
    
def update_styles(sld_directory: Optional[str] = None) -> None:
    if sld_directory:
        if not os.path.exists(sld_directory):
            print(f"⚠️ SLD directory not found: {sld_directory}")
            return
        print(f"📂 Processing SLD directory: {sld_directory}")
        for folder in os.listdir(sld_directory):
            create_or_update_sld(folder, sld_directory)

def create_or_update_sld(folder: str, sld_directory: str) -> None:
    style_name = folder.rsplit('.')[0]
    sld_path = os.path.join(sld_directory, folder)
    if not os.path.exists(sld_path):
        print(f"❌ SLD path does not exist: {sld_path}")
        return

    # Check if SLD file exists and is a file (not directory)
    sld_file = sld_path
    if not os.path.isfile(sld_file):
        print(f"❌ SLD file does not exist or is not a file: {sld_file}")
        return

    with open(sld_file, 'r', encoding='utf-8') as f:
        sld_content = f.read()
        
    url = f"{GEOSERVER_URL}/rest/styles/{style_name}"
    headers = {
        "Content-Type": "application/vnd.ogc.sld+xml"
    }
    response = requests.put(url, headers=headers, data=sld_content, auth=(GEOSERVER_USERNAME, GEOSERVER_PASSWORD))
    if response.status_code in [200, 201]:
        print("Style updated successfully.")
    else:
        print(f"Failed to update style. Status code: {response.status_code}")
        print(response.text)
        upload_sld(
            geoserver_url=GEOSERVER_URL,
            sld_content=sld_content,
            layer_name=style_name,
            username=GEOSERVER_USERNAME,
            password=GEOSERVER_PASSWORD,
        )
        
def upload_sld(geoserver_url, sld_content, layer_name, username, password):
    """Unified function to upload the SLD to GeoServer."""
    return upload_sld_generic(geoserver_url, sld_content, layer_name, username, password)
    
def create_ready_file(base_path, run: str, date: str) -> None:
    """Create a ready file to indicate that the process is complete."""
    identifier = f"{date}{run}"
    create_ready_file_generic(base_path, identifier, "windy")    

def write_mosaic_config_files(output_dir):
    indexer_content = """PropertyCollectors=TimestampFileNameExtractorSPI[timeregex](time)
    TimeAttribute=time
    Schema=*the_geom:Polygon,location:String,time:java.util.Date
    """

    timeregex_content = "regex=.*([0-9]{10}).*,format=yyyyMMddHH"

    indexer_path = os.path.join(output_dir, "indexer.properties")
    timeregex_path = os.path.join(output_dir, "timeregex.properties")

    with open(indexer_path, "w") as f:
        f.write(indexer_content)
    with open(timeregex_path, "w") as f:
        f.write(timeregex_content)

    print("📝 Wrote indexer.properties and timeregex.properties")

def process_and_rename_tiffs(base_date_str, start_hour, folder, TIFF_DIR):
    print("🔄 Processing and renaming TIFFs...")

    base_datetime = datetime.strptime(base_date_str, "%Y-%m-%d") + timedelta(hours=int(start_hour))
    output_dir = os.path.join(GEOSERVER_HOST_PATH, folder)
    os.makedirs(GEOSERVER_HOST_PATH, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    for f in os.listdir(output_dir):
        f_path = os.path.join(output_dir, f)
        if os.path.isfile(f_path):
            os.remove(f_path)
        elif os.path.isdir(f_path):
            shutil.rmtree(f_path)
    print(f"🧹 Cleared existing files in: {output_dir}")
    write_mosaic_config_files(output_dir)
    subdir_path = os.path.join(TIFF_DIR, folder)
    print("--------------------------------" + subdir_path)

    nomecartella, nomevariabile = subdir_path.rsplit('-', 1)

    # Extract offset from end of nomecartella (e.g., "cum6" → 6)
    match = re.search(r'(\d+)$', nomecartella)
    cumulata_offset = int(match.group(1)) if match else 0
    print(f"📁 Entering: {subdir_path} (variabile: {nomevariabile}) ➕ Offset: {cumulata_offset}")

    # Get matching files
    tiff_files = sorted([
        f for f in os.listdir(subdir_path)
        if f.startswith(f"{nomevariabile}_comp_") and f.endswith(".tif")
    ])

    for i, filename in enumerate(tiff_files):
        total_hours = cumulata_offset + i
        new_datetime = base_datetime + timedelta(hours=total_hours)
        formatted_time = new_datetime.strftime("%Y%m%d%H")

        new_filename = f"{nomevariabile}_comp_{formatted_time}.tif"
        src = os.path.join(subdir_path, filename)
        dst = os.path.join(output_dir, new_filename)

        shutil.copy(src, dst)
        print(f"  ✅ {filename} → {folder}/{new_filename}")

        # Optionally clean up the subdirectory
        try:
            os.rmdir(subdir_path)
        except OSError:
            pass  # Directory not empty or still in use

# === UTILS ===
def create_image_mosaic_store(folder, GEOSERVER_URL):
    """Create or refresh an ImageMosaic store with improved handling."""
    from maps.tasks.geoserver_utils import upload_geotiff_generic
    
    # Use the directory path for the mosaic
    mosaic_path = os.path.join(GEOSERVER_DATA_DIR, folder)
    
    # Use the improved generic function that handles ImageMosaic updates properly
    success = upload_geotiff_generic(
        geoserver_url=GEOSERVER_URL,
        file_path=mosaic_path,
        store_name=folder,
        username=GEOSERVER_USERNAME,
        password=GEOSERVER_PASSWORD,
        workspace=WORKSPACE
    )
    
    if success:
        print(f"✅ Successfully created/updated ImageMosaic store: {folder}")
        return True
    else:
        print(f"❌ Failed to create/update ImageMosaic store: {folder}")
        return False
        return False
    print("✅ Created coverage store.")
    return True

# def delete_coverage_store(folder):
#     url = f"{GEOSERVER_URL}/rest/workspaces/{WORKSPACE}/coveragestores/{folder}?recurse=true"
#     r = requests.delete(url, auth=HTTPBasicAuth(GEOSERVER_USERNAME, GEOSERVER_PASSWORD))
#     if r.status_code in [200, 202]:
#         print("🗑️ Deleted existing coverage store.")
#     elif r.status_code == 404:
#         print("ℹ️ No existing coverage store found.")
#     else:
#         print(f"❌ Failed to delete coverage store: {r.status_code} - {r.text}")

def publish_layer(folder, GEOSERVER_URL):
    url = f"{GEOSERVER_URL}/rest/workspaces/{WORKSPACE}/coveragestores/{folder}/coverages"
    headers = {"Content-Type": "text/xml"}
    sanitized_layer_name = folder.strip()  # Ensure no extra spaces
    data = f"""
    <coverage>
        <name>{folder}</name>
        <nativeName>{folder}</nativeName>
        <title>{folder}</title>
        <enabled>true</enabled>
        <srs>EPSG:4326</srs>
    </coverage>
    """.strip()

    r = requests.post(url, data=data, headers=headers,
                      auth=HTTPBasicAuth(GEOSERVER_USERNAME, GEOSERVER_PASSWORD))
    if r.status_code not in [200, 201]:
        print("❌ Failed to publish layer:", r.text)
        return False
    print("✅ Published mosaic layer.")
    return True

def bind_sld(folder, GEOSERVER_URL):
    sld = [key for key, values in sld_dir_mapping.items() if folder in values]
    url = f"{GEOSERVER_URL}/rest/layers/{WORKSPACE}:{folder}"
    if not sld:
        print(f"❌ No SLD found for folder {folder}.")
        return False
    sld = sld[0]  # Get the first matching SLD
    print("----------" + folder + "  " + sld)
    headers = {"Content-Type": "application/xml"}
    data = f"""
    <layer>
        <defaultStyle>
            <name>{sld}</name>
        </defaultStyle>
    </layer>
    """.strip()

    r = requests.put(url, data=data, headers=headers,
                     auth=HTTPBasicAuth(GEOSERVER_USERNAME, GEOSERVER_PASSWORD))
    if r.status_code not in [200, 201]:
        print("❌ Failed to enable time dimension:", r.text)
        return False
    print("✅ Time dimension enabled and style applied.")
    return True

def enable_time_dimension(folder, GEOSERVER_URL):
    url = f"{GEOSERVER_URL}/rest/workspaces/{WORKSPACE}/coveragestores/{folder}/coverages/{folder}"
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

    r = requests.put(url, data=data, headers=headers,
                     auth=HTTPBasicAuth(GEOSERVER_USERNAME, GEOSERVER_PASSWORD))
    if r.status_code not in [200, 201]:
        print("❌ Failed to enable time dimension:", r.text)
        return False
    print("✅ Time dimension enabled and style applied.")
    return True

def ensure_tiff_files_exist(folder, TIFF_DIR):
    tiff_folder = os.path.join(TIFF_DIR, folder)
    tiff_files = [f for f in os.listdir(tiff_folder) if f.endswith(".tif") or f.endswith(".tiff")]
    if not tiff_files:
        print("⚠️ No TIFF files found.")
        return False
    print(f"📁 Found {len(tiff_files)} TIFF files.")
    return True
