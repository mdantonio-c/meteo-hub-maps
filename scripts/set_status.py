#!/usr/bin/env python3
"""
Interactive script to set MeteoHub Maps maintenance status.

This script prompts the user for status information and writes it to the status.json file.

Usage:
    python scripts/set_status.py
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from restapi.env import Env

# Use environment variable if set, otherwise use project-local path for testing
STATUS_FILE_PATH = Env.get("STATUS_FILE_PATH", None)
if not STATUS_FILE_PATH:
    # Fallback to project directory for local testing outside Docker
    from pathlib import Path
    import sys
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    STATUS_FILE_PATH = str(project_root / "data" / "status" / "status.json")

VALID_STATUSES = ["operational", "maintenance", "degraded", "outage"]


def prompt_status():
    """Prompt user for status type."""
    print("\nSelect system status:")
    print("  1. operational  - All systems functioning normally")
    print("  2. maintenance  - Scheduled maintenance in progress or planned")
    print("  3. degraded     - System experiencing partial issues")
    print("  4. outage       - System unavailable")
    
    while True:
        choice = input("\nEnter choice (1-4) [1]: ").strip() or "1"
        if choice in ["1", "2", "3", "4"]:
            return VALID_STATUSES[int(choice) - 1]
        print("Invalid choice. Please enter 1-4.")


def prompt_message(status):
    """Prompt user for status message."""
    default_msg = {
        "operational": "",
        "maintenance": "Scheduled maintenance window",
        "degraded": "System experiencing issues",
        "outage": "System unavailable",
    }
    
    prompt_text = f"\nEnter status message [{default_msg.get(status, '')}]: "
    message = input(prompt_text).strip()
    return message if message else (default_msg.get(status) or None)


def prompt_datetime(field_name, default_offset_hours=None):
    """Prompt user for datetime."""
    if default_offset_hours:
        default_dt = datetime.now(timezone.utc) + timedelta(hours=default_offset_hours)
        default_str = default_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        prompt_text = f"Enter {field_name} (ISO 8601, e.g., 2025-01-15T02:00:00Z) [{default_str}]: "
    else:
        default_str = ""
        prompt_text = f"Enter {field_name} (ISO 8601, e.g., 2025-01-15T02:00:00Z) [skip]: "
    
    value = input(prompt_text).strip()
    
    if not value:
        return default_str if default_offset_hours else None
    
    # Basic validation
    try:
        if value.endswith("Z"):
            datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        else:
            datetime.fromisoformat(value)
        return value
    except ValueError:
        print(f"Warning: Invalid datetime format. Using: {value}")
        return value


def prompt_affected_services():
    """Prompt user for affected services."""
    print("\nAffected services (comma-separated):")
    print("  Examples: maps, windy, radar, marine, seasonal, all")
    print("  Leave empty for no specific services")
    
    services = input("Enter services [skip]: ").strip()
    if not services:
        return []
    
    return [s.strip() for s in services.split(",") if s.strip()]


def confirm_status(status_data):
    """Show summary and confirm before writing."""
    print("\n" + "="*60)
    print("STATUS SUMMARY")
    print("="*60)
    print(f"Status:           {status_data['status']}")
    print(f"Message:          {status_data['message'] or 'N/A'}")
    print(f"Scheduled Start:  {status_data['scheduled_start'] or 'N/A'}")
    print(f"Scheduled End:    {status_data['scheduled_end'] or 'N/A'}")
    print(f"Affected Services: {', '.join(status_data['affected_services']) if status_data['affected_services'] else 'N/A'}")
    print("="*60)
    
    confirm = input("\nWrite this status? (y/n) [y]: ").strip().lower()
    return confirm in ["", "y", "yes"]


def write_status(status_data):
    """Write status to file."""
    status_path = Path(STATUS_FILE_PATH)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(status_path, "w") as f:
        json.dump(status_data, f, indent=2)
    
    print(f"\n✓ Status written to {STATUS_FILE_PATH}")


def main():
    """Main interactive flow."""
    print("="*60)
    print("MeteoHub Maps - Status Configuration")
    print("="*60)
    
    status = prompt_status()
    message = prompt_message(status)
    
    scheduled_start = None
    scheduled_end = None
    
    if status in ["maintenance", "degraded", "outage"]:
        if status == "maintenance":
            scheduled_start = prompt_datetime("scheduled start", default_offset_hours=1)
            scheduled_end = prompt_datetime("scheduled end", default_offset_hours=3)
        else:
            scheduled_start = prompt_datetime("issue started", default_offset_hours=-1)
            scheduled_end = prompt_datetime("expected resolution", default_offset_hours=2)
    
    affected_services = prompt_affected_services()
    
    status_data = {
        "status": status,
        "message": message,
        "scheduled_start": scheduled_start,
        "scheduled_end": scheduled_end,
        "affected_services": affected_services,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    
    if not confirm_status(status_data):
        print("\n✗ Status update cancelled")
        sys.exit(0)
    
    write_status(status_data)
    
    print("\nStatus successfully updated!")
    print(f"Current status: {status.upper()}")
    
    if message:
        print(f"Message: {message}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n✗ Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)
