import calendar
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple, TypedDict

from restapi.config import DATA_PATH
from restapi.env import Env
from restapi.utilities.logs import log

RUNS = ["00", "12"]
RESOLUTIONS = ["lm2.2", "lm5", "WRF_OL", "WRF_DA_ITA", "icon"]
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
    "snow1",
    "snow3",
    "snow6",
    "snow12",
    "snow24",
    "percentile",
    "probability",
]
LEVELS_PE = ["1", "10", "25", "50", "70", "75", "80", "90", "95", "99"]
LEVELS_PR = ["5", "10", "20", "50"]
AREAS = ["Italia", "Nord_Italia", "Centro_Italia", "Sud_Italia", "Area_Mediterranea"]
PLATFORMS = ["G100", "leonardo"]
ENVS = ["PROD", "DEV"]
DEFAULT_PLATFORM = Env.get("PLATFORM", "G100")
WEEKDAYS = ["0", "1", "2", "3", "4", "5", "6"]


class Boundaries(TypedDict):
    SW: Tuple[float, float]
    NE: Tuple[float, float]


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


@lru_cache
def get_base_path(
    field: str,
    platform: str,
    env: str,
    run: str,
    dataset: str,
    weekday: Optional[str] = None,
) -> Path:
    # flood fields have a different path
    if field == "percentile" or field == "probability":
        dataset = "iff"
        prefix = "PROB"
    elif field == "tiles":
        prefix = "Tiles"
    else:
        prefix = "Magics"

    # weekday is transformed into a weekday_name to be integrated in the base_path.
    if weekday is not None:
        weekday = int(weekday)
        # The *.READY files of PROB-12* folders are actually inside the folders
        # with names corresponding to weekday-1 dates.
        if prefix == "PROB" and run == "12":
            weekday = int(WEEKDAYS[weekday - 1])
        weekday_name = calendar.day_name[weekday]
        if dataset == 'icon':
            dataset = "ICON_2I_all2km"
        folder = f"{prefix}-{run}-{dataset}.{weekday_name}.web"
    else:
        if dataset == 'icon':
            dataset = "ICON_2I_all2km"
        folder = f"{prefix}-{run}-{dataset}.web"


    base_path = DATA_PATH.joinpath(
        platform,
        env,
        folder,
    )
    log.debug(f"base_path: {base_path}")
    log.info(f"base_path: {base_path}")
    return base_path


def get_ready_file(base_path: Path, area: str) -> Optional[Path]:
    ready_path = base_path.joinpath(area)
    log.debug(f"ready_path: {ready_path}")

    ready_files: List[Path] = []
    if ready_path.exists():
        ready_files = [
            f for f in ready_path.iterdir() if f.is_file() and ".READY" in f.name
        ]

    # Check if .READY file exists (if not, images are not ready yet)
    log.debug(f"Looking for .READY files in: {ready_path}")
    if not ready_files:
        return None

    log.debug(f".READY files found: {ready_files}")
    return ready_files[0]


def check_platform_availability(platform: str) -> bool:
    return DATA_PATH.joinpath(platform).exists()
