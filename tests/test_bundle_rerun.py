"""S13: real FE/optimizer replay, saved settings, tampering, cache and PDF coverage."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from morphic.bundle import _unpack, compare, create_bundle, rerun_bundle
from morphic.cache import ROOT, RunCache, cache_key, load_results


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    root = tmp_path_factory.mktemp("bundle")
    # Use the actual approved RC geometry/loads with one material and a small mesh.
    # Non-default stop controls exercise restoration before engine imports.
    script = """
import json, sys
from pathlib import Path
from morphic import config
config.MAX_ITERS_COLD = 8
config.MAX_ITERS_WARM = 8
config.MAX_ITERS_REFINE = 8
config.BETA_STEP_ITERS = 2
config.REFINE_BISECTION_STEPS = 1
from morphic.precompute import precompute_part
from morphic.cache import code_version
root = Path(sys.argv[1])
p = json.loads(Path('examples/rc_arm.json').read_text())
p['materials'] = ['pa6cf']
(root / 'rc_arm.json').write_text(json.dumps(p))
precompute_part(root / 'rc_arm.json', root / 'cache', cap=700, levels=(.6, .4),
                version=code_version(), save_catalog_snapshots=False)
"""
    env = os.environ.copy()
    env["MPLCONFIGDIR"] = str(root / "mpl")
    subprocess.run([sys.executable, "-c", script, str(root)], cwd=ROOT, check=True, env=env)
    source = root / "cache" / "rc_arm"
    archive = create_bundle(source, root / "run.zip")
    return source, archive, root


def test_both_real_rerun_modes_restore_settings(run):
    _, archive, root = run
    result = rerun_bundle(archive)
    (root / "diff.json").write_text(json.dumps(result, indent=2))
    assert result["passed"], result
    assert set(result["modes"]) == {"evaluation", "optimization"}
    assert len(result["modes"]["evaluation"]["comparisons"]) > 30
    assert len(result["modes"]["optimization"]["comparisons"]) == 2


def test_bundle_complete_and_pdf_one_page(run):
    source, archive, _ = run
    with zipfile.ZipFile(archive) as z:
        assert {"problem.json", "materials.yaml", "processes.yaml", "solver_settings.json",
                "code_version.txt", "environment.txt", "results.json", "densities.npz", "report.pdf"} <= set(z.namelist())
        assert not any(".env" in name for name in z.namelist())
        pdf = z.read("report.pdf")
        assert pdf.startswith(b"%PDF-")
        import re
        assert len(re.findall(rb"/Type /Page\b", pdf)) == len(load_results(source)["designs"])


def test_checksum_and_traversal_rejected(run, tmp_path):
    _, archive, _ = run
    for name, payload in (("results.json", b"{}"), ("../outside", b"bad")):
        bad = tmp_path / ("traversal.zip" if name.startswith("..") else "changed.zip")
        with zipfile.ZipFile(archive) as src, zipfile.ZipFile(bad, "w") as dst:
            for member in src.namelist():
                dst.writestr(member, payload if member == name else src.read(member))
            if name.startswith(".."):
                dst.writestr(name, payload)
        with pytest.raises((ValueError, KeyError)):
            _unpack(bad, tmp_path)


def test_recomputed_numbers_detect_planted_error(run, tmp_path):
    _, archive, _ = run
    with zipfile.ZipFile(archive) as z:
        files = {n: z.read(n) for n in z.namelist()}
    results = json.loads(files["results.json"])
    results["designs"][0]["checks"]["mass_g"] *= 1.1
    files["results.json"] = json.dumps(results).encode()
    manifest = json.loads(files["manifest.json"])
    manifest["files"]["results.json"] = hashlib.sha256(files["results.json"]).hexdigest()
    files["manifest.json"] = json.dumps(manifest).encode()
    bad = tmp_path / "wrong-numbers.zip"
    with zipfile.ZipFile(bad, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    result = rerun_bundle(bad, "evaluation")
    assert not result["passed"]
    assert any(not c["passed"] and c["path"].endswith("checks.mass_g")
               for c in result["modes"]["evaluation"]["comparisons"])


def test_cache_invalidation_and_integrity(run, tmp_path):
    source, _, _ = run
    data = load_results(source)
    args = [data["problem"], data["solver_settings"], data["code_version"], data["materials_hash"]]
    assert cache_key(*args) == data["key"]
    for i, replacement in enumerate(({**args[0], "name": "edited"}, {**args[1], "cap_used": 999}, "new-code", "new-library")):
        changed = list(args)
        changed[i] = replacement
        assert cache_key(*changed) != data["key"]
    cache = RunCache(tmp_path / "store")
    assert cache.get("0" * 64) is None
    path = cache.put(source)
    assert cache.get(data["key"]) == data
    assert cache.put(source) == path
    (path / "densities.npz").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        cache.get(data["key"])
    with pytest.raises(ValueError):
        cache.path("../escape")


def test_comparison_boundaries():
    assert compare(100, 100.5, .005)[0].passed
    assert not compare(100, 100.51, .005)[0].passed
    assert compare(100, 102, .02)[0].passed
    assert not compare(100, 102.01, .02)[0].passed
    assert not compare(float("nan"), float("nan"), .005)[0].passed
    assert not compare({"a": 1}, {}, .005)[0].passed
    assert not compare([1], [1, 2], .005)[0].passed
    assert not compare(0, 1e-6, .005)[0].passed
    assert not compare("inf", "-inf", .005)[0].passed


def test_cli_dispatch_and_failure_exit(run, tmp_path, capsys):
    from morphic.cli import main
    source, _, _ = run
    assert main(["report", str(source), "--out", str(tmp_path / "one.pdf")]) == 0
    assert main(["render", str(source), "--out", str(tmp_path / "movie.mp4")]) == 2
    assert main(["cache", "--key", "0" * 64, "--root", str(tmp_path / "empty")]) == 1
    invalid = tmp_path / "invalid.zip"
    invalid.write_bytes(b"not a zip")
    assert main(["rerun", str(invalid)]) == 2
