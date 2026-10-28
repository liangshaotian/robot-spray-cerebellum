"""Prepare a manually selected door panel from the existing full-resolution scan."""
import pathlib,json,os,shutil,time
import numpy as np
import trimesh
from scipy.ndimage import gaussian_filter,distance_transform_edt,binary_erosion
from matplotlib.path import Path
from spray_cerebellum.common import REPO,atomic_json,read_json
from spray_cerebellum.demo_setup import install_precise_demo

def main():
    root=REPO/'.local/assets';source=install_precise_demo();destination=root/'artec_e350_door_v2'
    destination.mkdir(exist_ok=True)
    mesh_name='car_body_highres_smooth.ply'
    if not (destination/mesh_name).exists():
        try:os.link(source/mesh_name,destination/mesh_name)
        except OSError:shutil.copy2(source/mesh_name,destination/mesh_name)
    mesh=trimesh.load(source/mesh_name,process=False);vertices=np.asarray(mesh.vertices);faces=np.asarray(mesh.faces)
    u=np.arange(-1020.,221.,5.);v=np.arange(80.,801.,5.);U,V=np.meshgrid(u,v)
    triangles=vertices[faces]
    candidate=(triangles[:,:,0].max(1)>=u[0])&(triangles[:,:,0].min(1)<=u[-1])
    candidate&=(triangles[:,:,1].max(1)>=v[0])&(triangles[:,:,1].min(1)<=v[-1])
    candidate&=triangles[:,:,2].min(1)>650
    selected=triangles[candidate];h=np.full(U.shape,-np.inf)
    started=time.monotonic()
    for count,t in enumerate(selected):
        if count%50000==0:print('RASTER',count,len(selected),flush=True)
        lo=np.ceil((t[:,:2].min(0)-[u[0],v[0]])/5).astype(int)
        hi=np.floor((t[:,:2].max(0)-[u[0],v[0]])/5).astype(int)
        x0,y0=np.maximum(lo,[0,0]);x1,y1=np.minimum(hi,[len(u)-1,len(v)-1])
        if x1<x0 or y1<y0:continue
        a,b,c=t;den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(den)<1e-8:continue
        X=U[y0:y1+1,x0:x1+1];Y=V[y0:y1+1,x0:x1+1]
        w0=((b[1]-c[1])*(X-c[0])+(c[0]-b[0])*(Y-c[1]))/den
        w1=((c[1]-a[1])*(X-c[0])+(a[0]-c[0])*(Y-c[1]))/den
        w2=1-w0-w1;inside=(w0>=-1e-6)&(w1>=-1e-6)&(w2>=-1e-6)
        z=w0*a[2]+w1*b[2]+w2*c[2]
        old=h[y0:y1+1,x0:x1+1];np.maximum(old,np.where(inside,z,-np.inf),out=old)
    observed=np.isfinite(h)
    if not observed.all():
        nearest=distance_transform_edt(~observed,return_distances=False,return_indices=True)
        h=np.where(observed,h,h[tuple(nearest)])
    # The original mesh and raw sampled depth remain unchanged. Only the
    # planning support surface is smoothed to reject scan noise and trim ridges.
    path_h=gaussian_filter(h,sigma=5.,mode='nearest')
    dv,du=np.gradient(path_h,5.,5.)
    polygon=[[-885.,125.],[120.,125.],[120.,720.],[-800.,705.],[-865.,610.],[-900.,450.],[-900.,260.]]
    panel=Path(polygon).contains_points(np.c_[U.ravel(),V.ravel()],radius=.01).reshape(U.shape)
    safe=binary_erosion(observed,iterations=1)&panel&(np.hypot(du,dv)<.8)
    # Manual masking of the scanned handle, as in a panel repair demonstration.
    handle=((U-25.)/125.)**2+((V-620.)/29.)**2<1
    coverage_mask=safe&(~handle)
    area=25*np.sqrt(1+du**2+dv**2)
    np.savez_compressed(destination/'surface.npz',u=u,v=v,h=h,path_h=path_h,du=du,dv=dv,
        observed=observed,safe=safe,coverage_mask=coverage_mask,area=area)
    manifest=read_json(source/'manifest.json')
    manifest.update(asset_id='artec_e350_door_v2',policy_id=None,policy_file=None,
        allowed_roi={'u_min_mm':-900.,'u_max_mm':120.,'v_min_mm':125.,'v_max_mm':720.},
        target_polygon_uv_mm=polygon,policy_action_filter={'alpha':.22,'max_delta':.10},
        spray_tilt_deg=-10.,
        station_title='E12 | E350 front-door spray',
        presentation={'paint_offset_mm':1.2,'camera_eye_mm':[-3700.,1800.,1800.],
                      'camera_target_mm':[1000.,400.,620.]},
        planning_surface='25 mm Gaussian support smoothing; original raw mesh retained for collisions',
        target_selection='Manually selected front-door body panel; windows, seams and handle excluded from coating evaluation')
    atomic_json(destination/'manifest.json',manifest)
    metadata=read_json(source/'source_metadata.json');metadata.update(asset_id=manifest['asset_id'],
        selection=manifest['target_selection'],original_scan_unchanged=True,planning_normal_smoothing_mm=25.)
    atomic_json(destination/'source_metadata.json',metadata)
    print('PREPARED',json.dumps({'seconds':round(time.monotonic()-started,2),'triangles_sampled':len(selected),
        'observed_cells':int(observed.sum()),'safe_cells':int(safe.sum()),'coating_cells':int(coverage_mask.sum())}),flush=True)

if __name__=='__main__':main()
