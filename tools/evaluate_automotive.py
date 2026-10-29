"""Reproduce E350 front-door checks; these are not independent vehicle tests."""
import argparse
import csv
import json
from pathlib import Path
import numpy as np
import torch
from stable_baselines3 import SAC
from spray_cerebellum.automotive_setup import BUNDLE, verify_bundle
from spray_cerebellum.common import REPO
from spray_cerebellum.generalized import SurfaceCase, GeneralizedSprayEnv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=REPO / ".local/automotive_evaluation")
    parser.add_argument("--verify-recorded", action="store_true")
    args = parser.parse_args()
    torch.set_num_threads(2)
    verify_bundle()
    manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))
    reference = json.loads((REPO / "experiments/automotive_20261029/summary.json").read_text(encoding="utf-8"))
    case = SurfaceCase(BUNDLE, manifest, manifest["recommended_process"], 40.)
    model = SAC.load(BUNDLE / manifest["policy_file"], device="cpu")
    rows = []
    for gain in (.65, 1., 1.2):
        for method in ("raster", "fixed_speed", "sac"):
            env = GeneralizedSprayEnv([case]); observation, _ = env.reset()
            env.flow_gain = gain; observation = env.observation()
            while True:
                action = model.predict(observation, deterministic=True)[0] if method == "sac" else np.array([0., 1. if method == "fixed_speed" else 0.])
                observation, _, done, _, _ = env.step(action)
                if done:
                    break
            rows.append({"method": method, "flow_gain": gain, **env.quality()})
    keys = ("target_normalized_rmse", "relative_dose_cv", "coverage_fraction", "within_20pct_target_fraction", "estimated_spray_seconds")
    means = {method: {key: float(np.mean([r[key] for r in rows if r["method"] == method])) for key in keys}
             for method in ("raster", "fixed_speed", "sac")}
    if args.verify_recorded:
        for method in means:
            for key, value in means[method].items():
                np.testing.assert_allclose(value, reference["means_over_conditions"][method][key], rtol=1e-6, atol=1e-8)
    args.output.mkdir(parents=True, exist_ok=False)
    with (args.output / "rollouts.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    result = {"vehicle_sources": 1, "regions": 1, "conditions": 3, "rollouts": len(rows),
              "means": means, "verified": args.verify_recorded, "independent_vehicle_generalization": False}
    (args.output / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
