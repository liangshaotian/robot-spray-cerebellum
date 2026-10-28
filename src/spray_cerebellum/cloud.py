"""Explicit-unit XYZ/PLY/PCD import for a nominated visible heightfield surface."""
from __future__ import annotations
import pathlib,io,hashlib
import numpy as np
from scipy import ndimage
import trimesh
from .common import TaskError

def xyz_from_bytes(filename,content):
    ext=pathlib.Path(filename).suffix.lower()
    if ext==".ply":
        cloud=trimesh.load(io.BytesIO(content),file_type="ply",process=False)
        points=np.asarray(cloud.vertices,dtype=float)
    elif ext==".pcd":
        stream=io.BytesIO(content);header={}
        for _ in range(100):
            line=stream.readline()
            if not line:raise TaskError("INVALID_POINT_CLOUD","PCD header has no DATA line")
            text=line.decode("ascii",errors="strict").strip()
            if not text or text.startswith("#"):continue
            key,*values=text.split();header[key.upper()]=values
            if key.upper()=="DATA":break
        else:raise TaskError("INVALID_POINT_CLOUD","PCD header is too long")
        fields=header.get("FIELDS",[])
        if not all(k in fields for k in ("x","y","z")):raise TaskError("INVALID_POINT_CLOUD","PCD must contain x,y,z fields")
        sizes=list(map(int,header.get("SIZE",["4"]*len(fields))));types=header.get("TYPE",["F"]*len(fields))
        counts=list(map(int,header.get("COUNT",["1"]*len(fields))))
        n=int(header.get("POINTS",[str(int(header.get("WIDTH",["0"])[0])*int(header.get("HEIGHT",["1"])[0]))])[0])
        if not 16<=n<=2_000_000:raise TaskError("INVALID_POINT_CLOUD","PCD point count must be 16..2000000")
        if header["DATA"]==["binary"]:
            kinds={"F":"f","I":"i","U":"u"}
            dtype=np.dtype([(name,"<"+kinds[t]+str(size),(count,)) if count>1 else (name,"<"+kinds[t]+str(size)) for name,t,size,count in zip(fields,types,sizes,counts)])
            body=stream.read()
            if len(body)!=n*dtype.itemsize:raise TaskError("INVALID_POINT_CLOUD","PCD binary payload size disagrees with header")
            data=np.frombuffer(body,dtype=dtype,count=n)
            points=np.column_stack([data[k] for k in ("x","y","z")]).astype(float)
        elif header["DATA"]==["ascii"]:
            data=np.loadtxt(stream,dtype=float,ndmin=2)
            if data.shape!=(n,sum(counts)):raise TaskError("INVALID_POINT_CLOUD","PCD ASCII shape disagrees with header")
            offsets=np.cumsum([0]+counts[:-1]);points=data[:,[offsets[fields.index(k)] for k in ("x","y","z")]]
        else:raise TaskError("FORMAT_NOT_SUPPORTED","Only PCD ascii and binary are supported; binary_compressed is not supported")
    elif ext in (".xyz",".txt",".csv"):
        data=np.loadtxt(io.BytesIO(content),delimiter="," if ext==".csv" else None,ndmin=2)
        points=data[:,:3]
    else:raise TaskError("FORMAT_NOT_SUPPORTED","Upload .ply, .pcd, .xyz, .txt or numeric .csv")
    if points.ndim!=2 or points.shape[1]!=3 or not 16<=len(points)<=2_000_000 or not np.isfinite(points).all():
        raise TaskError("INVALID_POINT_CLOUD","Expected 16..2000000 finite XYZ points")
    return points

def import_cloud(metadata,filename,content,directory):
    points=xyz_from_bytes(filename,content)
    if metadata.input_units=="m":points=points*1000
    transform=np.asarray(metadata.T_workpiece_input)
    points=points@transform[:3,:3].T+transform[:3,3]
    dx=metadata.grid_mm
    lo=np.floor(points.min(0)/dx)*dx;hi=np.ceil(points.max(0)/dx)*dx
    dims=np.rint((hi[:2]-lo[:2])/dx).astype(int)+1
    if np.any(dims<3) or int(np.prod(dims))>200_000:
        raise TaskError("GEOMETRY_NOT_SUPPORTED","UV grid must contain 3..200000 cells; check units, transform, ROI and grid_mm")
    u=np.arange(dims[0])*dx+lo[0];v=np.arange(dims[1])*dx+lo[1];U,V=np.meshgrid(u,v)
    ix=np.clip(np.rint((points[:,0]-u[0])/dx).astype(int),0,len(u)-1)
    iy=np.clip(np.rint((points[:,1]-v[0])/dx).astype(int),0,len(v)-1)
    front=np.full(U.shape,-np.inf);counts=np.zeros(U.shape)
    np.maximum.at(front,(iy,ix),points[:,2]);np.add.at(counts,(iy,ix),1)
    observed=counts>=1
    weight=ndimage.gaussian_filter(observed.astype(float),.75)
    h=ndimage.gaussian_filter(np.where(observed,front,0),.75)/np.maximum(weight,1e-8)
    dv,du=np.gradient(h,dx)
    safe=ndimage.binary_erosion(observed)&(du**2+dv**2<.75**2)
    region=metadata.region_uv_mm.model_dump() if metadata.region_uv_mm else {"u_min_mm":float(u[0]+dx),"u_max_mm":float(u[-1]-dx),"v_min_mm":float(v[0]+dx),"v_max_mm":float(v[-1]-dx)}
    safe&=(U>=region["u_min_mm"])&(U<=region["u_max_mm"])&(V>=region["v_min_mm"])&(V<=region["v_max_mm"])
    if safe.sum()<16:raise TaskError("NO_USABLE_SURFACE","Fewer than 16 reliable heightfield cells in the requested region")
    vertices=np.column_stack([U.ravel(),V.ravel(),h.ravel()]);faces=[]
    for i in range(len(v)-1):
        for j in range(len(u)-1):
            if not observed[i:i+2,j:j+2].all():continue
            a=i*len(u)+j;b=a+1;c=a+len(u);d=c+1;faces.extend([[a,b,d],[a,d,c]])
    trimesh.Trimesh(vertices=vertices,faces=np.asarray(faces),process=False).export(directory/"surface.stl")
    np.savez_compressed(directory/"surface.npz",u=u,v=v,h=h,du=du,dv=dv,observed=observed,safe=safe,area=dx*dx*np.sqrt(1+du**2+dv**2))
    return {"asset_id":metadata.asset_id,"kind":"observed_heightfield","units":"mm","point_count":len(points),
      "source_sha256":hashlib.sha256(content).hexdigest(),"surface_file":"surface.npz","mesh_file":"surface.stl",
      "input_units":metadata.input_units,"T_workpiece_input":metadata.T_workpiece_input,
      "T_robot_base_workpiece":metadata.T_robot_base_workpiece,"allowed_roi":region,"grid_mm":dx,
      "policy_id":None,"collision_scope":"Observed visible surface mesh only, plus robot self-collision and floor; unobserved volume is unknown",
      "assumption":"Caller nominates a visible, single-valued h(u,v) surface; no general whole-object segmentation or overhang handling"}
