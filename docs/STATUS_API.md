# System Status API

The System Status API allows MeteoHub Maps to signal maintenance windows, outages, or operational state changes to clients.

## Endpoint

### GET /api/status

Retrieves the current system status and any scheduled maintenance information.

**Response Fields:**
- `status` (string): Current system state
  - `operational` - All systems functioning normally
  - `maintenance` - Scheduled maintenance in progress or planned
  - `degraded` - System experiencing partial issues
  - `outage` - System unavailable
- `message` (string, optional): Human-readable description of current status
- `scheduled_start` (string, optional): ISO 8601 timestamp for planned maintenance start
- `scheduled_end` (string, optional): ISO 8601 timestamp for planned maintenance end
- `affected_services` (array): List of affected service names (e.g., ["maps", "windy", "radar"])
- `updated_at` (string): ISO 8601 timestamp of last status update

**Example Response:**
```json
{
  "status": "maintenance",
  "message": "Scheduled database upgrade",
  "scheduled_start": "2025-01-15T02:00:00Z",
  "scheduled_end": "2025-01-15T06:00:00Z",
  "affected_services": ["maps", "windy", "radar"],
  "updated_at": "2025-01-14T10:00:00Z"
}
```

### POST /api/status

Updates the system status. This endpoint should be called by administrators or automation systems.

**Request Body:**
```json
{
  "status": "maintenance",
  "message": "Scheduled maintenance window",
  "scheduled_start": "2025-01-15T02:00:00Z",
  "scheduled_end": "2025-01-15T06:00:00Z",
  "affected_services": ["maps", "windy"]
}
```

**Required Fields:**
- `status` - Must be one of: `operational`, `maintenance`, `degraded`, `outage`

**Optional Fields:**
- `message` - Descriptive text about the status
- `scheduled_start` - Planned start time (ISO 8601)
- `scheduled_end` - Planned end time (ISO 8601)
- `affected_services` - Array of service identifiers

**Success Response (200):**
```json
{
  "success": true,
  "status": {
    "status": "maintenance",
    "message": "Scheduled maintenance window",
    "scheduled_start": "2025-01-15T02:00:00Z",
    "scheduled_end": "2025-01-15T06:00:00Z",
    "affected_services": ["maps", "windy"],
    "updated_at": "2025-01-14T10:00:00Z"
  }
}
```

**Error Response (400):**
```json
{
  "error": "Invalid status. Must be one of: operational, maintenance, degraded, outage"
}
```

## Configuration

The status file is stored at `/var/lib/meteohub/status.json` by default (configured via `STATUS_FILE_PATH` environment variable).

**Volume Mount:** The directory `/var/lib/meteohub` is mounted from `${DATA_DIR}/status` on the host to persist status across container restarts.

**Custom Location:**
```bash
export STATUS_FILE_PATH=/custom/path/status.json
```

## Usage Examples

### Check System Status (Client)

```bash
curl http://localhost:8080/api/status
```

### Set Maintenance Window (Admin)

```bash
curl -X POST http://localhost:8080/api/status \
  -H "Content-Type: application/json" \
  -d '{
    "status": "maintenance",
    "message": "Planned system upgrade",
    "scheduled_start": "2025-01-15T02:00:00Z",
    "scheduled_end": "2025-01-15T06:00:00Z",
    "affected_services": ["all"]
  }'
```

### Clear Status (Return to Operational)

```bash
curl -X POST http://localhost:8080/api/status \
  -H "Content-Type: application/json" \
  -d '{
    "status": "operational"
  }'
```

### Client-Side Integration (JavaScript)

```javascript
async function checkSystemStatus() {
  const response = await fetch('/api/status');
  const status = await response.json();
  
  if (status.status === 'maintenance') {
    showMaintenanceNotice(status.message, status.scheduled_start);
  } else if (status.status === 'outage') {
    showOutageNotice(status.message);
  } else if (status.status === 'degraded') {
    showDegradedNotice(status.message);
  }
  
  return status.status === 'operational';
}
```

## Status File Format

The status is persisted as JSON:

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

## Automation

You can automate status updates using cron jobs or CI/CD pipelines:

```bash
# Start maintenance
curl -X POST http://localhost:8080/api/status \
  -H "Content-Type: application/json" \
  -d '{"status": "maintenance", "message": "Deploying new version"}'

# ... perform maintenance ...

# Return to operational
curl -X POST http://localhost:8080/api/status \
  -H "Content-Type: application/json" \
  -d '{"status": "operational"}'
```

## Testing

Run the test suite:

```bash
rapydo shell backend 'pytest projects/maps/backend/tests/custom/test_api_status.py -v'
```
