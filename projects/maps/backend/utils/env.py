import os
from functools import lru_cache
from typing import Optional, Set, Union

from restapi.env import Env


class Env(Env):
    @staticmethod
    @lru_cache
    def get_set(var_name: str, default: Optional[Set[str]] = None) -> Set[str]:
        if default is None:
            default = set()
        value = os.getenv(var_name)
        if value is None:
            os.environ[var_name] = ",".join(default)
            return default
        return set(value.split(","))
