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
WW3_BASE_PATH = Env.get("WW3_DATA_PATH", "/ww3")
COPIES_BASE_DIRECTORY = "/geoserver_data/copies"

@CeleryExt.task(idempotent=True)
def (self, run_date):
    log.info(f"Starting ww3 ingestion for run {run_date}")
    
    create_workspace_generic(GEOSERVER_URL, USERNAME, PASSWORD, WORKSPACE)
    
    # Identify variables from directories, excluding 'dir-dir'
    if not os.path.exists(WW3_BASE_PATH):
        log.warning(f"WW3 base path not found: {WW3_BASE_PATH}")
        return

    variables = [
        d for d in os.listdir(WW3_BASE_PATH) 
        if os.path.isdir(os.path.join(WW3_BASE_PATH, d)) and d != 'dir-dir'
    ]
    
    # Handle SLDs
    sld_root = None
    possible_paths = [
        "/SLDs",
        "/projects/maps/builds/geoserver/SLDs",
        os.path.join(os.getcwd(), "projects/maps/builds/geoserver/SLDs")
    ]
    for path in possible_paths:
        if os.path.exists(path):
            sld_root = path
            break
            
    if sld_root:
        ww3_sld_dir = os.path.join(sld_root, "ww3")
        if not os.path.exists(ww3_sld_dir):
            os.makedirs(ww3_sld_dir)
            
        for var in variables:
            sld_path = os.path.join(ww3_sld_dir, f"ww3_{var}.sld")
            if not os.path.exists(sld_path):
                create_mock_sld(var, sld_path)
                log.info(f"Created mock SLD for {var} at {sld_path}")
        
        log.info(f"Updating SLDs from {ww3_sld_dir}")
        update_slds_from_local_folders(ww3_sld_dir, GEOSERVER_URL, USERNAME, PASSWORD)
    else:
        log.warning("SLD root directory not found, skipping SLD creation/update")
    
    for var in variables:
        process_ww3_variable(var)
            
    # Cleanup old GEOSERVER.READY files
    for f in os.listdir(WW3_BASE_PATH):
        if f.endswith(".GEOSERVER.READY"):
            try:
                os.remove(os.path.join(WW3_BASE_PATH, f))
            except Exception as e:
                log.warning(f"Failed to remove {f}: {e}")

    # Calculate range for GEOSERVER.READY filename
    all_timestamps = []
    for var in variables:
        source_dir = os.path.join(WW3_BASE_PATH, var)
        if os.path.exists(source_dir):
            for f in os.listdir(source_dir):
                try:
                    # Try dd-MM-yyyy-HH
                    parts = f.split('.')[0].split('-')
                    if len(parts) == 4:
                        dt = datetime.strptime(f.split('.')[0], "%d-%m-%Y-%H")
                        all_timestamps.append(dt)
                    elif len(parts) == 5:
                        dt = datetime.strptime(f.split('.')[0], "%d-%m-%Y-%H-%M")
                        all_timestamps.append(dt)
                except ValueError:
                    continue

    if all_timestamps:
        min_date = min(all_timestamps)
        max_date = max(all_timestamps)
        from_str = min_date.strftime("%Y%m%d%H")
        to_str = max_date.strftime("%Y%m%d%H")
        ready_filename = f"{from_str}-{to_str}.GEOSERVER.READY"
    else:
        ready_filename = f"{run_date}.GEOSERVER.READY"

    # Create GEOSERVER.READY file
    ready_file = os.path.join(WW3_BASE_PATH, ready_filename)
    with open(ready_file, "w") as f:
        f.write(f"Processed by GeoServer at {datetime.now().isoformat()}\n")
        f.write(f"Run: {run_date}\n")
    log.info(f"Created {ready_file}")
    
    # Cleanup CELERY.CHECKED
    for f in os.listdir(WW3_BASE_PATH):
        if f.endswith(".CELERY.CHECKED"):
            try:
                os.remove(os.path.join(WW3_BASE_PATH, f))
            except Exception as e:
                log.warning(f"Failed to remove {f}: {e}")

def process_ww3_variable(var):
    layer_name = f"ww3_{var}"
    store_name = f"mosaic_{layer_name}"
    
    source_dir = os.path.join(WW3_BASE_PATH, var)
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
        if publish_layer_generic(GEOSERVER_URL, store_name, layer_name, USERNAME, PASSWORD, WORKSPACE):
            enable_time_dimension(GEOSERVER_URL, store_name, layer_name, USERNAME, PASSWORD)
            
            # SLD Association
            sld_name = f"ww3_{var}"
            associate_sld_with_layer_generic(GEOSERVER_URL, layer_name, sld_name, USERNAME, PASSWORD, WORKSPACE)
        else:
            log.error(f"Failed to publish layer {layer_name}")
    else:
        log.error(f"Failed to upload GeoTIFF/Mosaic for {layer_name}")

def create_mock_sld(var, sld_path):
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor version="1.0.0" 
 xsi:schemaLocation="http://www.opengis.net/sld StyledLayerDescriptor.xsd" 
 xmlns="http://www.opengis.net/sld" 
 xmlns:ogc="http://www.opengis.net/ogc" 
 xmlns:xlink="http://www.w3.org/1999/xlink" 
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <NamedLayer>
    <Name>ww3_{var}</Name>
    <UserStyle>
      <Title>WW3 {var}</Title>
      <FeatureTypeStyle>
        <Rule>
          <RasterSymbolizer>
            <Opacity>1.0</Opacity>
            <ColorMap>
              <ColorMapEntry color="#000000" quantity="0" label="0"/>
              <ColorMapEntry color="#FFFFFF" quantity="10" label="10"/>
            </ColorMap>
          </RasterSymbolizer>
        </Rule>
      </FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>
"""
    with open(sld_path, "w") as f:
        f.write(content)

def create_mosaic_config(target_dir):
    indexer_content = "PropertyCollectors=TimestampFileNameExtractorSPI[timeregex](time)\n" \
                      "TimeAttribute=time\n" \
                      "Schema=*the_geom:Polygon,location:String,time:java.util.Date\n"
    
    # Regex for dd-MM-YYYY-hh.tif
    timeregex_content = "regex=([0-9]{2}-[0-9]{2}-[0-9]{4}-[0-9]{2}-[0-9]{2}),format=dd-MM-yyyy-HH-mm\n"
    
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
