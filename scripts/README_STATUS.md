# Status Management Scripts

Scripts for managing MeteoHub Maps system status and maintenance mode.

## Quick Toggle

### Enable Maintenance Mode
```bash
rapydo shell backend 'python scripts/toggle_maintenance.py on'
```

### Enable Maintenance Mode with Custom Message
```bash
rapydo shell backend 'python scripts/toggle_maintenance.py on "Database upgrade in progress"'
```

### Disable Maintenance Mode (Return to Operational)
```bash
rapydo shell backend 'python scripts/toggle_maintenance.py off'
```

### Check Current Status
```bash
rapydo shell backend 'python scripts/toggle_maintenance.py status'
```

## Interactive Configuration

For detailed status configuration with prompts:

```bash
rapydo shell backend 'python scripts/set_status.py'
```

This interactive script will ask you:
1. Status type (operational, maintenance, degraded, outage)
2. Status message
3. Scheduled start/end times
4. Affected services

## API Usage

You can also use the REST API directly:

### Get Status
```bash
curl http://localhost:8080/api/status
```

### Set Status
```bash
curl -X POST http://localhost:8080/api/status \
  -H "Content-Type: application/json" \
  -d '{
    "status": "maintenance",
    "message": "Scheduled maintenance",
    "scheduled_start": "2025-01-15T02:00:00Z",
    "scheduled_end": "2025-01-15T06:00:00Z",
    "affected_services": ["all"]
  }'
```

### Clear Status
```bash
curl -X POST http://localhost:8080/api/status \
  -H "Content-Type: application/json" \
  -d '{"status": "operational"}'
```

## Status File Location

Default: `/var/lib/meteohub/status.json`

The directory is mounted from `${DATA_DIR}/status` on the host to persist across container restarts.

Configure via `STATUS_FILE_PATH` environment variable if needed:
```bash
export STATUS_FILE_PATH=/custom/path/status.json
```

## Status Values

- `operational` - All systems functioning normally
- `maintenance` - Scheduled maintenance in progress or planned
- `degraded` - System experiencing partial issues
- `outage` - System unavailable

## Examples

### Emergency Outage
```bash
rapydo shell backend 'python scripts/toggle_maintenance.py on "Emergency outage - investigating"'
```

### Planned Maintenance
```bash
rapydo shell backend 'python scripts/set_status.py'
# Then follow interactive prompts
```

### Return to Service
```bash
rapydo shell backend 'python scripts/toggle_maintenance.py off'
```
