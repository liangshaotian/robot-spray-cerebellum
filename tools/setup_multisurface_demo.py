"""Register the checksum-verified GPU-trained policy and selected demo geometries."""
import argparse
from spray_cerebellum.multisurface_setup import install_multisurface_demo

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir")
    parser.add_argument("--cases", nargs="+", choices=("e350", "saddle", "shell", "starfish"), default=["e350", "saddle"])
    args = parser.parse_args()
    for path in install_multisurface_demo(args.state_dir, args.cases):
        print("Prepared asset:", path.name)
    if any(case in ("shell", "starfish") for case in args.cases):
        print("NOTE: shell/starfish are recorded E12 preflight failures, not successful robot demos.")
