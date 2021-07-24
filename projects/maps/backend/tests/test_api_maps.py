import datetime
from pathlib import Path

from faker import Faker
from maps.endpoints.config import (
    AREAS,
    DEFAULT_PLATFORM,
    ENVS,
    FIELDS,
    LEVELS_PE,
    LEVELS_PR,
    MEDIA_ROOT,
    PLATFORMS,
    RESOLUTIONS,
    RUNS,
)
from restapi.tests import API_URI, BaseTests, FlaskClient


class TestApp(BaseTests):
    def test_api_maps(self, client: FlaskClient, faker: Faker) -> None:

        # GENERAL COSMO CASE
        # define the different variables - use the lists used by marshmallow to validate the inputs
        map_offset = "0006"
        run = RUNS[0]
        res = RESOLUTIONS[0]
        area = AREAS[0]
        for i in FIELDS:
            if i != "percentile" or i != "probability":  # discard the iff fields
                field = i
                break
        platform = DEFAULT_PLATFORM
        env = ENVS[0]
        # test case where any platform is unavailable
        ready_endpoint = (
            API_URI
            + f"/maps/ready?field={field}&run={run}&res={res}&area={area}&env={env}"
        )
        r = client.get(ready_endpoint)
        assert r.status_code == 503
        service_down_msg = self.get_content(r)

        # create filesystem
        cosmo_map_dir = f"Magics-{run}-{res}.web"
        cosmo_map_path = Path(MEDIA_ROOT, platform, env, cosmo_map_dir, area)
        reftime_dt = faker.date_time()
        reftime = reftime_dt.strftime("%Y%m%d%H")
        # create the base directory for the maps
        cosmo_map_path.mkdir(parents=True, exist_ok=True)
        # create the directory for the field
        cosmo_field_dir = Path(cosmo_map_path, field)
        cosmo_field_dir.mkdir(parents=True, exist_ok=True)
        # create a fake map file
        fcontent = faker.paragraph()
        cosmo_mapfile_path = Path(
            cosmo_field_dir, f"{field}.{reftime}.{map_offset}.png"
        )
        with open(cosmo_mapfile_path, "w") as f:
            f.write(fcontent)

        # get a map which is not ready yet
        endpoint = (
            API_URI
            + f"/maps/offset/{map_offset}?field={field}&run={run}&res={res}&area={area}&platform={platform}&env={env}"
        )
        r = client.get(endpoint)
        assert r.status_code == 404
        not_ready_msg = self.get_content(r)

        # create a ready file
        cosmo_readyfile_path = Path(cosmo_map_path, f"{reftime}.READY")
        open(cosmo_readyfile_path, "a").close()

        # TEST API FOR CHECK MAPS READINESS
        # test an unavailable platform
        for p in PLATFORMS:
            if p != DEFAULT_PLATFORM:
                no_avail_platform = p
        ready_endpoint = (
            API_URI
            + f"/maps/ready?field={field}&run={run}&res={res}&area={area}&platform={no_avail_platform}&env={env}"
        )
        r = client.get(ready_endpoint)
        assert r.status_code == 503
        assert self.get_content(r) != service_down_msg

        # test an available platform
        ready_endpoint = (
            API_URI
            + f"/maps/ready?field={field}&run={run}&res={res}&area={area}&platform={platform}&env={env}"
        )
        r = client.get(ready_endpoint)
        assert r.status_code == 200
        ready_res = self.get_content(r)
        assert isinstance(ready_res, dict)
        assert ready_res["reftime"] == str(reftime)
        assert len(ready_res["offsets"]) == 1 and ready_res["offsets"][0] == map_offset
        assert ready_res["platform"] == platform

        # not specifying a platform with one platform not available
        ready_endpoint = (
            API_URI
            + f"/maps/ready?field={field}&run={run}&res={res}&area={area}&env={env}"
        )
        r = client.get(ready_endpoint)
        assert r.status_code == 200
        ready_res = self.get_content(r)
        assert isinstance(ready_res, dict)
        assert ready_res["platform"] == platform

        # not specify a platform with both the platform available
        # create the filesystem for the other platform
        cosmo_alt_map_path = Path(
            MEDIA_ROOT, no_avail_platform, env, cosmo_map_dir, area
        )
        latest_reftime_dt = reftime_dt + datetime.timedelta(days=1)
        alt_reftime = latest_reftime_dt.strftime("%Y%m%d%H")
        # create the base directory for the maps
        cosmo_alt_map_path.mkdir(parents=True, exist_ok=True)
        # create the directory for the field
        cosmo_alt_field_dir = Path(cosmo_alt_map_path, field)
        cosmo_alt_field_dir.mkdir(parents=True, exist_ok=True)
        # create a fake map file
        cosmo_alt_mapfile_path = Path(
            cosmo_alt_field_dir, f"{field}.{reftime}.{map_offset}.png"
        )
        open(cosmo_alt_mapfile_path, "a").close()

        # create a ready file
        cosmo_alt_readyfile_path = Path(cosmo_alt_map_path, f"{alt_reftime}.READY")
        open(cosmo_alt_readyfile_path, "a").close()

        r = client.get(ready_endpoint)
        assert r.status_code == 200
        ready_res = self.get_content(r)
        assert isinstance(ready_res, dict)
        assert ready_res["platform"] == no_avail_platform

        # get a map that does not exists
        endpoint = (
            API_URI
            + f"/maps/offset/{faker.pyint(1000, 9999)}?field={field}&run={run}&res={res}&area={area}&platform={platform}&env={env}"
        )
        r = client.get(endpoint)
        assert r.status_code == 404
        not_found_msg = self.get_content(r)

        # compare the different 404 messages
        assert not_ready_msg != not_found_msg

        # get a map file
        endpoint = (
            API_URI
            + f"/maps/offset/{map_offset}?field={field}&run={run}&res={res}&area={area}&platform={platform}&env={env}"
        )
        r = client.get(endpoint)
        assert r.status_code == 200
        retrieved_map_content = r.data.decode("utf-8")

        # check if the retrieved file is the same created (and if it's complete)
        assert retrieved_map_content == fcontent

        # TEST LEGEND RETRIEVING
        # legend file does not exists
        leg_endpoint = (
            API_URI
            + f"/maps/legend?field={field}&run={run}&res={res}&area={area}&platform={platform}&env={env}"
        )
        r = client.get(leg_endpoint)
        assert r.status_code == 404

        # create a legend file
        cosmo_legend_dir = Path(cosmo_map_path.parent, "legends")
        cosmo_legend_dir.mkdir(parents=True, exist_ok=True)
        # create a fake cosmo legend file
        fcontent = faker.paragraph()
        cosmo_legend_path = Path(cosmo_legend_dir, f"{field}.png")
        with open(cosmo_legend_path, "w") as f:
            f.write(fcontent)

        # get the legend
        r = client.get(leg_endpoint)
        assert r.status_code == 200
        retrieved_legend_content = r.data.decode("utf-8")

        # check if the retrieved file is the same created (and if it's complete)
        assert retrieved_legend_content == fcontent

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
        perc_mapfile_path = Path(
            perc_field_dir, f"perc6.{reftime}.{map_offset}_{level_pe}.png"
        )
        with open(perc_mapfile_path, "w") as f:
            f.write(fcontent)

        # get a map which is not ready yet
        endpoint = (
            API_URI
            + f"/maps/offset/{map_offset}?field={field}&run={run}&res={res}&area={area}&platform={platform}&env={env}&level_pe={level_pe}"
        )
        r = client.get(endpoint)
        assert r.status_code == 404
        iff_not_ready_msg = self.get_content(r)

        assert iff_not_ready_msg == not_ready_msg

        # create a iff ready file
        iff_readyfile_path = Path(iff_map_path, f"{reftime}.READY")
        open(iff_readyfile_path, "a").close()

        # test ready endpoint for percentile use case
        perc_ready_endpoint = (
            API_URI
            + f"/maps/ready?field={field}&run={run}&res={res}&area={area}&platform={platform}&env={env}&level_pe={level_pe}"
        )
        r = client.get(perc_ready_endpoint)
        assert r.status_code == 200
        ready_res = self.get_content(r)
        assert isinstance(ready_res, dict)
        assert ready_res["reftime"] == str(reftime)
        assert len(ready_res["offsets"]) == 1 and ready_res["offsets"][0] == map_offset
        assert ready_res["platform"] == platform

        # get a percentile map file
        endpoint = (
            API_URI
            + f"/maps/offset/{map_offset}?field={field}&run={run}&res={res}&area={area}&platform={platform}&env={env}&level_pe={level_pe}"
        )
        r = client.get(endpoint)
        assert r.status_code == 200
        retrieved_map_content = r.data.decode("utf-8")

        # check if the retrieved file is the same created (and if it's complete)
        assert retrieved_map_content == fcontent

        # TEST LEGENDS
        # create a legend file
        iff_legend_dir = Path(iff_map_path.parent, "legends")
        iff_legend_dir.mkdir(parents=True, exist_ok=True)
        # create a fake percentile legend file
        fcontent = faker.paragraph()
        perc_legend_path = Path(iff_legend_dir, "perc6.png")
        with open(perc_legend_path, "w") as f:
            f.write(fcontent)

        # get the legend
        leg_endpoint = (
            API_URI
            + f"/maps/legend?field={field}&run={run}&res={res}&area={area}&platform={platform}&env={env}&level_pe={level_pe}"
        )
        r = client.get(leg_endpoint)
        assert r.status_code == 200
        retrieved_legend_content = r.data.decode("utf-8")

        # check if the retrieved file is the same created (and if it's complete)
        assert retrieved_legend_content == fcontent

        # PROBABILITY CASE
        field = "probability"
        level_pr = LEVELS_PR[0]

        # create the directory for the field
        perc_field_dir = Path(iff_map_path, field)
        perc_field_dir.mkdir(parents=True, exist_ok=True)
        # create a fake probability map file
        fcontent = faker.paragraph()
        prob_mapfile_path = Path(
            perc_field_dir, f"prob6.{reftime}.{map_offset}_{level_pr}.png"
        )
        with open(prob_mapfile_path, "w") as f:
            f.write(fcontent)

        # test ready endpoint for probability use case
        prob_ready_endpoint = (
            API_URI
            + f"/maps/ready?field={field}&run={run}&res={res}&area={area}&platform={platform}&env={env}&level_pr={level_pr}"
        )
        r = client.get(prob_ready_endpoint)
        assert r.status_code == 200
        ready_res = self.get_content(r)
        assert isinstance(ready_res, dict)
        assert ready_res["reftime"] == str(reftime)
        assert len(ready_res["offsets"]) == 1 and ready_res["offsets"][0] == map_offset
        assert ready_res["platform"] == platform

        # get a probability map file
        endpoint = (
            API_URI
            + f"/maps/offset/{map_offset}?field={field}&run={run}&res={res}&area={area}&platform={platform}&env={env}&level_pr={level_pr}"
        )
        r = client.get(endpoint)
        assert r.status_code == 200
        retrieved_map_content = r.data.decode("utf-8")

        # check if the retrieved file is the same created (and if it's complete)
        assert retrieved_map_content == fcontent

        # create a fake probability legend file
        fcontent = faker.paragraph()
        prob_legend_path = Path(iff_legend_dir, "prob6.png")
        with open(prob_legend_path, "w") as f:
            f.write(fcontent)

        # get the legend
        leg_endpoint = (
            API_URI
            + f"/maps/legend?field={field}&run={run}&res={res}&area={area}&platform={platform}&env={env}&level_pr={level_pr}"
        )
        r = client.get(leg_endpoint)
        assert r.status_code == 200
        retrieved_legend_content = r.data.decode("utf-8")

        # check if the retrieved file is the same created (and if it's complete)
        assert retrieved_legend_content == fcontent

        # delete all the files used for the tests
        Path.unlink(cosmo_readyfile_path)
        Path.unlink(cosmo_alt_readyfile_path)
        Path.unlink(cosmo_mapfile_path)
        Path.unlink(cosmo_alt_mapfile_path)
        Path.unlink(cosmo_legend_path)
        Path.unlink(iff_readyfile_path)
        Path.unlink(perc_mapfile_path)
        Path.unlink(perc_legend_path)
        Path.unlink(prob_mapfile_path)
        Path.unlink(prob_legend_path)
