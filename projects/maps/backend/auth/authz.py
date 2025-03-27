"""
Simple authz decorator for restricting API access
"""

from functools import wraps

from flask import request
from restapi.exceptions import Forbidden
from restapi.utilities.logs import log


def check_ip_access(allowed_ips):
    def decorator(func):
        @wraps(func)
        def wrapper(requester_ip, *args, **kwargs):
            log.debug(request.remote_addr)
            log.debug(allowed_ips)
            if request.remote_addr not in allowed_ips:
                raise Forbidden("Access Forbidden", is_warning=True)
            return func(requester_ip, *args, **kwargs)

        return wrapper

    return decorator
