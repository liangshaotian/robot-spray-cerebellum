"""Bounded CUDA SAC training; validation only selects the checkpoint."""
import os
import pathlib
import sys
TOOLS = pathlib.Path(__file__).parent
REPO = TOOLS.parent
ROOT = REPO/"experiments/multisurface_20261029"
OUTPUT = REPO/".local/multisurface_training"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(REPO/"src"))
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")
import argparse
import csv
import hashlib
import json
import subprocess
import time
import numpy as np
import torch
from stable_baselines3 import SAC
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv
from spray_cerebellum.generalized import SurfaceCase, GeneralizedSprayEnv, OBSERVATION_VERSION
from multisurface_training_utils import load_cases, rollout


def write_json(path, value):
    temporary = path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(value,indent=2,allow_nan=False),encoding="utf-8")
    temporary.replace(path)


def export_portable_policy(model,destination):
    # Tensor-only export avoids pickled Python 3.12 closures in the project's
    # Python 3.11 inference process, while preserving the exact actor weights.
    torch.save({key:value.detach().cpu() for key,value in model.policy.state_dict().items()},destination/"best_policy_state.pt")
    rng=np.random.default_rng(928)
    observations=rng.uniform(-1,1,(32,70)).astype(np.float32)
    observations[:,21:]=rng.uniform(0,1.8,(32,49)).astype(np.float32)
    actions=model.predict(observations,deterministic=True)[0]
    np.savez_compressed(destination/"portable_policy_probe.npz",observations=observations,actions=actions)


def validate(cases, model):
    rows=[]
    for case in cases:
        for gain in (.65,1.15):
            quality,_=rollout(case,model,flow_gain=gain)
            rows.append({"case":case.manifest["asset_id"],"flow_gain":gain,**quality})
    score=float(np.mean([r["target_normalized_rmse"]+.25*r["relative_dose_cv"]+2*max(0.,.98-r["coverage_fraction"]) for r in rows]))
    return score,rows


class BudgetCallback(BaseCallback):
    def __init__(self,destination,validation,budget):
        super().__init__();self.destination=destination;self.validation=validation;self.budget=budget
        self.started=time.monotonic();self.best=float("inf");self.best_step=0;self.stale=0
        self.records=[];self.evaluations=[];self.episodes=0;self.stop_reason="step_limit"
        self.initial_actor=None;self.device_peaks={"memory_used_mib":0.,"temperature_c":0.}

    def _on_training_start(self):
        self.initial_actor=torch.cat([p.detach().flatten().cpu() for p in self.model.actor.parameters()]).clone()
        score,rows=validate(self.validation,self.model)
        self.best=score;self.model.save(self.destination/"best")
        export_portable_policy(self.model,self.destination)
        self.evaluations.append({"steps":0,"validation_score":score,"cases":rows})
        write_json(self.destination/"validation_history.json",self.evaluations)

    def _on_step(self):
        self.episodes+=sum(bool(info.get("episode")) for info in self.locals.get("infos",[]))
        elapsed=time.monotonic()-self.started
        if elapsed>=self.budget:
            self.stop_reason="wall_time_budget";return False
        if self.num_timesteps%5000==0:
            monitor={}
            try:
                result=subprocess.run(["nvidia-smi","--query-gpu=memory.used,utilization.gpu,temperature.gpu","--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=4,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
                used,util,temp=[float(v.strip()) for v in result.stdout.strip().split(",")]
                monitor={"device_memory_used_mib":used,"gpu_utilization_pct":util,"temperature_c":temp}
                self.device_peaks["memory_used_mib"]=max(self.device_peaks["memory_used_mib"],used)
                self.device_peaks["temperature_c"]=max(self.device_peaks["temperature_c"],temp)
                if temp>=88:
                    self.stop_reason="temperature_limit";return False
            except Exception:pass
            row={"steps":self.num_timesteps,"elapsed_s":round(elapsed,2),"steps_per_second":round(self.num_timesteps/max(elapsed,1),1),
                 "gradient_updates":self.model._n_updates,"completed_episodes":self.episodes,
                 "cuda_allocated_mib":round(torch.cuda.memory_allocated()/2**20,2),
                 "cuda_reserved_mib":round(torch.cuda.memory_reserved()/2**20,2),**monitor}
            self.records.append(row);write_json(self.destination/"progress.json",row)
            write_json(self.destination/"training_progress.json",self.records)
            print("TRAINING",json.dumps(row),flush=True)
        if self.num_timesteps%20000==0:
            score,rows=validate(self.validation,self.model)
            improved=score < self.best-1e-4
            if improved:
                self.best=score;self.best_step=self.num_timesteps;self.stale=0;self.model.save(self.destination/"best")
                export_portable_policy(self.model,self.destination)
            else:self.stale+=1
            self.model.save(self.destination/"latest")
            self.evaluations.append({"steps":self.num_timesteps,"validation_score":score,"selected":improved,"cases":rows})
            write_json(self.destination/"validation_history.json",self.evaluations)
            print("VALIDATION",self.num_timesteps,round(score,6),"best",round(self.best,6),"selected",improved,flush=True)
            if self.num_timesteps>=120000 and self.stale>=4:
                self.stop_reason="validation_plateau";return False
        return True


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--steps",type=int,default=240000);parser.add_argument("--budget-seconds",type=int,default=5400)
    parser.add_argument("--run-name",default="sac_multisurface_gpu_v2");args=parser.parse_args()
    OUTPUT.mkdir(parents=True,exist_ok=True)
    if not 0<args.budget_seconds<=6600:raise ValueError("Training budget must stay below two hours")
    if not torch.cuda.is_available():raise RuntimeError("CUDA is required; refusing an unnoticed CPU fallback")
    torch.set_num_threads(2);torch.set_num_interop_threads(2)
    torch.cuda.set_per_process_memory_fraction(.35,0)
    torch.manual_seed(20261029)
    torch.backends.cudnn.benchmark=False
    # Exercise a real CUDA kernel before starting any learning.
    probe=torch.ones((128,128),device="cuda")@torch.ones((128,128),device="cuda")
    assert float(probe[0,0])==128.;torch.cuda.synchronize()
    write_json(OUTPUT/"cuda_ready.json",{"torch":torch.__version__,"cuda":torch.version.cuda,
                                      "gpu":torch.cuda.get_device_name(0),"kernel_check_passed":True})
    dataset=json.loads((ROOT/"dataset.json").read_text(encoding="utf-8"))
    train=load_cases(dataset["train"]);validation=load_cases(dataset["validation"])
    destination=OUTPUT/args.run_name;destination.mkdir(parents=True,exist_ok=False)
    config={"algorithm":"SAC","library":"Stable-Baselines3 2.4.1","torch":torch.__version__,"cuda":torch.version.cuda,
            "gpu":torch.cuda.get_device_name(0),"device":"cuda:0","cuda_kernel_check":True,
            "observation_version":OBSERVATION_VERSION,"observation_dim":70,"action_dim":2,"net_arch":[256,256],
            "training_profiles":len(train),"training_geometry_assets":dataset["metadata"]["training_geometry_assets"],
            "validation_profiles":len(validation),"held_out_test_profiles":len(dataset["test"]),
            "seed":20261029,"max_timesteps":args.steps,"wall_budget_seconds":args.budget_seconds,
            "gpu_allocator_fraction":.35,"num_envs":4,"batch_size":256,"buffer_size":100000,
            "learning_rate":2e-4,"learning_starts":5000,"gradient_steps":4,"gamma":.99,"tau":.01,"ent_coef":"auto_0.03",
            "flow_gain_randomization":[.55,1.25],"validation_flow_gains":[.65,1.15],"validation_selects_checkpoint":True,"test_used_for_selection":False,
            "physical_model":"Uncalibrated relative Gaussian deposition; fixed reference emission rate; not CFD or physical thickness"}
    import spray_cerebellum.generalized as environment_module
    snapshot=destination/"source_snapshot";snapshot.mkdir()
    source_files=[pathlib.Path(__file__),TOOLS/"multisurface_training_utils.py",pathlib.Path(environment_module.__file__)]
    config["source_code_sha256"]={}
    for source_file in source_files:
        payload=source_file.read_bytes()
        config["source_code_sha256"][source_file.name]=hashlib.sha256(payload).hexdigest()
        (snapshot/source_file.name).write_bytes(payload)
    config["dataset_sha256"]=hashlib.sha256((ROOT/"dataset.json").read_bytes()).hexdigest()
    (snapshot/"dataset.json").write_bytes((ROOT/"dataset.json").read_bytes())
    write_json(destination/"config.json",config)
    write_json(OUTPUT/"current_run.json",{"run_dir":str(destination),"state":"training"})
    env=DummyVecEnv([lambda index=index:Monitor(GeneralizedSprayEnv(train,training=True,seed=20261029+index)) for index in range(4)])
    model=SAC("MlpPolicy",env,policy_kwargs={"net_arch":[256,256]},learning_rate=2e-4,buffer_size=100000,
              learning_starts=5000,batch_size=256,tau=.01,gamma=.99,train_freq=1,gradient_steps=4,
              ent_coef="auto_0.03",seed=20261029,device="cuda",verbose=0)
    assert all(parameter.is_cuda for parameter in model.policy.parameters()), "A policy tensor silently fell back to CPU"
    callback=BudgetCallback(destination,validation,args.budget_seconds)
    print("TRAIN_START",json.dumps(config),flush=True)
    train_started=time.monotonic()
    try:
        model.learn(total_timesteps=args.steps,callback=callback)
    finally:
        model.save(destination/"final")
        elapsed=time.monotonic()-train_started
        actor=torch.cat([p.detach().flatten().cpu() for p in model.actor.parameters()])
        report={**config,"timesteps":model.num_timesteps,"gradient_updates":model._n_updates,
                "training_seconds":round(elapsed,2),"stop_reason":callback.stop_reason,
                "best_validation_score":callback.best,"best_step":callback.best_step,
                "completed_training_episodes":callback.episodes,
                "actor_parameter_count":sum(p.numel() for p in model.actor.parameters()),
                "actor_device":str(next(model.actor.parameters()).device),
                "critic_device":str(next(model.critic.parameters()).device),
                "all_policy_parameter_count":sum(p.numel() for p in model.policy.parameters()),
                "actor_parameter_l2_change":float(torch.linalg.norm(actor-callback.initial_actor)),
                "cuda_peak_allocated_mib":torch.cuda.max_memory_allocated()/2**20,
                "cuda_peak_reserved_mib":torch.cuda.max_memory_reserved()/2**20,
                "observed_gpu_peaks":callback.device_peaks,
                "best_sha256":hashlib.sha256((destination/"best.zip").read_bytes()).hexdigest()}
        write_json(destination/"training_report.json",report)
        write_json(OUTPUT/"current_run.json",{"run_dir":str(destination),"state":"trained","training_seconds":report["training_seconds"]})
        env.close()
        print("TRAIN_COMPLETE",json.dumps(report),flush=True)


if __name__=="__main__":main()
