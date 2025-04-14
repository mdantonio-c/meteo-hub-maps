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

sld_dir_mapping = {
    "hcc": ["cloud_hml-hcc"],
    "lcc": ["cloud_hml-lcc"],
    "mcc": ["cloud_hml-mcc"],
    "tcc_1": ["cloud-tcc"],
    "prp_1_3": ["prec1-tp", "prec3-tp"],
    "prp_6_12_24": ["prec6-tp", "prec12-tp", "prec24-tp"],
    "prs": ["pressure-pmsl"],
    "rh_1": ["humidity-r"],
    "sf_1_3": ["snow1-snow", "snow3-snow"],
    "sf_6_12_24": ["snow6-snow", "snow12-snow", "snow24-snow"],
    "t2m": ["t2m-t2m"],
    "ws10m_2": ["wind-10u", "wind-10v", "wind-vmax_10m"],
}

# === CONFIGURATION ===
# GEOSERVER_URL = "http://localhost:8081/geoserver"
GEOSERVER_USERNAME = Env.get("GEOSERVER_ADMIN_USER", None)
GEOSERVER_PASSWORD = Env.get("GEOSERVER_ADMIN_PASSWORD", None)
GEOSERVER_URL = "http://geoserver.dockerized.io:8080/geoserver"
WORKSPACE = "meteohub"
RENAMED_FILES = "copies"
BASE_PATH = "/meteo"
# TIFF_DIR = f"{BASE_PATH}/Windy-12-ICON_2I_all2km.web/Italia"  # Local path containing .tiff files
GEOSERVER_HOST_PATH = f"/geoserver_data/{RENAMED_FILES}"
GEOSERVER_DATA_DIR = f"geoserver_data/{RENAMED_FILES}/"  # Path where GeoServer can access TIFFs

@CeleryExt.task(idempotent=True)
def update_geoserver_image_mosaic(
    self,
    GEOSERVER_URL: str,
    run: str,
    date: str = datetime.now().strftime("%Y-%m-%d"),
    sld_directory: Optional[str] = "/SLDs",
) -> None:
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
            if ensure_tiff_files_exist(folder, TIFF_DIR):
                # delete_coverage_store()
                create_image_mosaic_store(folder, GEOSERVER_URL)
            publish_layer(folder, GEOSERVER_URL)
            bind_sld(folder, GEOSERVER_URL)
            enable_time_dimension(folder, GEOSERVER_URL)
    create_ready_file(TIFF_DIR, run, date)
    
def update_styles(sld_directory: Optional[str] = None) -> None:
    if sld_directory:
        print(f"📂 Processing SLD directory: {sld_directory}")
        for folder in os.listdir(sld_directory):
            create_or_update_sld(folder, sld_directory)

def create_or_update_sld(folder: str, sld_directory: str) -> None:
    style_name = folder.rsplit('.')[0]
    sld_path = os.path.join(sld_directory, folder)
    if not os.path.exists(sld_path):
        print(f"❌ SLD directory does not exist: {sld_path}")
        return

    # Check if SLD file exists
    sld_file = sld_path
    if not os.path.exists(sld_file):
        print(f"❌ SLD file does not exist: {sld_file}")
        return

    with open(sld_file, 'rb') as sld_file:
        sld_content = sld_file.read()
        
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
            GEOSERVER_URL,
            sld=sld_content,
            layer_name=style_name,
            USERNAME=GEOSERVER_USERNAME,
            PASSWORD=GEOSERVER_PASSWORD,
        )
        
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
    
def create_ready_file(base_path, run: str, date: str) -> None:
    """Create a ready file to indicate that the process is complete."""
    data_path = base_path
    ready_file_path = os.path.join(data_path, f"{date}{run}.GEOSERVER.READY")
    with open(ready_file_path, "w") as f:
        f.write(f"Run: {run}\nDate: {date}\n")
    log.info(f"Ready file created at {ready_file_path}")    

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
    url = f"{GEOSERVER_URL}/rest/workspaces/{WORKSPACE}/coveragestores"
    headers = {"Content-Type": "text/xml"}
    data = f"""
    <coverageStore>
        <name>{folder}</name>
        <type>ImageMosaic</type>
        <enabled>true</enabled>
        <workspace>{WORKSPACE}</workspace>
        <url>file:{os.path.join(GEOSERVER_DATA_DIR, folder)}</url>
    </coverageStore>
    """.strip()

    r = requests.post(url, data=data, headers=headers,
                      auth=HTTPBasicAuth(GEOSERVER_USERNAME, GEOSERVER_PASSWORD))
    # If store already exists (HTTP 409), try updating it
    if r.status_code in [409, 500]:
        print("⚠️ Coverage store already exists. Trying to update...")
        update_url = f"{GEOSERVER_URL}/rest/workspaces/{WORKSPACE}/coveragestores/{folder}"
        r = requests.put(update_url, data=data, headers=headers,
                         auth=HTTPBasicAuth(GEOSERVER_USERNAME, GEOSERVER_PASSWORD))
        if r.status_code in [200, 201]:
            print("✅ Updated existing coverage store.")
            return True
        else:
            print("❌ Failed to update existing coverage store:", r.text)
            return False
    if r.status_code not in [200, 201]:
        print("❌ Failed to create coverage store:",r.status_code,  r.text)
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

# # === MAIN ===
# if __name__ == "__main__":
#     for folder in os.listdir(TIFF_DIR):
#         folder_path = os.path.join(TIFF_DIR, folder)
#         if os.path.isdir(folder_path):
#             flat_sld_dirs = [item for sublist in sld_dir_mapping.values() for item in sublist]
#             if folder in flat_sld_dirs:
#                 print(f"📂 Processing folder: {folder}")
#                 process_and_rename_tiffs("2025-04-09", 12, folder)
#             if ensure_tiff_files_exist(folder):
#                 # delete_coverage_store()
#                 create_image_mosaic_store(folder)
#             publish_layer(folder)
#             bind_sld(folder)
#             enable_time_dimension(folder)
