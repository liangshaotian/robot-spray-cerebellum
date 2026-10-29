"""Install the E350 automotive demo with the existing 70-dimensional policy."""
from __future__ import annotations
import json
import os
import pathlib
import shutil
import uuid
from .common import REPO
from .demo_setup import install_precise_demo, sha256

BUNDLE = REPO / "demo/e350_sac_v2"
ASSET_ID = "sacgen_e350_v2"


def verify_bundle(bundle=BUNDLE):
    bundle = pathlib.Path(bundle)
    checks = json.loads((bundle / "checksums.json").read_text(encoding="utf-8"))
    for name, expected in checks["files"].items():
        if pathlib.Path(name).name != name or sha256(bundle / name) != expected:
            raise ValueError("Automotive bundle checksum mismatch: " + name)
    return bundle


def install_automotive_demo(state_dir=None, bundle=BUNDLE):
    bundle = verify_bundle(bundle)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    geometry = install_precise_demo(state_dir) / manifest["mesh_file"]
    root = pathlib.Path(state_dir or REPO / ".local") / "assets"
    destination = root / ASSET_ID
    expected = {name: sha256(bundle / name) for name in (manifest["surface_file"], manifest["policy_file"])}
    expected[manifest["mesh_file"]] = sha256(geometry)
    if destination.exists():
        current = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
        if current != manifest or any(sha256(destination / name) != value for name, value in expected.items()):
            raise ValueError("Existing automotive asset differs; use a separate --state-dir")
        return destination
    staging = root / (ASSET_ID + ".staging-" + uuid.uuid4().hex)
    staging.mkdir()
    try:
        for name in (manifest["surface_file"], manifest["policy_file"], "manifest.json"):
            shutil.copyfile(bundle / name, staging / name)
        try:
            os.link(geometry, staging / manifest["mesh_file"])
        except OSError:
            shutil.copyfile(geometry, staging / manifest["mesh_file"])
        if any(sha256(staging / name) != value for name, value in expected.items()):
            raise ValueError("Automotive asset copy checksum mismatch")
        staging.rename(destination)
    except Exception:
        if staging.resolve().parent != root.resolve():
            raise RuntimeError("Refusing cleanup outside automotive staging root")
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return destination
