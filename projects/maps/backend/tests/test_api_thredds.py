from maps.endpoints import thredds as thredds_endpoints
from restapi.tests import API_URI, BaseTests, FlaskClient


class TestThreddsEndpoints(BaseTests):
    def test_api_thredds_latest_products(self, client: FlaskClient, tmp_path, monkeypatch) -> None:
        mer_root = tmp_path / "MER"
        thredds_root = tmp_path / "thredds_ugrid"

        arpae_root = mer_root / "water-level-arpae"
        dpc_root = mer_root / "water-level-dpc"
        arpae_source = arpae_root / "files"
        dpc_source = dpc_root / "files"
        arpae_source.mkdir(parents=True, exist_ok=True)
        dpc_source.mkdir(parents=True, exist_ok=True)

        # ARPAE is fully ingested in THREDDS.
        (arpae_root / "20260507.READY").write_text("", encoding="utf-8")
        (arpae_source / "20260507.nc").write_text("arpae", encoding="utf-8")
        (arpae_root / "20260507.THREDDS.READY").write_text("", encoding="utf-8")

        arpae_target = thredds_root / "MER" / "water-level-arpae"
        arpae_target.mkdir(parents=True, exist_ok=True)
        (arpae_target / "20260507.nc").write_text("arpae", encoding="utf-8")
        (arpae_target / "INGESTION.META").write_text(
            "IngestedAt: 2026-05-07T10:00:00\n"
            "Source: MER/water-level-arpae\n"
            "CopiedFile: 20260507.nc\n"
            "DeletedFiles: 0\n",
            encoding="utf-8",
        )

        # DPC has newer source data not yet confirmed by THREDDS marker.
        (dpc_root / "20260508.READY").write_text("", encoding="utf-8")
        (dpc_source / "20260508.nc").write_text("dpc", encoding="utf-8")
        (dpc_root / "20260507.THREDDS.READY").write_text("", encoding="utf-8")

        monkeypatch.setattr(thredds_endpoints, "MER_BASE_PATH", mer_root)
        monkeypatch.setattr(thredds_endpoints, "THREDDS_TARGET_PATH", thredds_root)

        response = client.get(f"{API_URI}/thredds/latest")
        assert response.status_code == 200

        payload = self.get_content(response)
        products = {item["product"]: item for item in payload["products"]}

        assert "arpae/water-level" in products
        assert "dpc/water-level" in products

        arpae_payload = products["arpae/water-level"]
        assert arpae_payload["ingestion"]["status"] == "ingested"
        assert arpae_payload["ingestion"]["latestIngestedFiles"] == ["20260507.nc"]
        assert arpae_payload["ingestion"]["lastThreddsReady"] == "20260507"

        dpc_payload = products["dpc/water-level"]
        assert dpc_payload["ingestion"]["status"] == "ingesting"
        assert dpc_payload["ingestion"]["latestIngestedFiles"] == []
        assert dpc_payload["ingestion"]["lastSourceReady"] == "20260508"

        single_product = client.get(f"{API_URI}/thredds/arpae/water-level/latest")
        assert single_product.status_code == 200
        assert self.get_content(single_product)["product"] == "arpae/water-level"

        unknown_product = client.get(f"{API_URI}/thredds/unknown/water-level/latest")
        assert unknown_product.status_code == 404
