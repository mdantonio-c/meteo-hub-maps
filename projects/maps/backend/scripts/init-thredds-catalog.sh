#!/bin/bash
# Initialize THREDDS MER Water Level Catalog Directories
# This script creates the required directory structure for MER water-level data
# to be properly exposed through THREDDS

set -e

THREDDS_DATA_PATH="${THREDDS_DATA_PATH:-/thredds_ugrid}"
MER_ARPAE_PATH="${THREDDS_DATA_PATH}/MER/water-level-arpae"
MER_DPC_PATH="${THREDDS_DATA_PATH}/MER/water-level-dpc"

echo "Initializing THREDDS MER Water Level Catalog directories..."
echo "THREDDS_DATA_PATH: ${THREDDS_DATA_PATH}"

# Create ARPAE water level directory
if [ ! -d "${MER_ARPAE_PATH}" ]; then
    echo "Creating directory: ${MER_ARPAE_PATH}"
    mkdir -p "${MER_ARPAE_PATH}"
else
    echo "Directory already exists: ${MER_ARPAE_PATH}"
fi

# Create DPC water level directory
if [ ! -d "${MER_DPC_PATH}" ]; then
    echo "Creating directory: ${MER_DPC_PATH}"
    mkdir -p "${MER_DPC_PATH}"
else
    echo "Directory already exists: ${MER_DPC_PATH}"
fi

# Verify directories were created
if [ -d "${MER_ARPAE_PATH}" ] && [ -d "${MER_DPC_PATH}" ]; then
    echo "✓ THREDDS MER catalog directories initialized successfully"
    ls -la "${THREDDS_DATA_PATH}/MER/" 2>/dev/null || echo "  (directories empty, waiting for first ingestion)"
    exit 0
else
    echo "✗ Failed to initialize THREDDS directories"
    exit 1
fi
