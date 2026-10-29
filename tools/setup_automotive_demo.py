"""Register the automotive-only demo package, without retraining."""
import argparse
from spray_cerebellum.automotive_setup import install_automotive_demo

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir")
    args = parser.parse_args()
    print("Prepared automotive asset:", install_automotive_demo(args.state_dir))
