from pathlib import Path

from faker import Faker
from maps.endpoints.config import DATASETS, DEFAULT_PLATFORM, MEDIA_ROOT, RUNS
from restapi.tests import API_URI, BaseTests, FlaskClient


class TestApp(BaseTests):
    def test_api_tiles(self, client: FlaskClient, faker: Faker) -> None:

        dataset = list(DATASETS.keys())[0]
        run = RUNS[0]
        platform = DEFAULT_PLATFORM
        area = DATASETS[dataset]["area"]

        # case of a dataset without metadata
        DATASETS["fake_dataset"] = {}  # type:ignore
        r = client.get(f"{API_URI}/tiles?dataset=fake_dataset")
        assert r.status_code == 404
        no_metadata_msg = self.get_content(r)

        # dataset without area
        DATASETS["fake_dataset"]["step"] = 1
        r = client.get(f"{API_URI}/tiles?dataset=fake_dataset")
        assert r.status_code == 404
        no_area_msg = self.get_content(r)
        assert no_metadata_msg != no_area_msg

        # no run specified any maps is ready
        tiles_dir = f"Tiles-{run}-{dataset}.web"
        tiles_path = Path(MEDIA_ROOT, platform, "PROD", tiles_dir, area)
        tiles_path.mkdir(parents=True, exist_ok=True)
        r = client.get(f"{API_URI}/tiles?dataset={dataset}")
        assert r.status_code == 404
        not_ready_msg = self.get_content(r)
        assert no_metadata_msg != not_ready_msg

        # no run specified but map is ready
        # create a ready file
        reftime = faker.pyint(1000000000, 9999999999)
        tiles_readyfile_path = Path(tiles_path, f"{reftime}.READY")
        open(tiles_readyfile_path, "a").close()
        r = client.get(f"{API_URI}/tiles?dataset={dataset}")
        assert r.status_code == 200
        # check response
        tiles_metadata = self.get_content(r)
        assert isinstance(tiles_metadata, dict)
        assert tiles_metadata["area"] == area
        assert tiles_metadata["reftime"] == str(reftime)

        # specify the run
        r = client.get(f"{API_URI}/tiles?dataset={dataset}&run={run}")
        assert r.status_code == 200
        # check the response is the same
        assert self.get_content(r) == tiles_metadata

        # delete the files used for the test
        Path.unlink(tiles_readyfile_path)
