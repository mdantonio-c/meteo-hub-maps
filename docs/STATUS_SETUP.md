# Status Endpoint Setup Guide

This guide explains how to configure and use the system status endpoint for maintenance signaling.

## Overview

The status endpoint (`/api/status`) allows MeteoHub Maps to signal maintenance windows, outages, or operational state changes to clients.

## Architecture

```
Host: data/status/status.json
          ↓ (Docker volume mount)
Container: /var/lib/meteohub/status.json
          ↓ (read/write)
API: GET/POST /api/status
```

## Initial Setup

### 1. Run Setup Script (One-time)

```bash
cd /home/dcrisant/Documents/MeteoHub/meteo-hub-maps
bash scripts/setup_status_dir.sh
```

This creates:
- Directory: `data/status/`
- Initial file: `data/status/status.json`

### 2. Verify Configuration

Check that volume mounts are configured in `projects/maps/confs/commons.yml`:

```yaml
backend:
  volumes:
    - ${HOST_STATUS_DIR}:/var/lib/meteohub

celery:
  volumes:
    - ${HOST_STATUS_DIR}:/var/lib/meteohub
```

Where `HOST_STATUS_DIR=${DATA_DIR}/status` (from `project_configuration.yaml`).

## Usage

### Quick Commands (Inside Container)

```bash
# Enable maintenance mode
rapydo shell backend 'python scripts/toggle_maintenance.py on "Database upgrade"'

# Disable maintenance mode
rapydo shell backend 'python scripts/toggle_maintenance.py off'

# Check status
rapydo shell backend 'python scripts/toggle_maintenance.py status'

# Interactive configuration
rapydo shell backend 'python scripts/set_status.py'
```

### API Calls

```bash
# Get current status
curl http://localhost:8080/api/status

# Set maintenance
curl -X POST http://localhost:8080/api/status \
  -H "Content-Type: application/json" \
  -d '{
    "status": "maintenance",
    "message": "Scheduled maintenance",
    "scheduled_start": "2025-01-15T02:00:00Z",
    "scheduled_end": "2025-01-15T06:00:00Z",
    "affected_services": ["all"]
  }'

# Return to operational
curl -X POST http://localhost:8080/api/status \
  -H "Content-Type: application/json" \
  -d '{"status": "operational"}'
```

### Client Integration

```javascript
// Check status before making API calls
async function checkSystemStatus() {
  const response = await fetch('/api/status');
  const status = await response.json();
  
  if (status.status === 'maintenance') {
    showMaintenanceBanner(status.message, status.scheduled_end);
    return false;
  } else if (status.status === 'outage') {
    showOutageBanner(status.message);
    return false;
  }
  
  return true; // operational
}
```

## Status Values

| Status | Description | Use Case |
|--------|-------------|----------|
| `operational` | All systems normal | Default state |
| `maintenance` | Planned maintenance | Scheduled upgrades, deployments |
| `degraded` | Partial issues | Performance problems, some features unavailable |
| `outage` | System unavailable | Critical failures, emergency downtime |

## File Structure

```
data/status/
└── status.json          # Persisted status file (mounted to container)
```

### Status File Format

```json
{
  "status": "operational",
  "message": null,
  "scheduled_start": null,
  "scheduled_end": null,
  "affected_services": [],
  "updated_at": "2025-01-14T10:00:00Z"
}
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `STATUS_FILE_PATH` | `/var/lib/meteohub/status.json` | Path inside container |
| `HOST_STATUS_DIR` | `${DATA_DIR}/status` | Host directory mount |

### Custom Location

To use a different location, set in `.projectrc` or environment:

```bash
export STATUS_FILE_PATH=/custom/path/status.json
```

Update volume mount in `commons.yml` accordingly.

## Automation Examples

### Pre-deployment Maintenance

```bash
#!/bin/bash
# deploy.sh

# Signal maintenance start
rapydo shell backend 'python scripts/toggle_maintenance.py on "Deploying new version"'

# Perform deployment
# ... deployment steps ...

# Signal operational
rapydo shell backend 'python scripts/toggle_maintenance.py off'
```

### Cron-based Status Check

```bash
# crontab -e
# Check status every 5 minutes and alert if not operational
*/5 * * * * curl -s http://localhost:8080/api/status | jq -r '.status' | grep -v "operational" && /usr/local/bin/alert_admin.sh
```

### CI/CD Integration (GitHub Actions)

```yaml
- name: Set maintenance mode
  run: |
    rapydo shell backend 'python scripts/toggle_maintenance.py on "CI/CD deployment"'

- name: Deploy
  run: |
    # ... deployment steps ...

- name: Clear maintenance mode
  run: |
    rapydo shell backend 'python scripts/toggle_maintenance.py off'
```

## Monitoring

### Check Status File Directly

```bash
cat data/status/status.json | jq .
```

### Watch for Changes

```bash
watch -n 5 'cat data/status/status.json | jq .status'
```

### Log Monitoring

Status changes are logged in backend logs:

```bash
rapydo logs backend | grep "System status updated"
```

## Troubleshooting

### Permission Denied

If you get permission errors:

```bash
# Ensure directory exists and has correct permissions
mkdir -p data/status
chmod 755 data/status
```

### Status Not Persisting

Verify volume mount is active:

```bash
# Inside container
rapydo shell backend 'ls -la /var/lib/meteohub/'
rapydo shell backend 'cat /var/lib/meteohub/status.json'
```

### API Returns Error

Check backend logs:

```bash
rapydo logs backend | tail -50
```

## Testing

Run the test suite:

```bash
rapydo shell backend 'pytest projects/maps/backend/tests/custom/test_api_status.py -v'
```

## Best Practices

1. **Set status before maintenance** - Always signal maintenance before starting work
2. **Provide clear messages** - Help users understand what's happening
3. **Include time estimates** - Use `scheduled_start` and `scheduled_end`
4. **Specify affected services** - Be specific about what's impacted
5. **Return to operational** - Always clear status after maintenance completes
6. **Monitor status file** - Ensure it's being written correctly
7. **Test automation** - Verify scripts work before relying on them in production

## Related Documentation

- [STATUS_API.md](../docs/STATUS_API.md) - Complete API documentation
- [API.md](../docs/API.md) - Full API reference (includes status endpoint)
- [AGENTS.md](../AGENTS.md) - Project overview
