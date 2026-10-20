"""S5 acceptance: the library loads, and the loader rejects any value without a citation."""

import copy

import pytest
import yaml

from morphic import materials as M


def test_library_loads_with_six_materials_and_three_processes():
    ms = M.load_materials()
    ps = M.load_processes()
    assert set(ms) == {"pla", "petg", "pa6cf", "pa12", "alsi10mg", "ti64"}
    assert set(ps) == {"fdm", "sls", "metal"}
    for m in ms.values():
        assert m.E > 0 and m.strength > 0 and m.density > 0
        z, note = m.strength_z_used()
        assert z > 0 and note
        tau, note2 = m.interlayer_shear_used()
        assert 0 < tau < z
        for key in ("E", "nu", "strength_xy", "density"):
            assert m.citations[key].url.startswith("http")
    for p in ps.values():
        assert p.min_wall_mm > 0 and p.citation.url.startswith("http")


def _raw():
    with open(M.MATERIALS_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_value_without_citation_is_rejected(tmp_path):
    doc = _raw()
    bad = copy.deepcopy(doc)
    bad["materials"][0]["citations"]["E"] = None
    p = tmp_path / "m.yaml"
    p.write_text(yaml.safe_dump(bad), encoding="utf-8")
    with pytest.raises(M.MaterialDataError, match="citation"):
        M.load_materials(p)


def test_citation_without_url_is_rejected(tmp_path):
    doc = _raw()
    bad = copy.deepcopy(doc)
    bad["materials"][1]["citations"]["density"] = {"title": "some sheet"}
    p = tmp_path / "m.yaml"
    p.write_text(yaml.safe_dump(bad), encoding="utf-8")
    with pytest.raises(M.MaterialDataError):
        M.load_materials(p)


def test_missing_z_and_knockdown_is_rejected(tmp_path):
    doc = _raw()
    bad = copy.deepcopy(doc)
    m = bad["materials"][0]
    m["strength_z_MPa"] = None
    m["z_knockdown"] = {"value": None, "source": None}
    p = tmp_path / "m.yaml"
    p.write_text(yaml.safe_dump(bad), encoding="utf-8")
    with pytest.raises(M.MaterialDataError, match="knockdown"):
        M.load_materials(p)


def test_missing_required_value_is_rejected(tmp_path):
    doc = _raw()
    bad = copy.deepcopy(doc)
    bad["materials"][2]["density_g_cm3"] = None
    p = tmp_path / "m.yaml"
    p.write_text(yaml.safe_dump(bad), encoding="utf-8")
    with pytest.raises(M.MaterialDataError, match="density"):
        M.load_materials(p)


def test_library_hash_is_stable():
    assert M.library_hash() == M.library_hash()
