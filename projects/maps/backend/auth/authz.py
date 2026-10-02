"""
Simple authz decorator for restricting API access
"""

import re
from functools import wraps
from ipaddress import ip_address, ip_network

from flask import request
from restapi.env import Env
from restapi.exceptions import Forbidden


def check_ip_access(func):
    """Restrict access to IPs/CIDRs in the shared maintenance allowlist."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        allowlist = Env.get("MAINTENANCE_ALLOWLIST", "")
        try:
            networks = [
                ip_network(entry, strict=False)
                for entry in re.split(r"[\s,]+", allowlist.strip())
                if entry
            ]
            address = ip_address(request.remote_addr or "")
        except ValueError:
            raise Forbidden("Access Forbidden", is_warning=True) from None
        if not any(address in network for network in networks):
            raise Forbidden("Access Forbidden", is_warning=True)
        return func(*args, **kwargs)

    return wrapper
