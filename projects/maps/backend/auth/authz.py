"""
Simple authz decorator for restricting API access
"""
from functools import wraps
from flask import request
from restapi.rest.definition import EndpointResource

def check_ip_access(allowed_ips):
    def decorator(func):
        @wraps(func)
        def wrapper(requester_ip, *args, **kwargs):
            print(request.remote_addr)
            print(allowed_ips)
            if request.remote_addr not in allowed_ips:
                return EndpointResource.response("Forbidden", code=403)
            return func(requester_ip, *args, **kwargs)

        return wrapper

    return decorator
