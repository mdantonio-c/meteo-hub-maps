# Status Endpoint - Quick Reference

## 🚀 Quick Commands

```bash
# Enable maintenance
rapydo shell backend 'python scripts/toggle_maintenance.py on "Maintenance message"'

# Disable maintenance  
rapydo shell backend 'python scripts/toggle_maintenance.py off'

# Check status
rapydo shell backend 'python scripts/toggle_maintenance.py status'

# Interactive setup
rapydo shell backend 'python scripts/set_status.py'
```

## 🌐 API Endpoints

### GET /api/status
```bash
curl http://localhost:8080/api/status
```

### POST /api/status
```bash
curl -X POST http://localhost:8080/api/status \
  -H "Content-Type: application/json" \
  -d '{"status": "maintenance", "message": "Upgrading database"}'
```

## 📊 Status Values

- `operational` - All systems normal (default)
- `maintenance` - Scheduled maintenance
- `degraded` - Partial issues  
- `outage` - System unavailable

## 📁 Files

- **Endpoint**: `projects/maps/backend/endpoints/status.py`
- **Scripts**: `scripts/toggle_maintenance.py`, `scripts/set_status.py`
- **Config**: `projects/maps/confs/commons.yml` (volume mounts)
- **Data**: `data/status/status.json` (persisted)
- **Docs**: `docs/STATUS_API.md`, `docs/STATUS_SETUP.md`

## 🔧 Configuration

```yaml
# project_configuration.yaml
STATUS_FILE_PATH: /var/lib/meteohub/status.json
HOST_STATUS_DIR: ${DATA_DIR}/status

# commons.yml (volume mounts)
- ${HOST_STATUS_DIR}:/var/lib/meteohub
```

## ✅ Setup (One-time)

```bash
bash scripts/setup_status_dir.sh
```

## 🧪 Testing

```bash
rapydo shell backend 'pytest projects/maps/backend/tests/custom/test_api_status.py -v'
```

## 📝 Example Response

```json
{
  "status": "maintenance",
  "message": "Scheduled upgrade",
  "scheduled_start": "2025-01-15T02:00:00Z",
  "scheduled_end": "2025-01-15T06:00:00Z",
  "affected_services": ["maps", "windy"],
  "updated_at": "2025-01-14T10:00:00Z"
}
```

## 🔗 Full Documentation

- [STATUS_API.md](STATUS_API.md) - Complete API reference
- [STATUS_SETUP.md](STATUS_SETUP.md) - Setup and usage guide
- [README_STATUS.md](../scripts/README_STATUS.md) - Scripts reference
