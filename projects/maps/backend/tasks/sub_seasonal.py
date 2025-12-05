from restapi.connectors.celery import CeleryExt
from restapi.utilities.logs import log
from restapi.env import Env
import os
import shutil
import requests
from datetime import datetime
from maps.tasks.geoserver_utils import (
    upload_geotiff_generic,
    publish_layer_generic,
    create_workspace_generic,
    associate_sld_with_layer_generic,
    update_slds_from_local_folders
)

GEOSERVER_URL = "http://geoserver.dockerized.io:8080/geoserver"
USERNAME = Env.get("GEOSERVER_ADMIN_USER", None)
PASSWORD = Env.get("GEOSERVER_ADMIN_PASSWORD", None)
WORKSPACE = "meteohub"
SUB_SEASONAL_BASE_PATH = "/sub-seasonal-aim"
COPIES_BASE_DIRECTORY = "/geoserver_data/copies"

@CeleryExt.task(idempotent=True)
def update_geoserver_sub_seasonal_layers(self, run_date, range_str):
    log.info(f"Starting sub-seasonal ingestion for run {run_date}, range {range_str}")
    
    create_workspace_generic(GEOSERVER_URL, USERNAME, PASSWORD, WORKSPACE)

    # Update SLDs
    sld_directory = None
    possible_paths = [
        "/SLDs",
        "/projects/maps/builds/geoserver/SLDs",
        os.path.join(os.getcwd(), "projects/maps/builds/geoserver/SLDs")
    ]
    for path in possible_paths:
        if os.path.exists(path):
            sld_directory = path
            break
    
    if sld_directory:
        sld_directory = os.path.join(sld_directory, "sub-seasonal")
        log.info(f"Updating SLDs from {sld_directory}")
        update_slds_from_local_folders(sld_directory, GEOSERVER_URL, USERNAME, PASSWORD)
    else:
        log.warning("SLD directory not found, skipping SLD update")
    
    if not os.path.exists(SUB_SEASONAL_BASE_PATH):
        log.warning(f"Sub-seasonal base path not found: {SUB_SEASONAL_BASE_PATH}")
        return

    variables = [
        d for d in os.listdir(SUB_SEASONAL_BASE_PATH) 
        if os.path.isdir(os.path.join(SUB_SEASONAL_BASE_PATH, d))
    ]
    
    for var in variables:
        var_path = os.path.join(SUB_SEASONAL_BASE_PATH, var)
        values = [
            d for d in os.listdir(var_path)
            if os.path.isdir(os.path.join(var_path, d))
        ]
        for val in values:
            process_sub_seasonal_variable(var, val)

    # Cleanup old GEOSERVER.READY files
    for f in os.listdir(SUB_SEASONAL_BASE_PATH):
        if f.endswith(".GEOSERVER.READY"):
            try:
                os.remove(os.path.join(SUB_SEASONAL_BASE_PATH, f))
                log.info(f"Removed old status file: {f}")
            except Exception as e:
                log.warning(f"Failed to remove {f}: {e}")
            
    # Create GEOSERVER.READY file
    ready_file = os.path.join(SUB_SEASONAL_BASE_PATH, f"{range_str}.GEOSERVER.READY")
    with open(ready_file, "w") as f:
        f.write(f"Processed by GeoServer at {datetime.now().isoformat()}\n")
        f.write(f"Run: {run_date}\n")
        f.write(f"Range: {range_str}\n")
    log.info(f"Created {ready_file}")
    
    # Cleanup CELERY.CHECKED
    for f in os.listdir(SUB_SEASONAL_BASE_PATH):
        if f.endswith(".CELERY.CHECKED"):
            try:
                os.remove(os.path.join(SUB_SEASONAL_BASE_PATH, f))
            except Exception as e:
                log.warning(f"Failed to remove {f}: {e}")

def process_sub_seasonal_variable(var, val):
    layer_name = f"sub-seasonal-{var}-{val}"
    store_name = f"mosaic-{layer_name}"
    
    source_dir = os.path.join(SUB_SEASONAL_BASE_PATH, var, val)
    target_dir = os.path.join(COPIES_BASE_DIRECTORY, layer_name)
    
    if not os.path.exists(source_dir):
        log.warning(f"Source directory not found: {source_dir}")
        return

    # Clean and recreate target directory
    if os.path.exists(target_dir):
        shutil.rmtree(target_dir)
    os.makedirs(target_dir)
    
    # Copy files
    for f in os.listdir(source_dir):
        if f.endswith(".tiff") or f.endswith(".tif"):
            shutil.copy2(os.path.join(source_dir, f), os.path.join(target_dir, f))
            
    # Create properties files
    create_mosaic_config(target_dir)
    
    # Upload and Publish
    if upload_geotiff_generic(GEOSERVER_URL, target_dir, store_name, USERNAME, PASSWORD, WORKSPACE):
        publish_layer_generic(GEOSERVER_URL, store_name, layer_name, USERNAME, PASSWORD, WORKSPACE)
        enable_time_dimension(GEOSERVER_URL, store_name, layer_name, USERNAME, PASSWORD)
        
        # SLD Association
        sld_name = f"{var}_{val}"
        associate_sld_with_layer_generic(GEOSERVER_URL, layer_name, sld_name, USERNAME, PASSWORD, WORKSPACE)

def create_mosaic_config(target_dir):
    indexer_content = "PropertyCollectors=TimestampFileNameExtractorSPI[timeregex](time)\n" \
                      "TimeAttribute=time\n" \
                      "Schema=*the_geom:Polygon,location:String,time:java.util.Date\n"
    
    # Regex for YYYY-MM-DD.tiff
    timeregex_content = "regex=([0-9]{4}-[0-9]{2}-[0-9]{2}),format=yyyy-MM-dd\n"
    
    with open(os.path.join(target_dir, "indexer.properties"), "w") as f:
        f.write(indexer_content)
    with open(os.path.join(target_dir, "timeregex.properties"), "w") as f:
        f.write(timeregex_content)

def enable_time_dimension(geoserver_url, store_name, layer_name, username, password):
    url = f"{geoserver_url}/rest/workspaces/{WORKSPACE}/coveragestores/{store_name}/coverages/{layer_name}"
    headers = {
        "Content-Type": "application/xml",
        "Accept": "application/xml"
    }
    data = """
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
