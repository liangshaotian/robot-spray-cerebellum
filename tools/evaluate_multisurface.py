"""Reproduce the 90 reported held-out rollouts on CPU; never trains or drives a robot."""
import argparse
import csv
import json
import pathlib
import numpy as np
import torch
from stable_baselines3 import SAC
from spray_cerebellum.common import REPO
from spray_cerebellum.generalized import SurfaceCase, GeneralizedSprayEnv
from spray_cerebellum.multisurface_setup import BUNDLE, verify_bundle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, default=REPO / ".local/multisurface_evaluation")
    parser.add_argument("--verify-recorded", action="store_true")
    args = parser.parse_args()
    torch.set_num_threads(2)
    verify_bundle()
    dataset = json.loads((BUNDLE / "dataset.json").read_text(encoding="utf-8"))
    reference = json.loads((BUNDLE / "results/summary.json").read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=False)
    model = SAC.load(BUNDLE / "models/sac_multisurface_gpu_v2.zip", device="cpu")
    rows = []
    for row in dataset["test"]:
        directory = BUNDLE / row["asset_dir"]
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        case = SurfaceCase(directory, manifest, row["process"], row["sample_step_mm"])
        for gain in (.65, 1., 1.2):
            for method in ("raster", "constant_validation", "new_sac"):
                env = GeneralizedSprayEnv([case])
                observation, _ = env.reset()
                env.flow_gain = gain
                observation = env.observation()
                while True:
                    if method == "raster":
                        action = np.zeros(2)
                    elif method == "constant_validation":
                        action = np.asarray(reference["constant_control_action_selected_on_validation"])
                    else:
                        action = model.predict(observation, deterministic=True)[0]
                    observation, _, done, _, _ = env.step(action)
                    if done:
                        break
                rows.append({"case_id": row["case_id"], "method": method, "flow_gain": gain, **env.quality()})
        print("Tested:", row["case_id"], flush=True)
    numeric = ("target_normalized_rmse", "relative_dose_cv", "coverage_fraction", "within_20pct_target_fraction", "estimated_spray_seconds")
    means = {method: {key: float(np.mean([r[key] for r in rows if r["method"] == method])) for key in numeric}
             for method in reference["reported_methods"]}
    # Exactly three gains per geometry, so this average equals equal geometry weighting.
    if args.verify_recorded:
        for method in means:
            for key, value in means[method].items():
                np.testing.assert_allclose(value, reference["methods"][method]["means"][key], rtol=1e-6, atol=1e-8)
    with (args.output / "rollouts.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    (args.output / "summary.json").write_text(json.dumps({"rollouts": len(rows), "means": means,
        "matches_recorded": True if args.verify_recorded else None}, indent=2), encoding="utf-8")
    print(json.dumps({"rollouts": len(rows), "means": means, "verified": args.verify_recorded}))


if __name__ == "__main__":
    main()
