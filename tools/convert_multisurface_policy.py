"""Convert trusted tensor-only weights to the existing Python 3.11 runtime."""
import argparse
import hashlib
import json
import pathlib
import numpy as np
import gymnasium as gym
from gymnasium import spaces
import torch
from stable_baselines3 import SAC

ROOT=pathlib.Path(__file__).parent.parent/".local/multisurface_training"


class ShapeOnlyEnv(gym.Env):
    def __init__(self):
        self.observation_space=spaces.Box(-5.,5.,shape=(70,),dtype=np.float32)
        self.action_space=spaces.Box(-1.,1.,shape=(2,),dtype=np.float32)
    def reset(self,seed=None,options=None):
        super().reset(seed=seed)
        return np.zeros(70,dtype=np.float32),{}
    def step(self,action):
        return np.zeros(70,dtype=np.float32),0.,True,False,{}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--run-dir",type=pathlib.Path,default=ROOT/"sac_multisurface_gpu_v2")
    parser.add_argument("--preflight",action="store_true",help="Check the current export without treating it as final trained weights")
    args=parser.parse_args();run=args.run_dir
    if args.preflight:
        config=json.loads((run/"config.json").read_text())
        history=json.loads((run/"validation_history.json").read_text())
        report={"best_step":min(history,key=lambda row:row["validation_score"])["steps"],
                "best_sha256":hashlib.sha256((run/"best.zip").read_bytes()).hexdigest(),"torch":config["torch"]}
    else:
        report=json.loads((run/"training_report.json").read_text())
    torch.set_num_threads(2)
    state=torch.load(run/"best_policy_state.pt",map_location="cpu",weights_only=True)
    model=SAC("MlpPolicy",ShapeOnlyEnv(),policy_kwargs={"net_arch":[256,256]},device="cpu",learning_rate=2e-4)
    model.policy.load_state_dict(state,strict=True)
    model.num_timesteps=report["best_step"]
    with np.load(run/"portable_policy_probe.npz",allow_pickle=False) as probe:
        actions=model.predict(probe["observations"],deterministic=True)[0]
        error=float(np.max(np.abs(actions-probe["actions"])))
    assert error<2e-5,error
    stem="preflight_inference" if args.preflight else "best_inference"
    model.save(run/stem)
    result={"passed":True,"source_training_checkpoint_sha256":report["best_sha256"],
            "inference_checkpoint_sha256":hashlib.sha256((run/(stem+".zip")).read_bytes()).hexdigest(),
            "max_cuda_vs_cpu_action_difference":error,"probe_observations":32,
            "training_torch":report["torch"],"inference_torch":torch.__version__,
            "format":"Same policy state_dict; fresh local runtime metadata and optimizer; inference only","preflight_only":args.preflight}
    (run/("preflight_conversion.json" if args.preflight else "inference_conversion.json")).write_text(json.dumps(result,indent=2))
    print("INFERENCE_CONVERSION",json.dumps(result),flush=True)


if __name__=="__main__":main()
