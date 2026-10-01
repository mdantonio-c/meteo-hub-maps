#!/bin/sh
set -eu

python3 /opt/meteohub-proxy/maintenance.py prepare
python3 /opt/meteohub-proxy/maintenance.py watch &
exec "${MAINTENANCE_ORIGINAL_ENTRYPOINT:-/usr/local/bin/docker-entrypoint}" "$@"
