"""Shared evaluation over the exact training/inference environment."""
import json
import pathlib
import numpy as np
from spray_cerebellum.generalized import SurfaceCase, GeneralizedSprayEnv


def load_cases(rows):
    cases=[]
    for row in rows:
        directory=pathlib.Path(row["asset_dir"])
        if not directory.is_absolute():
            from spray_cerebellum.multisurface_setup import BUNDLE
            directory=BUNDLE/directory
        manifest=json.loads((directory/"manifest.json").read_text(encoding="utf-8"))
        manifest["deposition_flow_gain"]=row.get("flow_gain",1.)
        cases.append(SurfaceCase(directory,manifest,row["process"],row["sample_step_mm"]))
    return cases


def rollout(case, model=None, legacy=False, record=False, flow_gain=None, fixed_action=None):
    env=GeneralizedSprayEnv([case],record=record)
    obs,_=env.reset()
    if flow_gain is not None:
        env.flow_gain=float(flow_gain);obs=env.observation()
    while True:
        if fixed_action is not None:action=np.asarray(fixed_action,dtype=float)
        elif model is None:action=np.zeros(2)
        else:action=model.predict(env.observation(legacy=legacy),deterministic=True)[0]
        obs,_,done,_,_=env.step(action)
        if done:break
    return env.quality(),env


def quality_score(rows):
    return float(np.mean([r["target_normalized_rmse"]+.25*r["relative_dose_cv"]+2*max(0.,.98-r["coverage_fraction"]) for r in rows]))
