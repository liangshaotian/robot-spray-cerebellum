from __future__ import annotations
import math,pathlib
from .common import TaskError,make_moves,filter_policy_action

def mock_plan(request,manifest,region,context):
    """Protocol fixture, deliberately makes no reachability/coverage claim."""
    history=[];segment=0;step=0
    for repeat in range(request.process.passes):
        for row in range(3):
            v=region['v_min_mm']+(row+.5)*(region['v_max_mm']-region['v_min_mm'])/3
            us=[region['u_min_mm']+i*(region['u_max_mm']-region['u_min_mm'])/4 for i in range(5)]
            if row%2:us.reverse()
            for i,u in enumerate(us):
                context.check()
                history.append({'step':step,'segment':segment,'start':i==0,'end':i==len(us)-1,
                    'surface_xyz_mm':[u,v,750.],'surface_normal':[0.,0.,1.],
                    'speed_mm_s':request.process.speed_mm_s,'policy_action':None,'pass_index':repeat})
                step+=1
            segment+=1
    return {'history':history,'moves':make_moves(history,request),'quality':None,
      'planner':'mock_fixture','warnings':['MOCK: fixture path, no RL inference, robot motion, collision or coating validation']}

def plan_surface(request,manifest,directory,region,context):
    try:
        import numpy as np
        from scipy.ndimage import map_coordinates
    except ImportError as e:raise TaskError('DEPENDENCY_MISSING','Install geometry extras for real surface planning') from e
    path=directory/manifest['surface_file']
    if not path.is_file():raise TaskError('ASSET_FILE_MISSING','Registered surface file is missing')
    with np.load(path,allow_pickle=False) as stored:
        surface={key:stored[key] for key in stored.files}
    u=surface['u'];v=surface['v'];h=surface['h'];du=surface['du'];dv=surface['dv'];dx=float(u[1]-u[0])
    path_h=surface.get('path_h',h)
    U,V=np.meshgrid(u,v);safe=surface['safe'].astype(bool).copy();area=surface['area']
    safe&=(U>=region['u_min_mm'])&(U<=region['u_max_mm'])&(V>=region['v_min_mm'])&(V<=region['v_max_mm'])
    coating_mask=safe&surface.get('coverage_mask',safe).astype(bool)
    if safe.sum()<8:raise TaskError('NO_USABLE_SURFACE','Requested region contains fewer than 8 reliable cells')
    def valid(x,y):
        i=int(round((y-v[0])/dx));j=int(round((x-u[0])/dx))
        return 0<=i<len(v) and 0<=j<len(u) and bool(safe[i,j])
    def query(x,y):
        co=np.array([[(y-v[0])/dx],[(x-u[0])/dx]])
        def at(a):return float(map_coordinates(a.astype(float),co,order=1,mode='nearest')[0])
        n=np.array([-at(du),-at(dv),1.]);n/=np.linalg.norm(n)
        return np.array([x,y,at(path_h)]),n
    def connected(a,b):
        steps=max(2,int(np.linalg.norm(np.asarray(b)-a)/(dx/2))+1)
        return all(valid(float(p[0]),float(p[1])) for p in np.linspace(a,b,steps))
    spacing=request.process.spray_width_mm*(1-request.process.overlap_ratio)
    sample=request.planning.sample_step_mm
    ys=np.arange(region['v_min_mm']+min(30.,(region['v_max_mm']-region['v_min_mm'])/2),region['v_max_mm'],spacing)
    xs=np.arange(region['u_min_mm']+min(20.,sample/2),region['u_max_mm'],sample)
    if len(ys)*len(xs)*request.process.passes>3000:raise TaskError('TASK_TOO_LARGE','Use a smaller ROI, larger spacing or fewer passes; maximum 3000 sampled points')
    anchors=[];segment=0
    for repeat in range(request.process.passes):
        for row,y in enumerate(ys):
            groups=[];current=[]
            for x in (xs[::-1] if row%2 else xs):
                if valid(x,y):
                    if current and not connected(current[-1],(x,y)):
                        if len(current)>=3:groups.append(current)
                        current=[]
                    current.append((float(x),float(y)))
                else:
                    if len(current)>=3:groups.append(current)
                    current=[]
            if len(current)>=3:groups.append(current)
            for group in groups:
                for i,(x,y0) in enumerate(group):anchors.append({'u':x,'v':y0,'segment':segment,'start':i==0,'end':i==len(group)-1,'pass_index':repeat})
                segment+=1
    if not anchors:raise TaskError('NO_USABLE_PATH','No connected spray stroke of at least 3 samples exists in this region')
    model=None
    if request.planning.method=='sac':
        try:
            import torch
            from stable_baselines3 import SAC
        except ImportError as e:raise TaskError('DEPENDENCY_MISSING','Install rl extras for SAC inference') from e
        model_path=directory/manifest['policy_file']
        if not model_path.is_file():raise TaskError('POLICY_FILE_MISSING','Registered SAC checkpoint is missing')
        torch.set_num_threads(2);model=SAC.load(model_path,device='cpu')
    dose=np.zeros_like(h);history=[];last=np.zeros(2);previous=None;elapsed=0.;painted=np.zeros_like(safe);paint_layers=[]
    for index,a in enumerate(anchors):
        context.check();p,n=query(a['u'],a['v'])
        action=np.zeros(2)
        if model is not None:
            i=int(round((a['v']-v[0])/dx));j=int(round((a['u']-u[0])/dx))
            crop=np.pad(dose/2.2,3)[i:i+7,j:j+7].ravel()
            features=np.array([a['u']/600,(a['v']-750)/350,p[2]/900,*n,index/len(anchors),float(a['start']),float(a['end']),*last])
            obs=np.clip(np.r_[features,crop],-5,5).astype(np.float32)
            action=np.clip(model.predict(obs,deterministic=True)[0],-1,1)
            action=np.asarray(filter_policy_action(action,last,manifest.get('policy_action_filter')))
        y=a['v']+10*float(action[0]);projected=not valid(a['u'],y)
        if projected:y=a['v']
        if history and not a['start'] and not connected((history[-1]['u'],history[-1]['v']),(a['u'],y)):
            y=a['v'];projected=True
            if not connected((history[-1]['u'],history[-1]['v']),(a['u'],y)):
                raise TaskError('REGION_DISCONTINUITY','Policy residual would cross an unknown or excluded surface region')
        p,n=query(a['u'],y);speed=request.process.speed_mm_s*(1+.25*float(action[1])) if model is not None else request.process.speed_mm_s
        if previous is not None and not a['start']:
            dt=float(np.linalg.norm(p-previous))/speed;elapsed+=dt
            dose+=np.exp(-.5*(((U-a['u'])/35.)**2+((V-y)/(request.process.spray_width_mm/4))**2))*coating_mask*dt*request.process.speed_mm_s/sample
        history.append({**a,'step':index,'v':y,'surface_xyz_mm':p.tolist(),'surface_normal':n.tolist(),
            'speed_mm_s':float(speed),'policy_action':action.tolist(),'projection_applied':projected})
        tilt=float(manifest.get('spray_tilt_deg',0.))
        if tilt:
            tangent=np.array([1.,0.,0.])-n*n[0];tangent/=np.linalg.norm(tangent)
            history[-1]['spray_axis_normal']=(n*math.cos(math.radians(tilt))+tangent*math.sin(math.radians(tilt))).tolist()
        new=(dose>.2)&coating_mask&(~painted);painted|=new
        if np.any(new):paint_layers.append({'step':index,'cells':np.argwhere(new).tolist()})
        previous=p;last=action
    weight=area[coating_mask];values=dose[coating_mask];mean=float(np.average(values,weights=weight))
    quality={'coverage_fraction':float(weight[values>.2].sum()/weight.sum()),
        'relative_dose_mean':mean,'relative_dose_cv':float(np.sqrt(np.average((values-mean)**2,weights=weight))/max(mean,1e-8)),
        'estimated_spray_seconds':elapsed,'evaluated_area_mm2':float(weight.sum()),'model':'geometric_relative_gaussian',
        'physical_thickness_um':None,'scope':'Requested reliable observed heightfield cells only'}
    warnings=['Relative coating model is uncalibrated; pressure and true film thickness are not simulated']
    if manifest.get('spray_tilt_deg'):
        warnings.append('Registered asset uses a '+str(manifest['spray_tilt_deg'])+' degree tangential spray-axis tilt; standoff is measured along the spray axis')
    return {'history':history,'moves':make_moves(history,request),'quality':quality,'paint_layers':paint_layers,
        'relative_dose':dose,'coating_mask':coating_mask,
        'planner':request.planning.method,'warnings':warnings}
