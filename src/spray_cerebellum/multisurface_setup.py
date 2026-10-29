"""Install the frozen multi-surface SAC assets without replacing legacy assets."""
from __future__ import annotations
import gzip
import hashlib
import json
import os
import pathlib
import shutil
import uuid
from .common import REPO
from .demo_setup import install_precise_demo, sha256

BUNDLE = REPO / "experiments/multisurface_20261029"
POLICY_ID = "sac_multisurface_gpu_v2"


def verify_bundle(bundle=BUNDLE):
    bundle = pathlib.Path(bundle)
    checks = json.loads((bundle / "checksums.json").read_text(encoding="utf-8"))
    for name, expected in checks["files"].items():
        path = (bundle / name).resolve()
        if not path.is_relative_to(bundle.resolve()):
            raise ValueError("Invalid bundle member")
        if sha256(path) != expected:
            raise ValueError("Multi-surface bundle checksum mismatch: " + name)
    return bundle


def install_multisurface_demo(state_dir=None, cases=("e350", "saddle"), bundle=BUNDLE):
    bundle = verify_bundle(bundle)
    index = json.loads((bundle / "registry_assets.json").read_text(encoding="utf-8"))
    if not cases or len(set(cases)) != len(cases) or any(case not in index for case in cases):
        raise ValueError("Choose distinct supported cases: " + ", ".join(index))
    root = pathlib.Path(state_dir or REPO / ".local") / "assets"
    root.mkdir(parents=True, exist_ok=True)
    installed = []
    for case in cases:
        item = index[case]
        manifest = item["manifest"]
        destination = root / manifest["asset_id"]
        surface = bundle / item["surface_dir"] / manifest["surface_file"]
        policy = bundle / "models/sac_multisurface_gpu_v2.zip"
        if item["mesh_source"] == "bundled_artec_e350_geometry":
            geometry = install_precise_demo(state_dir) / manifest["mesh_file"]
            mesh_hash = sha256(geometry)
        else:
            geometry = None
            mesh_hash = item["mesh_sha256"]
        expected = {manifest["surface_file"]: sha256(surface), manifest["policy_file"]: sha256(policy),
                    manifest["mesh_file"]: mesh_hash}
        if destination.exists():
            current = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
            if current != manifest or any(sha256(destination / name) != value for name, value in expected.items()):
                raise ValueError("Existing multi-surface asset differs; use a separate --state-dir: " + case)
            installed.append(destination)
            continue
        staging = root / (manifest["asset_id"] + ".staging-" + uuid.uuid4().hex)
        staging.mkdir()
        try:
            shutil.copyfile(surface, staging / manifest["surface_file"])
            shutil.copyfile(policy, staging / manifest["policy_file"])
            mesh_target = staging / manifest["mesh_file"]
            if geometry is not None:
                try:
                    os.link(geometry, mesh_target)
                except OSError:
                    shutil.copyfile(geometry, mesh_target)
            else:
                with gzip.open(bundle / item["mesh_source"], "rb") as source, mesh_target.open("wb") as output:
                    shutil.copyfileobj(source, output)
            if any(sha256(staging / name) != value for name, value in expected.items()):
                raise ValueError("Expanded asset checksum mismatch: " + case)
            (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            staging.rename(destination)
        except Exception:
            if staging.resolve().parent != root.resolve():
                raise RuntimeError("Refusing cleanup outside asset staging root")
            if staging.exists():
                shutil.rmtree(staging)
            raise
        installed.append(destination)
    return installed
