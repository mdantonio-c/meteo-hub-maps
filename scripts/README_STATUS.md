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

The REST API exposes a read-only system status endpoint. It does not accept status updates; use the scripts above to write status changes.

### Get system status
```bash
curl http://localhost:8080/api/service/status
```

`GET /api/status` is a separate liveness check that returns `Server is alive`.

### Set a detailed status
```bash
rapydo shell backend 'python scripts/set_status.py'
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
