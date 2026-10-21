"""Local, content-addressed run storage; compatible with the S14 demo caches.

Only named solver artifacts are copied. No directory recursion, pickle, environment
files, credentials, or network access are involved.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = ROOT / "examples" / "cache" / "runs"


def code_version() -> str:
    """Commit plus a content fingerprint when dirty (dirty edits must invalidate caches)."""
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        status = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)
        if not status:
            return head
        digest = hashlib.sha256(status)
        for path in sorted((ROOT / "morphic").rglob("*")):
            if path.is_file() and path.suffix in {".py", ".yaml"}:
                digest.update(path.relative_to(ROOT).as_posix().encode())
                digest.update(path.read_bytes())
        for name in ("pyproject.toml", "uv.lock"):
            digest.update((ROOT / name).read_bytes())
        return f"{head}-dirty-{digest.hexdigest()[:16]}"
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def cache_key(problem, settings: dict, version: str, materials_hash: str | None = None) -> str:
    """SHA-256 of problem, library hash (materials AND processes), settings, version.

    The encoding deliberately matches precompute.cache_key for existing demo runs.
    """
    from .materials import library_hash
    if hasattr(problem, "model_dump"):
        problem = problem.model_dump(mode="json")
    h = hashlib.sha256()
    h.update(json.dumps(problem, sort_keys=True).encode())
    h.update((materials_hash if materials_hash is not None else library_hash()).encode())
    h.update(json.dumps(settings, sort_keys=True, default=str).encode())
    h.update(version.encode())
    return h.hexdigest()


def load_results(directory: Path | str) -> dict:
    data = json.loads((Path(directory) / "results.json").read_text(encoding="utf-8"))
    if data.get("format_version") != 1 or not data.get("designs"):
        raise ValueError("unsupported or empty cache")
    expected = cache_key(data["problem"], data["solver_settings"], data["code_version"], data["materials_hash"])
    if data.get("key") != expected:
        raise ValueError("cache key does not match its inputs")
    return data


def artifact_names(results: dict) -> set[str]:
    names = {"results.json", "densities.npz", "utilization.npz"}
    for d in results["designs"]:
        mid = d["material"]
        if not re.fullmatch(r"[a-z0-9_]+", mid):
            raise ValueError("invalid material id")
        if d.get("geometry"):
            for suffix, name in d["geometry"]["files"].items():
                if suffix not in {"stl", "svg", "dxf"} or name != f"{mid}.{suffix}":
                    raise ValueError("invalid geometry artifact name")
                names.add(name)
    for pid in results["catalogs"]:
        if pid not in {"fdm", "sls", "metal"}:
            raise ValueError("invalid process id")
        names.add(f"rerun_{pid}.npz")
    return names


class RunCache:
    def __init__(self, root: Path | str = DEFAULT_ROOT):
        self.root = Path(root)

    def path(self, key: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{64}", key):
            raise ValueError("cache key must be a SHA-256 digest")
        return self.root / key

    def get(self, key: str) -> dict | None:
        path = self.path(key)
        if not path.exists():
            return None
        data = load_results(path)
        if data["key"] != key:
            raise ValueError("cache entry is stored under the wrong key")
        manifest = json.loads((path / "cache_manifest.json").read_text(encoding="utf-8"))
        names = artifact_names(data)
        required = {n for n in names if n != "utilization.npz" and not n.startswith("rerun_")}
        if not required <= set(manifest) or not set(manifest) <= names:
            raise ValueError("cache manifest member mismatch")
        for name in names:
            if name in manifest:
                if hashlib.sha256((path / name).read_bytes()).hexdigest() != manifest[name]:
                    raise ValueError(f"cache artifact checksum mismatch: {name}")
        return data

    def put(self, source: Path | str) -> Path:
        source = Path(source)
        data = load_results(source)
        target = self.path(data["key"])
        self.root.mkdir(parents=True, exist_ok=True)
        if target.exists():
            self.get(data["key"])
            return target
        with tempfile.TemporaryDirectory(prefix=".cache-", dir=self.root) as tmp:
            staging = Path(tmp) / "run"
            staging.mkdir()
            manifest = {}
            for name in sorted(artifact_names(data)):
                path = source / name
                if not path.exists() and (name == "utilization.npz" or name.startswith("rerun_")):
                    continue
                if path.is_symlink():
                    raise ValueError("cache artifacts must be regular files")
                shutil.copyfile(path, staging / name)
                manifest[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            (staging / "cache_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            try:
                staging.rename(target)
            except FileExistsError:
                self.get(data["key"])
        return target
