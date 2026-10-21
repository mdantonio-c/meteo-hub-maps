#!/bin/sh
set -eu

# Compose clears the image CMD when overriding entrypoint unless command is set.
if [ "$#" -eq 0 ]; then
    set -- proxy
fi

python3 /opt/meteohub-proxy/maintenance.py prepare
python3 /opt/meteohub-proxy/maintenance.py watch &
exec "${MAINTENANCE_ORIGINAL_ENTRYPOINT:-/usr/local/bin/docker-entrypoint}" "$@"
