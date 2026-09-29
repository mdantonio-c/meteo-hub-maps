#!/usr/bin/env python3
"""
Example script for using the MeteoHub Maps Status API.

This script demonstrates how to:
1. Check current system status
2. Set maintenance windows
3. Clear status (return to operational)

Usage:
    python status_api_example.py get
    python status_api_example.py set maintenance "Scheduled maintenance"
    python status_api_example.py clear
"""

import json
import sys
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

BASE_URL = "http://localhost:8080/api"


def get_status():
    """Retrieve current system status."""
    try:
        req = Request(f"{BASE_URL}/status")
        with urlopen(req) as response:
            data = json.loads(response.read().decode())
            return data
    except HTTPError as e:
        print(f"HTTP Error: {e.code} - {e.reason}")
        sys.exit(1)
    except URLError as e:
        print(f"URL Error: {e.reason}")
        sys.exit(1)


def set_status(status, message=None, affected_services=None, duration_hours=2):
    """
    Update system status.
    
    Args:
        status: One of 'operational', 'maintenance', 'degraded', 'outage'
        message: Human-readable description
        affected_services: List of affected service names
        duration_hours: Duration of maintenance in hours
    """
    now = datetime.utcnow()
    scheduled_start = now + timedelta(hours=1)
    scheduled_end = scheduled_start + timedelta(hours=duration_hours)
    
    payload = {
        "status": status,
        "message": message,
        "scheduled_start": scheduled_start.isoformat() + "Z",
        "scheduled_end": scheduled_end.isoformat() + "Z",
        "affected_services": affected_services or [],
    }
    
    # Remove None values
    payload = {k: v for k, v in payload.items() if v is not None and v != []}
    
    try:
        data = json.dumps(payload).encode('utf-8')
        req = Request(
            f"{BASE_URL}/status",
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        
        with urlopen(req) as response:
            result = json.loads(response.read().decode())
            return result
    except HTTPError as e:
        print(f"HTTP Error: {e.code} - {e.reason}")
        error_body = e.read().decode()
        print(f"Error details: {error_body}")
        sys.exit(1)
    except URLError as e:
        print(f"URL Error: {e.reason}")
        sys.exit(1)


def clear_status():
    """Clear status and return to operational."""
    return set_status("operational")


def print_status(status_data):
    """Pretty print status data."""
    print("\n" + "="*60)
    print("SYSTEM STATUS")
    print("="*60)
    print(f"Status: {status_data.get('status', 'unknown').upper()}")
    
    if status_data.get('message'):
        print(f"Message: {status_data['message']}")
    
    if status_data.get('scheduled_start'):
        print(f"Scheduled Start: {status_data['scheduled_start']}")
    
    if status_data.get('scheduled_end'):
        print(f"Scheduled End: {status_data['scheduled_end']}")
    
    if status_data.get('affected_services'):
        services = ', '.join(status_data['affected_services'])
        print(f"Affected Services: {services}")
    
    print(f"Last Updated: {status_data.get('updated_at', 'N/A')}")
    print("="*60 + "\n")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "get":
        status = get_status()
        print_status(status)
    
    elif command == "set":
        if len(sys.argv) < 3:
            print("Error: Status value required")
            print("Usage: python status_api_example.py set <status> [message]")
            sys.exit(1)
        
        status_value = sys.argv[2]
        message = sys.argv[3] if len(sys.argv) > 3 else None
        
        valid_statuses = ["operational", "maintenance", "degraded", "outage"]
        if status_value not in valid_statuses:
            print(f"Error: Invalid status. Must be one of: {', '.join(valid_statuses)}")
            sys.exit(1)
        
        result = set_status(status_value, message)
        print(f"\nStatus updated successfully!")
        print_status(result.get('status', {}))
    
    elif command == "clear":
        result = clear_status()
        print("\nStatus cleared - system returned to operational")
        print_status(result.get('status', {}))
    
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
