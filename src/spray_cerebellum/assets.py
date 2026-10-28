from __future__ import annotations
import pathlib,threading,shutil
from .common import DEMO,TaskError,read_json,atomic_json

DEMO_MANIFEST={
 "asset_id":"demo_car_4500","kind":"observed_heightfield","units":"mm",
 "source":"Real3D-AD real optical scan of a small car-shaped physical object, affine-scaled for full-size demonstration",
 "surface_file":"data/surface.npz","mesh_file":"assets/real_scan_car.stl",
 "policy_id":"sac_car_side_v1","policy_file":"models/sac_car_side_v1.zip",
 "allowed_roi":{"u_min_mm":-500.,"u_max_mm":500.,"v_min_mm":500.,"v_max_mm":1000.},
 "T_robot_base_workpiece":[[0.,0.,-1.,2000.],[-1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,0.,1.]],
 "axis_convention":{"u":"vehicle length","v":"height above floor","h":"outward side depth, +Z in workpiece frame"},
 "collision_scope":"Observed front and back scan envelope plus floor, robot self-collision and nozzle",
 "dimensions_length_width_height_mm":[4500.,1798.06,1500.]}

class AssetRegistry:
    def __init__(self,state_dir,demo_dir=DEMO):
        self.root=pathlib.Path(state_dir)/"assets";self.root.mkdir(parents=True,exist_ok=True)
        self.demo=pathlib.Path(demo_dir);self.lock=threading.RLock()
    def get(self,asset_id):
        if asset_id=="demo_car_4500":return dict(DEMO_MANIFEST),self.demo
        path=self.root/asset_id/"manifest.json"
        if not path.is_file():raise TaskError("ASSET_NOT_FOUND",f"Asset {asset_id!r} is not registered")
        return read_json(path),path.parent
    def list(self):
        rows=[dict(DEMO_MANIFEST)]
        rows.extend(read_json(p) for p in sorted(self.root.glob("*/manifest.json")))
        return rows
    def import_cloud(self,metadata,filename,content):
        with self.lock:
            destination=self.root/metadata.asset_id
            if metadata.asset_id=="demo_car_4500" or destination.exists():
                raise TaskError("ASSET_EXISTS","Choose a new asset_id; existing assets are immutable")
            staging=self.root/(metadata.asset_id+".staging")
            staging.mkdir(exist_ok=False)
            try:
                from .cloud import import_cloud
                manifest=import_cloud(metadata,filename,content,staging)
                atomic_json(staging/"manifest.json",manifest)
                staging.rename(destination)
            except Exception:
                if staging.resolve().parent!=self.root.resolve():raise RuntimeError('Refusing cleanup outside asset staging root')
                shutil.rmtree(staging)
                raise
            return manifest

def validate_asset_request(request,registry):
    if request.robot.model_id!="huayan_e12":raise TaskError("ROBOT_NOT_SUPPORTED","Registered robot model_id is huayan_e12")
    manifest,directory=registry.get(request.target.asset_id)
    region=request.target.region_uv_mm.model_dump() if request.target.region_uv_mm else dict(manifest["allowed_roi"])
    allowed=manifest["allowed_roi"]
    if region["u_min_mm"]<allowed["u_min_mm"] or region["u_max_mm"]>allowed["u_max_mm"] or region["v_min_mm"]<allowed["v_min_mm"] or region["v_max_mm"]>allowed["v_max_mm"]:
        raise TaskError("REGION_OUT_OF_BOUNDS","Requested UV region is outside the registered usable surface",{"allowed_roi":allowed})
    if request.execution.backend=="robodk" and request.planning.method=="sac" and manifest.get("policy_id")!=request.planning.policy_id:
        raise TaskError("POLICY_ASSET_MISMATCH","No SAC policy is registered for this asset; use raster or train/register a matching policy")
    return manifest,directory,region
