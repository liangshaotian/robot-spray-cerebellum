"""Versioned, process-conditioned SAC environment and compatible path export.

This is a geometric relative-deposition model, not calibrated coating physics.
The same environment implementation is used for training and inference.
"""
from __future__ import annotations
import json
import math
import pathlib
import numpy as np
from scipy.ndimage import map_coordinates, distance_transform_edt
import gymnasium as gym
from gymnasium import spaces
from .common import make_moves, filter_policy_action, TaskError

OBSERVATION_VERSION = "spray_v2_70"


class SurfaceCase:
    def __init__(self, directory, manifest, process=None, sample_step=40.):
        self.directory = pathlib.Path(directory)
        self.manifest = dict(manifest)
        self.process = {"standoff_mm": 200., "speed_mm_s": 400., "spray_width_mm": 240.,
                        "overlap_ratio": .5833333333333333, "passes": 1, **(process or {})}
        self.sample_step = float(sample_step)
        with np.load(self.directory / manifest["surface_file"], allow_pickle=False) as data:
            self.surface = {key: data[key].copy() for key in data.files}
        self.u, self.v = self.surface["u"], self.surface["v"]
        self.dx = float(self.u[1]-self.u[0])
        self.U, self.V = np.meshgrid(self.u, self.v)
        self.h = self.surface.get("path_h", self.surface["h"])
        self.du, self.dv = self.surface["du"], self.surface["dv"]
        self.safe = self.surface["safe"].astype(bool).copy()
        region = manifest["allowed_roi"]
        self.safe &= (self.U >= region["u_min_mm"]) & (self.U <= region["u_max_mm"])
        self.safe &= (self.V >= region["v_min_mm"]) & (self.V <= region["v_max_mm"])
        self.mask = self.safe & self.surface.get("coverage_mask", self.safe).astype(bool)
        self.area = self.surface["area"].astype(float)
        self.weights = self.area * self.mask
        self.weight_sum = float(self.weights.sum())
        if self.weight_sum <= 0:
            raise ValueError("No evaluated cells in " + manifest["asset_id"])
        self.edge_distance = distance_transform_edt(self.mask) * self.dx
        self.roi = region
        self.mean_h = float(np.average(self.h[self.mask], weights=self.area[self.mask]))
        self.anchors = []
        row_spacing = self.process["spray_width_mm"] * (1-self.process["overlap_ratio"])
        ys = np.arange(region["v_min_mm"] + min(30., (region["v_max_mm"]-region["v_min_mm"])/2), region["v_max_mm"], row_spacing)
        xs = np.arange(region["u_min_mm"] + min(20., self.sample_step/2), region["u_max_mm"], self.sample_step)
        if len(xs)*len(ys)*self.process["passes"] > 3000:
            raise TaskError("TASK_TOO_LARGE", "Generalized planner supports at most 3000 sampled anchor candidates")
        segment = 0
        for repeat in range(self.process["passes"]):
            for row, y in enumerate(ys):
                groups, current = [], []
                for x in (xs[::-1] if row % 2 else xs):
                    if self.valid(x, y):
                        if current and not self.connected(current[-1], (x, y)):
                            if len(current) >= 3: groups.append(current)
                            current = []
                        current.append((float(x), float(y)))
                    else:
                        if len(current) >= 3: groups.append(current)
                        current = []
                if len(current) >= 3: groups.append(current)
                for group in groups:
                    for index, (x, y0) in enumerate(group):
                        self.anchors.append({"u": x, "v": y0, "segment": segment, "start": index == 0,
                                             "end": index == len(group)-1, "pass_index": repeat,
                                             "row_fraction": index/max(1, len(group)-1)})
                    segment += 1
        if not self.anchors:
            raise ValueError("No usable three-point stroke: " + manifest["asset_id"])
        self.base_points, self.base_normals = zip(*(self.query(a["u"], a["v"]) for a in self.anchors))
        self.base_points = np.asarray(self.base_points)
        self.base_normals = np.asarray(self.base_normals)

    def query(self, u, v):
        coordinates = np.array([[(v-self.v[0])/self.dx], [(u-self.u[0])/self.dx]])
        def at(array):
            return float(map_coordinates(array, coordinates, order=1, mode="nearest")[0])
        normal = np.array([-at(self.du), -at(self.dv), 1.])
        normal /= np.linalg.norm(normal)
        return np.array([u, v, at(self.h)]), normal

    def valid(self, u, v):
        i, j = int(round((v-self.v[0])/self.dx)), int(round((u-self.u[0])/self.dx))
        return 0 <= i < len(self.v) and 0 <= j < len(self.u) and bool(self.safe[i, j])

    def connected(self, a, b):
        n = max(2, int(np.linalg.norm(np.asarray(b)-a)/(self.dx/2))+1)
        pts = np.linspace(a, b, n)
        ix = np.rint((pts[:, 0]-self.u[0])/self.dx).astype(int)
        iy = np.rint((pts[:, 1]-self.v[0])/self.dx).astype(int)
        if np.any(ix < 0) or np.any(ix >= len(self.u)) or np.any(iy < 0) or np.any(iy >= len(self.v)):
            return False
        return bool(self.safe[iy, ix].all())


class GeneralizedSprayEnv(gym.Env):
    """One full raster traversal per episode with bounded residual actions."""
    metadata = {"render_modes": []}

    def __init__(self, cases, training=False, seed=0, record=False):
        super().__init__()
        self.cases = cases
        self.training = training
        self.record = record
        self.rng = np.random.default_rng(seed)
        self.action_space = spaces.Box(-1., 1., shape=(2,), dtype=np.float32)
        self.observation_space = spaces.Box(-5., 5., shape=(70,), dtype=np.float32)
        self.case = cases[0]

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        if seed is not None: self.rng = np.random.default_rng(seed)
        self.case = self.cases[int(self.rng.integers(len(self.cases)))] if self.training else self.cases[0]
        self.index = 0
        self.dose = np.zeros_like(self.case.h, dtype=np.float64)
        self.last = np.zeros(2)
        self.previous = None
        self.previous_uv = None
        self.elapsed = 0.
        self.history = []
        self.paint_layers = []
        self.painted = np.zeros_like(self.case.mask)
        self.projections = 0
        self.flow_gain = float(self.rng.uniform(.55, 1.25)) if self.training else float(self.case.manifest.get("deposition_flow_gain", 1.))
        self.target = 2.2
        self.previous_mse = 1.
        self.episode_reward = 0.
        return self.observation(), {}

    def observation(self, legacy=False):
        case = self.case
        k = min(self.index, len(case.anchors)-1)
        a = case.anchors[k]
        point, normal = case.base_points[k], case.base_normals[k]
        i, j = int(round((a["v"]-case.v[0])/case.dx)), int(round((a["u"]-case.u[0])/case.dx))
        # A local slice avoids repeatedly copying/padding the full dose array.
        crop = np.zeros((7, 7))
        i0, i1 = max(0, i-3), min(len(case.v), i+4)
        j0, j1 = max(0, j-3), min(len(case.u), j+4)
        crop[i0-i+3:i1-i+3, j0-j+3:j1-j+3] = self.dose[i0:i1, j0:j1] / self.target
        shared = [*normal, self.index/len(case.anchors), float(a["start"]), float(a["end"]), *self.last]
        if legacy:
            features = [a["u"]/600, (a["v"]-750)/350, point[2]/900, *shared]
        else:
            region = case.roi
            mid_u = (region["u_min_mm"]+region["u_max_mm"])/2
            mid_v = (region["v_min_mm"]+region["v_max_mm"])/2
            features = [(a["u"]-mid_u)/max(1., (region["u_max_mm"]-region["u_min_mm"])/2),
                        (a["v"]-mid_v)/max(1., (region["v_max_mm"]-region["v_min_mm"])/2),
                        (point[2]-case.mean_h)/100, *shared,
                        case.process["spray_width_mm"]/240, case.process["overlap_ratio"],
                        case.process["speed_mm_s"]/400, case.sample_step/40, case.dx/5,
                        self.flow_gain, self.target/2.2,
                        case.edge_distance[i, j]/case.process["spray_width_mm"],
                        float(a["row_fraction"]),
                        0. if self.previous is None or a["start"] else float(np.linalg.norm(point-self.previous))/40]
        return np.clip(np.r_[features, crop.ravel()], -5, 5).astype(np.float32)

    def quality(self):
        case = self.case
        values = self.dose[case.mask]
        weights = case.area[case.mask]
        mean = float(np.average(values, weights=weights))
        return {"coverage_fraction": float(weights[values > .2].sum()/weights.sum()),
                "relative_dose_mean": mean,
                "relative_dose_cv": float(np.sqrt(np.average((values-mean)**2, weights=weights))/max(mean, 1e-8)),
                "target_normalized_rmse": float(np.sqrt(np.average(((values-self.target)/self.target)**2, weights=weights))),
                "within_20pct_target_fraction": float(weights[np.abs(values/self.target-1) <= .2].sum()/weights.sum()),
                "estimated_spray_seconds": self.elapsed, "evaluated_area_mm2": case.weight_sum,
                "boundary_projection_fraction": self.projections/max(1, self.index),
                "model": "geometric_relative_gaussian_v2", "physical_thickness_um": None,
                "scope": "Observed visible heightfield; uncalibrated relative deposition"}

    def step(self, action):
        case = self.case
        action = np.asarray(filter_policy_action(np.clip(action, -1, 1), self.last,
                           case.manifest.get("policy_action_filter", {"alpha": .22, "max_delta": .1})))
        a = case.anchors[self.index]
        v = a["v"] + 10*float(action[0])
        projected = not case.valid(a["u"], v)
        if projected: v = a["v"]
        if not a["end"]:
            next_anchor = case.anchors[self.index+1]
            if not case.connected((a["u"], v), (next_anchor["u"], next_anchor["v"])):
                v = a["v"]
                projected = True
        if self.previous_uv is not None and not a["start"] and not case.connected(self.previous_uv, (a["u"], v)):
            v = a["v"]
            projected = True
            if not case.connected(self.previous_uv, (a["u"], v)):
                raise TaskError("REGION_DISCONTINUITY", "Generalized policy would cross an unknown surface gap")
        point, normal = case.query(a["u"], v)
        speed = case.process["speed_mm_s"]*(1+.25*float(action[1]))
        reward = -.003*float(np.linalg.norm(action-self.last)) - (.04 if projected else 0.)
        if self.previous is not None and not a["start"]:
            dt = float(np.linalg.norm(point-self.previous))/speed
            self.elapsed += dt
            # Reference deposition rate is fixed: varying nominal speed cannot
            # cancel its effect on dwell time, unlike the legacy demonstration.
            gu = np.exp(-.5*((case.u-a["u"])/35.)**2)
            gv = np.exp(-.5*((case.v-v)/(case.process["spray_width_mm"]/4))**2)
            increment = np.multiply.outer(gv, gu) * case.mask * (dt*10*self.flow_gain)
            error = self.dose-self.target
            delta_mse = float(np.sum((2*error*increment + increment*increment)*case.weights)/(case.weight_sum*self.target**2))
            self.dose += increment
            reward += -150*delta_mse - .012*dt
            self.previous_mse += delta_mse
        self.projections += int(projected)
        if self.record:
            row = {**a, "step": self.index, "v": float(v), "surface_xyz_mm": point.tolist(),
                   "surface_normal": normal.tolist(), "speed_mm_s": float(speed),
                   "policy_action": action.tolist(), "projection_applied": projected}
            tilt = float(case.manifest.get("spray_tilt_deg", -10.))
            if tilt:
                tangent = np.array([1., 0., 0.])-normal*normal[0]
                tangent /= np.linalg.norm(tangent)
                row["spray_axis_normal"] = (normal*math.cos(math.radians(tilt))+tangent*math.sin(math.radians(tilt))).tolist()
            self.history.append(row)
            new = (self.dose > .2) & case.mask & ~self.painted
            self.painted |= new
            if new.any(): self.paint_layers.append({"step": self.index, "cells": np.argwhere(new).tolist()})
        self.previous, self.previous_uv, self.last = point, (a["u"], v), action
        self.index += 1
        terminated = self.index >= len(case.anchors)
        info = {}
        if terminated:
            quality = self.quality()
            reward -= 3*quality["target_normalized_rmse"] + quality["relative_dose_cv"] + 3*max(0., .98-quality["coverage_fraction"])
            info = {"quality": quality, "asset_id": case.manifest["asset_id"]}
        self.episode_reward += reward
        return self.observation(), float(reward), terminated, False, info


def plan_generalized(request, manifest, directory, region, context):
    import torch
    from stable_baselines3 import SAC
    torch.set_num_threads(2)
    profile = {**manifest, "allowed_roi": region}
    case = SurfaceCase(directory, profile, request.process.model_dump(), request.planning.sample_step_mm)
    env = GeneralizedSprayEnv([case], record=True)
    obs, _ = env.reset()
    model = SAC.load(pathlib.Path(directory)/manifest["policy_file"], device="cpu")
    if model.observation_space.shape != (70,):
        raise TaskError("POLICY_OBSERVATION_MISMATCH", "Expected version spray_v2_70")
    while True:
        context.check()
        action = model.predict(obs, deterministic=True)[0]
        obs, _, done, _, _ = env.step(action)
        if done: break
    quality = env.quality()
    # Keep the existing external quality contract; extended metrics are saved
    # by the evaluation tools without changing the v1 API response schema.
    quality = {key: value for key, value in quality.items() if key not in
               ("target_normalized_rmse", "within_20pct_target_fraction", "boundary_projection_fraction")}
    return {"history": env.history, "moves": make_moves(env.history, request), "quality": quality,
            "paint_layers": env.paint_layers, "relative_dose": env.dose, "coating_mask": case.mask,
            "planner": "sac", "warnings": ["Multi-surface research SAC; uncalibrated geometric deposition, not physical film thickness",
            "The training environment does not perform E12 kinematics; all robot paths still require the existing RoboDK checks"]}
