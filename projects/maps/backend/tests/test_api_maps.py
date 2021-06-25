from faker import Faker
from pathlib import Path
from flask.wrappers import Response
from restapi.tests import API_URI, BaseTests, FlaskClient
from maps.endpoints.config import (
    AREAS,
    ENVS,
    FIELDS,
    LEVELS_PE,
    LEVELS_PR,
    PLATFORMS,
    RESOLUTIONS,
    RUNS,
    MEDIA_ROOT
)
from restapi.utilities.logs import log

class TestApp(BaseTests):
    def test_api_maps(self, client: FlaskClient, faker: Faker) -> None:

        # GENERAL COSMO CASE
        # define the different variables - use the lists used by marshmallow to validate the inputs
        map_offset = "0006"
        run = RUNS[0]
        res = RESOLUTIONS[0]
        area = AREAS[0]
        for i in FIELDS:
            if i != "percentile" or i != "probability": # discard the iff fields
                field = i
                break
        platform = PLATFORMS[0]
        env = ENVS[0]
        cosmo_map_dir = f"Magics-{run}-{res}.web"
        cosmo_map_path = Path(MEDIA_ROOT,platform,env,cosmo_map_dir,area)
        reftime = faker.pyint(1000000000, 9999999999)
        # create the base directory for the maps
        cosmo_map_path.mkdir(parents=True, exist_ok=True)
        # create the directory for the field
        cosmo_field_dir = Path(cosmo_map_path,field)
        cosmo_field_dir.mkdir(parents=True, exist_ok=True)
        # create a fake map file
        fcontent = faker.paragraph()
        cosmo_mapfile_path = Path(cosmo_field_dir,f"{field}.{reftime}.{map_offset}.png")
        with open(cosmo_mapfile_path, "w") as f:
            f.write(fcontent)

        # get a map which is not ready yet
        endpoint = API_URI + f"/maps/offset/{map_offset}?field={field}&run={run}&res={res}&area={area}&platform={platform}&env={env}"
        r = client.get(endpoint)
        assert r.status_code == 404
        not_ready_msg = self.get_content(r)

        # create a ready file
        cosmo_readyfile_path = Path(cosmo_map_path, f"{reftime}.READY")
        open(cosmo_readyfile_path, 'a').close()

        # get a map that does not exists
        endpoint = API_URI + f"/maps/offset/{faker.pyint(1000, 9999)}?field={field}&run={run}&res={res}&area={area}&platform={platform}&env={env}"
        r = client.get(endpoint)
        assert r.status_code == 404
        not_found_msg = self.get_content(r)

        #compare the different 404 messages
        assert not_ready_msg != not_found_msg

        # get a map file
        endpoint = API_URI + f"/maps/offset/{map_offset}?field={field}&run={run}&res={res}&area={area}&platform={platform}&env={env}"
        r = client.get(endpoint)
        assert r.status_code == 200
        retrieved_map_content = r.data.decode("utf-8")

        # check if the retrieved file is the same created (and if it's complete)
        assert retrieved_map_content == fcontent

        # PERCENTILE CASE
        field = "percentile"
        level_pe = LEVELS_PE[0]

        iff_map_dir = f"PROB-{run}-iff.web"
        iff_map_path = Path(MEDIA_ROOT, platform, env, iff_map_dir, area)
        # create the directory for the field
        perc_field_dir = Path(iff_map_path, field)
        perc_field_dir.mkdir(parents=True, exist_ok=True)
        # create a fake percentile map file
        fcontent = faker.paragraph()
        perc_mapfile_path = Path(perc_field_dir, f"perc6.{reftime}.{map_offset}_{level_pe}.png")
        print("*** ", perc_mapfile_path)
        with open(perc_mapfile_path, "w") as f:
            print("writing in ", perc_mapfile_path)
            f.write(fcontent)

        # get a map which is not ready yet
        endpoint = API_URI + f"/maps/offset/{map_offset}?field={field}&run={run}&res={res}&area={area}&platform={platform}&env={env}&level_pe={level_pe}"
        r = client.get(endpoint)
        assert r.status_code == 404
        iff_not_ready_msg = self.get_content(r)

        assert iff_not_ready_msg == not_ready_msg

        # create a iff ready file
        iff_readyfile_path = Path(iff_map_path, f"{reftime}.READY")
        open(iff_readyfile_path, 'a').close()

        # get a percentile map file
        endpoint = API_URI + f"/maps/offset/{map_offset}?field={field}&run={run}&res={res}&area={area}&platform={platform}&env={env}&level_pe={level_pe}"
        r = client.get(endpoint)
        assert r.status_code == 200
        retrieved_map_content = r.data.decode("utf-8")

        # check if the retrieved file is the same created (and if it's complete)
        assert retrieved_map_content == fcontent

        # PROBABILITY CASE
        field = "probability"
        level_pr = LEVELS_PR[0]

        # create the directory for the field
        perc_field_dir = Path(iff_map_path, field)
        perc_field_dir.mkdir(parents=True, exist_ok=True)
        # create a fake probability map file
        fcontent = faker.paragraph()
        prob_mapfile_path = Path(perc_field_dir, f"prob6.{reftime}.{map_offset}_{level_pr}.png")
        with open(prob_mapfile_path, "w") as f:
            f.write(fcontent)

        # get a percentile map file
        endpoint = API_URI + f"/maps/offset/{map_offset}?field={field}&run={run}&res={res}&area={area}&platform={platform}&env={env}&level_pr={level_pr}"
        r = client.get(endpoint)
        assert r.status_code == 200
        retrieved_map_content = r.data.decode("utf-8")

        # check if the retrieved file is the same created (and if it's complete)
        assert retrieved_map_content == fcontent


        #delete all the files used for the tests
        Path.unlink(cosmo_readyfile_path)
        Path.unlink(cosmo_mapfile_path)
        Path.unlink(iff_readyfile_path)
        Path.unlink(perc_mapfile_path)
        Path.unlink(prob_mapfile_path)
