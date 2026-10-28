from __future__ import annotations
import os,pathlib,socket,subprocess,time,math,json
from .common import TaskError,DEMO
from .planning import mock_plan,plan_surface

def run_mock(request,manifest,directory,region,context):
    context.update('planning',.1,'Generating protocol fixture')
    plan=mock_plan(request,manifest,region,context)
    context.trajectory(plan['moves'])
    if request.execution.mode=='simulate':
        for i in range(len(plan['moves'])):
            context.check();time.sleep(.012)
            context.update('simulating',.2+.7*(i+1)/len(plan['moves']),'Mock execution; no simulator or hardware')
    return {'planner':'mock_fixture','validation':{'passed':False,'reachable':None,'collision_free':None,'executable':False,'scope':'Not checked in mock mode'},
        'quality':None,'execution':{'requested':request.execution.mode=='simulate','completed':request.execution.mode=='simulate','executed_in_simulator':False,'waypoints_executed':0},
        'warnings':plan['warnings'],'waypoint_count':len(plan['moves'])}

def _connect():
    try:from robodk.robolink import Robolink,RUNMODE_SIMULATE
    except ImportError as e:raise TaskError('DEPENDENCY_MISSING','Install robodk extras') from e
    port=int(os.environ.get('ROBODK_PORT','20721'))
    host=os.environ.get('ROBODK_HOST','127.0.0.1')
    configured=os.environ.get('ROBODK_EXE')
    candidates=[pathlib.Path(configured)] if configured else [pathlib.Path(p) for p in [r'C:\RoboDK\bin\RoboDK.exe',r'D:\RoboDK5.9\bin\RoboDK.exe',r'D:\RoboDK\bin\RoboDK.exe']]
    executable=next((p for p in candidates if p.is_file()),None)
    def listening():
        try:
            with socket.create_connection((host,port),timeout=.25):return True
        except OSError:return False
    if not listening():
        if executable is None or host not in ('localhost','127.0.0.1'):
            raise TaskError('ROBODK_UNAVAILABLE','Start RoboDK API at configured ROBODK_HOST/ROBODK_PORT, or set ROBODK_EXE')
        options={'cwd':str(executable.parent.parent),'stdin':subprocess.DEVNULL,'stdout':subprocess.DEVNULL,'stderr':subprocess.DEVNULL}
        if os.name=='nt':
            options['creationflags']=subprocess.DETACHED_PROCESS|subprocess.CREATE_NEW_PROCESS_GROUP
            options['startupinfo']=subprocess.STARTUPINFO();options['startupinfo'].dwFlags|=subprocess.STARTF_USESHOWWINDOW;options['startupinfo'].wShowWindow=6
        else:options['start_new_session']=True
        subprocess.Popen([str(executable),'-NEWINSTANCE','-NOSPLASH','-PORT='+str(port)],**options)
        deadline=time.monotonic()+40
        while not listening():
            if time.monotonic()>deadline:raise TaskError('ROBODK_UNAVAILABLE','RoboDK API did not become ready within 40 seconds')
            time.sleep(.2)
    r=Robolink(robodk_ip=host,port=port,robodk_path=str(executable) if executable else None)
    r.COM.settimeout(20);r.TIMEOUT=20;r.setRunMode(RUNMODE_SIMULATE)
    return r

def run_robodk(request,manifest,directory,region,context):
    import numpy as np
    try:
        from robodk.robolink import ITEM_TYPE_ROBOT,ITEM_TYPE_OBJECT,RUNMODE_SIMULATE,COLLISION_ON,COLLISION_OFF,PROJECTION_NONE,WINDOWSTATE_MAXIMIZED
        from robodk.robomath import Mat,transl,invH
    except ImportError as e:raise TaskError('DEPENDENCY_MISSING','Install robodk extras') from e
    context.update('planning',.03,'Inferring surface trajectory')
    plan=plan_surface(request,manifest,directory,region,context);moves=plan['moves']
    context.trajectory(moves)
    robot_file=pathlib.Path(os.environ.get('E12_ROBOT_FILE',str(DEMO/'assets/Han-s-E12.robot')))
    if not robot_file.is_file():raise TaskError('ROBOT_ASSET_MISSING','Run python tools/fetch_robot.py to download the official E12 model')
    r=None;robot=None
    try:
        r=_connect();context.check();r.Render(False)
        name='Cerebellum | '+request.task_id
        for old in r.getOpenStations():
            if old.Name()==name:old.Delete()
        station=r.AddStation(name);r.setActiveStation(station)
        robot=r.AddFile(str(robot_file),station)
        if not robot.Valid():raise TaskError('ROBOT_LOAD_FAILED','Official E12 model did not load')
        robot.setName('Huayan E12 - original dimensions')
        frame=r.AddFrame('Task workpiece',station)
        transform=request.target.T_robot_base_workpiece or manifest['T_robot_base_workpiece']
        frame.setPose(Mat(transform))
        part=r.AddFile(str(directory/manifest['mesh_file']),frame);part.setName('Registered observed surface')
        part.Recolor([.5,.54,.59,1])
        def box(x0,x1,y0,y1,z0,z1):
            p=[(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),(x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]
            fs=[(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
            return Mat([list(p[i]) for f in fs for i in f]).tr()
        floor=r.AddShape(box(-1600,4200,-3000,3000,-80,-20));floor.setParent(station);floor.setName('Floor');floor.Recolor([.23,.27,.31,1])
        tool=robot.AddTool(transl(0,0,200),'Spray TCP +Z 200 mm')
        # Geometric nozzle with the same physical TCP as the profile.
        vertices=[]
        for j in range(16):
            a=2*math.pi*j/16;b=2*math.pi*(j+1)/16
            vertices.extend([[22*math.cos(a),22*math.sin(a),40],[22*math.cos(b),22*math.sin(b),40],[4*math.cos(b),4*math.sin(b),200],
                             [22*math.cos(a),22*math.sin(a),40],[4*math.cos(b),4*math.sin(b),200],[4*math.cos(a),4*math.sin(a),200]])
        r.AddShape(Mat(vertices).tr(),tool);tool.Recolor([.05,.42,.7,1]);robot.setPoseTool(tool);robot.setPoseFrame(frame);robot.setRounding(0)
        r.Command('CollisionMap','None')
        for obstacle in (part,floor):
            for link in range(7):r.setCollisionActivePair(COLLISION_ON,robot,obstacle,link,0)
            r.setCollisionActivePair(COLLISION_ON,tool,obstacle)
        for i in range(7):
            for j in range(i+2,7):r.setCollisionActivePair(COLLISION_ON,robot,robot,i,j)
        for i in range(5):r.setCollisionActivePair(COLLISION_ON,robot,tool,i,0)
        r.setCollisionActive(COLLISION_ON);r.Update()
        reference=invH(robot.PoseAbs())*frame.PoseAbs()
        lo,hi,_=robot.JointLimits();lo=lo.list()[:6];hi=hi.list()[:6]
        q=[-135.9,3.,-119.9,86.,76.9,30.5]
        def pose(m):return Mat([m['rotation_matrix'][i]+[m['nozzle_xyz_mm'][i]] for i in range(3)]+[[0,0,0,1]])
        for i,m in enumerate(moves):
            context.check()
            result=robot.SolveIK(pose(m),q,tool=tool.PoseTool(),reference=reference).list()[:6]
            if len(result)!=6:raise TaskError('UNREACHABLE','No E12 inverse kinematics solution',{'waypoint':i})
            normalized=[]
            for value,previous,lower,upper in zip(result,q,lo,hi):
                candidates=[value+360*k for k in range(-3,4) if lower-1e-6<=value+360*k<=upper+1e-6]
                if not candidates:raise TaskError('JOINT_LIMIT','Joint limit exceeded',{'waypoint':i})
                normalized.append(float(min(candidates,key=lambda a:abs(a-previous))))
            if m['motion']=='MoveL' and max(abs(a-b) for a,b in zip(normalized,q))>120:
                raise TaskError('IK_BRANCH_DISCONTINUITY','Linear motion changes IK branch',{'waypoint':i})
            m['joints_deg']=normalized;q=normalized
        context.update('validating',.2,'Checking every E12 path segment and mapped collision pair')
        q=moves[0]['joints_deg'];checks=[]
        for i,m in enumerate(moves):
            context.check();robot.setJoints(q)
            code=robot.MoveJ_Test(q,m['joints_deg'],minstep_deg=1) if m['motion']=='MoveJ' else robot.MoveL_Test(q,pose(m),minstep_mm=5)
            checks.append({'id':i,'code':int(code)})
            if code!=0:raise TaskError('PATH_VALIDATION_FAILED','Collision or inaccessible motion detected',{'waypoint':i,'robodk_code':int(code)})
            q=m['joints_deg']
            if i%10==0:context.update('validating',.2+.3*(i+1)/len(moves),'Checking path segment '+str(i+1))
        for m in moves:
            a=np.array(transform)@np.r_[m['nozzle_xyz_mm'],1.]
            m['nozzle_xyz_robot_base_mm']=a[:3].tolist()
            m['rotation_matrix_robot_base']=(np.array(transform)[:3,:3]@np.array(m['rotation_matrix'])).tolist()
        context.trajectory(moves);context.artifact('validation.json',{'passed':True,'checks':checks,'sampling_mm':5,'sampling_deg':1})
        paint_by_step={}
        if request.execution.mode=='simulate':
            surface=np.load(directory/manifest['surface_file'],allow_pickle=False)
            for layer in plan['paint_layers']:
                vertices=[]
                for iy,ix in layer['cells']:
                    if iy+1>=len(surface['v']) or ix+1>=len(surface['u']) or not surface['observed'][iy:iy+2,ix:ix+2].all():continue
                    corners=[]
                    for dy,dx in ((0,0),(0,1),(1,1),(1,0)):
                        i=iy+dy;j=ix+dx;n=np.array([-surface['du'][i,j],-surface['dv'][i,j],1.]);n/=np.linalg.norm(n)
                        p=np.array([surface['u'][j],surface['v'][i],surface['h'][i,j]])+5*n
                        corners.append(p.tolist())
                    vertices.extend(corners[k] for k in (0,1,2,0,2,3))
                if vertices:
                    obj=r.AddShape(Mat(vertices).tr());obj.setParent(frame);obj.setName('Relative coverage '+str(layer['step']))
                    obj.Recolor([.06,.52,.92,1]);obj.setVisible(False);paint_by_step[layer['step']]=obj
        groups={}
        for m in moves:
            if m['kind']=='entry' or m['spray_on']:groups.setdefault(m['segment'],[]).append(m['nozzle_xyz_mm'])
        curves=r.AddCurve([Mat(g).tr() for g in groups.values() if len(g)>1],0,False,PROJECTION_NONE)
        curves.setParent(frame);curves.setName('Task spray TCP path');curves.setColor([1,.83,.08,1])
        robot.setJoints(moves[0]['joints_deg']);r.setSelection([]);frame.setVisible(False);tool.setVisible(True,False)
        # View pose is a world->camera transform; no geometry is scaled.
        eye=np.array([-4500.,-2100.,1900.]);target=np.array([1600.,0.,700.]);z=eye-target;z/=np.linalg.norm(z)
        x=np.cross([0.,0.,1.],z);x/=np.linalg.norm(x);y=np.cross(z,x);R=np.array([x,y,z]);camera=np.eye(4);camera[:3,:3]=R;camera[:3,3]=-R@eye
        r.setViewPose(Mat(camera.tolist()));r.Render(True)
        if request.execution.show_window:r.setWindowState(WINDOWSTATE_MAXIMIZED)
        execution={'requested':request.execution.mode=='simulate','completed':False,'executed_in_simulator':False,'waypoints_executed':0}
        if request.execution.mode=='simulate':
            r.setRunMode(RUNMODE_SIMULATE);r.setSimulationSpeed(request.execution.simulation_speed)
            max_error=0.
            for i,m in enumerate(moves):
                context.check();robot.setSpeed(m['speed_mm_s'],60,600,120)
                if m['motion']=='MoveJ':robot.MoveJ(m['joints_deg'],blocking=False)
                else:robot.MoveL(pose(m),blocking=False)
                while robot.Busy():context.check();time.sleep(.04)
                actual=robot.Pose().Pos();error=float(np.linalg.norm(np.array(actual)-m['nozzle_xyz_mm']));max_error=max(max_error,error)
                if error>.1:raise TaskError('TRACKING_ERROR','Simulated TCP does not match the validated plan',{'waypoint':i,'error_mm':error})
                if m['spray_on'] and m['source_policy_step'] in paint_by_step:paint_by_step[m['source_policy_step']].setVisible(True)
                execution['waypoints_executed']=i+1
                context.update('simulating',.5+.48*(i+1)/len(moves),'Simulating E12 motion')
            execution.update(completed=True,executed_in_simulator=True,maximum_tcp_position_error_mm=max_error,paint_layers=len(paint_by_step))
        result={'planner':plan['planner'],'validation':{'passed':True,'reachable':True,'collision_free':True,'executable':True,
            'sampling_mm':5,'sampling_deg':1,'scope':manifest['collision_scope'],'method':'Complete sampled MoveJ_Test/MoveL_Test validation'},
            'quality':plan['quality'],'execution':execution,'warnings':plan['warnings'],
            'waypoint_count':len(moves),'simulator_version':r.Version(),'T_robot_base_workpiece':transform}
        try:r.Command('Snapshot',str(context.directory/'preview.png'))
        except Exception:pass
        return result
    finally:
        if r:
            try:
                if robot is not None:robot.Stop()
                r.Render(True);r.Disconnect()
            except Exception:pass
