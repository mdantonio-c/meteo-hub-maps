#!/usr/bin/env python3
"""
Quick toggle script for maintenance mode.

Usage:
    python scripts/toggle_maintenance.py on   - Enable maintenance mode
    python scripts/toggle_maintenance.py off  - Disable maintenance mode (operational)
    python scripts/toggle_maintenance.py status - Show current status
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from restapi.env import Env
except ImportError:
    Env = None

# Use environment variable if set, otherwise use project-local path for testing
STATUS_FILE_PATH = (
    Env.get("STATUS_FILE_PATH", None)
    if Env is not None
    else os.environ.get("STATUS_FILE_PATH")
)
if not STATUS_FILE_PATH:
    # Fallback to project directory for local testing outside Docker
    from pathlib import Path
    import sys
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    STATUS_FILE_PATH = str(project_root / "data" / "status" / "status.json")


def get_current_status():
    """Read current status from file."""
    if not Path(STATUS_FILE_PATH).exists():
        return {
            "status": "operational",
            "message": None,
            "scheduled_start": None,
            "scheduled_end": None,
            "affected_services": [],
            "updated_at": None,
        }
    
    with open(STATUS_FILE_PATH, "r") as f:
        return json.load(f)


def set_maintenance_mode(message="Scheduled maintenance"):
    """Enable maintenance mode."""
    now = datetime.now(timezone.utc)
    status_data = {
        "status": "maintenance",
        "message": message,
        "scheduled_start": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scheduled_end": (now.replace(hour=now.hour + 2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "affected_services": ["all"],
        "updated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    
    Path(STATUS_FILE_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(STATUS_FILE_PATH, "w") as f:
        json.dump(status_data, f, indent=2)
    
    print(f"✓ Maintenance mode ENABLED")
    print(f"  Message: {message}")
    print(f"  Started: {status_data['scheduled_start']}")


def set_operational_mode():
    """Disable maintenance mode (return to operational)."""
    now = datetime.now(timezone.utc)
    status_data = {
        "status": "operational",
        "message": None,
        "scheduled_start": None,
        "scheduled_end": None,
        "affected_services": [],
        "updated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    
    Path(STATUS_FILE_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(STATUS_FILE_PATH, "w") as f:
        json.dump(status_data, f, indent=2)
    
    print("✓ Maintenance mode DISABLED")
    print("  Status: OPERATIONAL")


def show_status():
    """Display current status."""
    status = get_current_status()
    
    print("\n" + "="*50)
    print("CURRENT STATUS")
    print("="*50)
    print(f"Status: {status['status'].upper()}")
    
    if status.get('message'):
        print(f"Message: {status['message']}")
    
    if status.get('scheduled_start'):
        print(f"Start: {status['scheduled_start']}")
    
    if status.get('scheduled_end'):
        print(f"End: {status['scheduled_end']}")
    
    if status.get('affected_services'):
        print(f"Affected: {', '.join(status['affected_services'])}")
    
    if status.get('updated_at'):
        print(f"Updated: {status['updated_at']}")
    
    print("="*50 + "\n")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "on":
        message = sys.argv[2] if len(sys.argv) > 2 else "Scheduled maintenance"
        set_maintenance_mode(message)
    
    elif command == "off":
        set_operational_mode()
    
    elif command == "status":
        show_status()
    
    elif command == "help":
        print(__doc__)
    
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)
