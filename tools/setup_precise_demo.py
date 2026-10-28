"""Register the bundled full-size E350 door demo; no download or retraining."""
import argparse
from spray_cerebellum.demo_setup import install_precise_demo

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--state-dir')
    args=parser.parse_args();print('Prepared asset:',install_precise_demo(args.state_dir))
