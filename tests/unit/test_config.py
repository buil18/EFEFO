from __future__ import annotations

import shutil

import pytest

from efefo.cli import main as cli_main
from efefo.config import SITES_DIR, ConfigError, load_site


def copy_sites(tmp_path):
    target = tmp_path / "sites"
    shutil.copytree(SITES_DIR, target)
    return target


def test_hm_site_matches_legacy_constants(site):
    assert site.sap.base_url == "https://my420157.s4hana.cloud.sap"
    assert site.sap.client == "100"
    assert site.location.strip_prefixes == ("HMPKG", "PKG", "HM")
    assert site.location.display_exclude_prefixes == ("K", "H")
    assert site.location.display_exclude_keywords == ("LOOSE",)
    assert site.fefo.lot_split_days == 7
    assert site.fefo.display_max_slots == 6
    assert site.fefo.min_quantity == 100
    assert site.audit.qty_delta_threshold == 100
    assert site.audit.confirm_runs == 2
    assert len(site.location.empty_location_exclusions) == 13


def test_template_site_loads():
    assert load_site("_template").site.code == "xx"


def test_unknown_site_lists_available(tmp_path):
    with pytest.raises(ConfigError, match="hm"):
        load_site("nope")


def test_missing_key_rejected(tmp_path):
    sites = copy_sites(tmp_path)
    text = (sites / "hm.toml").read_text(encoding="utf-8").replace("lot_split_days = 7\n", "")
    (sites / "hm.toml").write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match="lot_split_days"):
        load_site("hm", sites)


def test_unknown_key_rejected(tmp_path):
    sites = copy_sites(tmp_path)
    text = (sites / "hm.toml").read_text(encoding="utf-8").replace("[fefo]\n", "[fefo]\nlot_split_dayz = 3\n")
    (sites / "hm.toml").write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match="lot_split_dayz"):
        load_site("hm", sites)


def test_wrong_type_rejected(tmp_path):
    sites = copy_sites(tmp_path)
    text = (sites / "hm.toml").read_text(encoding="utf-8").replace("lot_split_days = 7", 'lot_split_days = "7"')
    (sites / "hm.toml").write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match="số nguyên"):
        load_site("hm", sites)


def test_threshold_order_validated(tmp_path):
    sites = copy_sites(tmp_path)
    text = (sites / "hm.toml").read_text(encoding="utf-8").replace("emart_below = 69", "emart_below = 99")
    (sites / "hm.toml").write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match="tăng dần"):
        load_site("hm", sites)


def test_local_override_merges(tmp_path):
    sites = copy_sites(tmp_path)
    (sites / "hm.local.toml").write_text('[publish]\nsecret = "abc"\n[fefo]\nlot_split_days = 3\n', encoding="utf-8")
    site = load_site("hm", sites)
    assert site.publish.secret == "abc"
    assert site.fefo.lot_split_days == 3
    assert site.fefo.display_max_slots == 6
    assert site.fefo.min_quantity == 100


def test_new_site_command(tmp_path, monkeypatch):
    sites = copy_sites(tmp_path)
    monkeypatch.setattr("efefo.cli.SITES_DIR", sites)
    monkeypatch.setattr("efefo.config.SITES_DIR", sites)
    monkeypatch.setattr("efefo.cli.site_file", lambda code: sites / f"{code}.toml")
    monkeypatch.setattr("efefo.cli.local_site_file", lambda code: sites / f"{code}.local.toml")
    assert cli_main(["new-site", "dn"]) == 0
    assert 'code = "dn"' in (sites / "dn.toml").read_text(encoding="utf-8")
    assert cli_main(["new-site", "dn"]) == 2
    assert cli_main(["new-site", "Bad Code!"]) == 2


def test_check_site_reports_missing_inputs(tmp_path, monkeypatch, site):
    from efefo.checks import check_site

    monkeypatch.setenv("SAP_OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("SAP_SESSION_DIR", str(tmp_path / "s"))
    monkeypatch.delenv("SAP_INPUT_DIR", raising=False)
    problems, warnings = check_site(site)
    assert any("Shelflife.xlsx" in p for p in problems) and any("Capacity.xlsx" in p for p in problems)
    assert any("FEFO" in w for w in warnings)
