#!/bin/bash
# Setup script for status file directory
# Run this once to create the necessary directory structure

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
STATUS_DIR="${PROJECT_ROOT}/data/status"

echo "Setting up status file directory..."
echo "Directory: ${STATUS_DIR}"

# Create directory if it doesn't exist
if [ ! -d "${STATUS_DIR}" ]; then
    mkdir -p "${STATUS_DIR}"
    echo "✓ Created directory: ${STATUS_DIR}"
else
    echo "✓ Directory already exists: ${STATUS_DIR}"
fi

# Set permissions
chmod 755 "${STATUS_DIR}"
echo "✓ Permissions set: 755"

# Create initial status file if it doesn't exist
STATUS_FILE="${STATUS_DIR}/status.json"
if [ ! -f "${STATUS_FILE}" ]; then
    cat > "${STATUS_FILE}" << 'EOF'
{
  "status": "operational",
  "message": null,
  "scheduled_start": null,
  "scheduled_end": null,
  "affected_services": [],
  "updated_at": null
}
EOF
    echo "✓ Created initial status.json"
else
    echo "✓ status.json already exists"
fi

echo ""
echo "Setup complete!"
echo ""
echo "The status directory is now ready to be mounted by Docker."
echo "Volume mount: ${STATUS_DIR}:/var/lib/meteohub"
echo ""
echo "Current configuration:"
echo "  STATUS_FILE_PATH: /var/lib/meteohub/status.json"
echo "  Host directory: ${STATUS_DIR}"
echo ""
