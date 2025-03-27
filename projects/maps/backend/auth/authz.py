"""
Simple authz decorator for restricting API access
"""
from functools import wraps


def check_ip_access(allowed_ips):
    def decorator(func):
        @wraps(func)
        def wrapper(requester_ip, *args, **kwargs):
            if requester_ip not in allowed_ips:
                return "Access Denied: Unauthorized IP"
            return func(requester_ip, *args, **kwargs)

        return wrapper

    return decorator
