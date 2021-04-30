import os
from functools import lru_cache
from typing import Dict, Tuple, TypedDict

from restapi.exceptions import NotFound
from restapi.utilities.logs import log


@lru_cache
def get_base_path(field: str, platform: str, env: str, run: str, dataset: str) -> str:
    # flood fields have a different path
    if field == "percentile" or field == "probability":
        dataset = "iff"
        prefix = "PROB"
    elif field == "tiles":
        prefix = "Tiles"
    else:
        prefix = "Magics"

    folder = f"{prefix}-{run}-{dataset}.web"

    base_path = os.path.join(
        MEDIA_ROOT,
        platform,
        env,
        folder,
    )
    log.debug(f"base_path: {base_path}")
    return base_path


def get_ready_file(base_path: str, area: str) -> str:
    ready_path = os.path.join(base_path, area)
    log.debug(f"ready_path: {ready_path}")

    ready_files = []
    if os.path.exists(ready_path):
        ready_files = [
            f
            for f in os.listdir(ready_path)
            if os.path.isfile(os.path.join(ready_path, f)) and ".READY" in f
        ]

    # Check if .READY file exists (if not, images are not ready yet)
    log.debug(f"Looking for .READY files in: {ready_path}")
    if not ready_files:
        raise NotFound("no .READY files found")

    log.debug(f".READY files found: {ready_files}")
    return ready_files[0]


def check_platform_availability(platform: str) -> bool:
    return os.access(os.path.join(MEDIA_ROOT, platform), os.X_OK)


MEDIA_ROOT = "/meteo/"

RUNS = ["00", "12"]
RESOLUTIONS = ["lm2.2", "lm5"]
FIELDS = [
    "prec1",
    "prec3",
    "prec6",
    "prec12",
    "prec24",
    "t2m",
    "wind",
    "cloud",
    "pressure",
    "cloud_hml",
    "humidity",
    "snow3",
    "snow6",
    "percentile",
    "probability",
]
LEVELS_PE = ["1", "10", "25", "50", "70", "75", "80", "90", "95", "99"]
LEVELS_PR = ["5", "10", "20", "50"]
AREAS = ["Italia", "Nord_Italia", "Centro_Italia", "Sud_Italia", "Area_Mediterranea"]
PLATFORMS = ["GALILEO", "MEUCCI"]
ENVS = ["PROD", "DEV"]
DEFAULT_PLATFORM = os.environ.get("PLATFORM", "GALILEO")


class Boundaries(TypedDict):
    SW: Tuple[int, int]
    NE: Tuple[int, int]


class DatasetType(TypedDict):
    area: str
    start_offset: int
    end_offset: int
    step: int
    boundaries: Boundaries


DATASETS: Dict[str, DatasetType] = {
    "lm5": {
        "area": "Area_Mediterranea",
        "start_offset": 0,
        "end_offset": 72,
        "step": 1,
        "boundaries": {
            "SW": (
                25.8,
                -30.9,
            ),
            "NE": (
                55.5,
                47.0,
            ),
        },
    },
    "lm2.2": {
        "area": "Italia",
        "start_offset": 0,
        "end_offset": 48,
        "step": 1,
        "boundaries": {
            "SW": (
                34.5,
                5.0,
            ),
            "NE": (
                48.0,
                21.2,
            ),
        },
    },
    "iff": {
        "area": "Italia",
        "start_offset": 6,
        "end_offset": 72,
        "step": 3,
        "boundaries": {
            "SW": (
                34.5,
                5.0,
            ),
            "NE": (
                48.0,
                21.2,
            ),
        },
    },
}
