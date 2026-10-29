"""Replay a prepared asset through the same public task API, without retraining."""
import pathlib,sys,os,time,json,uuid,subprocess,argparse,traceback,socket
from spray_cerebellum.client import SprayClient
from spray_cerebellum.common import REPO,TERMINAL

def select_task_station(r,task_id):
    """RoboDK 5.9 requires activation before querying inactive station items."""
    for candidate in r.getOpenStations():
        r.setActiveStation(candidate)
        active=r.ActiveStation()
        if active.Name().endswith(' | '+task_id):return active
    return None

def show_completed_scene(asset,task_id,previous_id=None):
    from robodk.robolink import Robolink,WINDOWSTATE_MAXIMIZED
    from robodk.robomath import Mat
    import numpy as np
    port=int(os.environ.get('ROBODK_PORT','20721'))
    with socket.create_connection(('127.0.0.1',port),timeout=.5):pass
    r=Robolink(robodk_ip='127.0.0.1',port=port)
    try:
        r.Render(False)
        scene=select_task_station(r,task_id)
        if scene is None or not scene.Childs():raise RuntimeError('Completed demo station is not available in the viewer')
        # Retain the previous working scene until the new task has succeeded.
        # Closing any station in 5.9 can select the empty default station.
        if previous_id and previous_id!=task_id:
            previous=select_task_station(r,previous_id)
            if previous is not None:previous.Delete()
        scene=select_task_station(r,task_id)
        if scene is None:raise RuntimeError('Cannot restore the completed demo station')
        r.setActiveStation(scene)
        for child in scene.Childs():child.setParam('Tree','Collapse')
        presentation=asset.get('presentation',{})
        eye=np.array(presentation.get('camera_eye_mm',[-4500.,-2100.,1900.]),dtype=float)
        target=np.array(presentation.get('camera_target_mm',[1600.,0.,700.]),dtype=float)
        z=eye-target;z/=np.linalg.norm(z);x=np.cross([0.,0.,1.],z);x/=np.linalg.norm(x)
        y=np.cross(z,x);rotation=np.array([x,y,z]);camera=np.eye(4)
        camera[:3,:3]=rotation;camera[:3,3]=-rotation@eye
        r.setViewPose(Mat(camera.tolist()));r.setSelection([])
        # This activation must remain after cleanup and all station enumeration.
        r.setActiveStation(scene);r.Render(True);r.setWindowState(WINDOWSTATE_MAXIMIZED)
    finally:
        r.Render(True);r.Disconnect()

def ensure_server(client):
    try:client.request('GET','/healthz');return
    except Exception:pass
    local=REPO/'.local';local.mkdir(exist_ok=True)
    options=dict(cwd=REPO,env=dict(os.environ),stdin=subprocess.DEVNULL,
        stdout=(local/'server.stdout.log').open('ab'),stderr=(local/'server.stderr.log').open('ab'))
    flags=0
    if os.name=='nt':flags=subprocess.DETACHED_PROCESS|subprocess.CREATE_NEW_PROCESS_GROUP
    command=[sys.executable,'-m','spray_cerebellum']
    try:p=subprocess.Popen(command,creationflags=flags|getattr(subprocess,'CREATE_BREAKAWAY_FROM_JOB',0),**options)
    except PermissionError:p=subprocess.Popen(command,creationflags=flags,**options)
    (local/'server_process.json').write_text(json.dumps({'pid':p.pid,'url':client.base_url}))
    for _ in range(100):
        try:client.request('GET','/healthz');return
        except Exception:time.sleep(.1)
    raise RuntimeError('Local task API failed to start; inspect .local/server.stderr.log')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--asset-id',default='demo_car_4500')
    parser.add_argument('--show-only',action='store_true',help='Show the completed scene without starting motion')
    args=parser.parse_args();client=SprayClient();ensure_server(client)
    assets=client.request('GET','/v1/assets')['assets'];asset=next((a for a in assets if a['asset_id']==args.asset_id),None)
    if not asset or not asset.get('policy_id'):raise RuntimeError('The asset and matching trained policy must be prepared before replay')
    previous_path=REPO/'.local'/('replay_'+args.asset_id+'.json')
    previous=json.loads(previous_path.read_text()) if previous_path.exists() else None
    if args.show_only:
        if previous is None:raise RuntimeError('Run this demo once before opening the completed scene')
        status=client.status(previous['task_id'])
        if status['state']!='succeeded':raise RuntimeError('The latest demo has not completed successfully')
        show_completed_scene(asset,previous['task_id'])
        return
    if previous:
        status=client.status(previous['task_id'])
        if status['state'] not in TERMINAL:
            row=client.wait(previous['task_id'])
            if row['state']!='succeeded':raise RuntimeError(str(row['error']))
            show_completed_scene(asset,previous['task_id'])
            return
    task={'schema_version':'1.0','task_id':'scan-demo-'+uuid.uuid4().hex[:12],
        'target':{'asset_id':args.asset_id,'units':'mm'},
        'process':asset.get('recommended_process',{}),
        'planning':{'method':'sac','policy_id':asset['policy_id'],'sample_step_mm':asset.get('recommended_sample_step_mm',40.)},
        'execution':{'backend':'robodk','mode':'simulate','show_window':True,'simulation_speed':5,'timeout_s':300},
        'context':{'source':asset.get('source','prepared scan asset')}}
    client.submit(task);previous_path.write_text(json.dumps({'task_id':task['task_id']}))
    row=client.wait(task['task_id'])
    if row['state']!='succeeded':raise RuntimeError(str(row['error']))
    show_completed_scene(asset,task['task_id'],previous['task_id'] if previous else None)

if __name__=='__main__':
    local=REPO/'.local';local.mkdir(exist_ok=True)
    lock=(local/'replay.lock').open('a+b');lock.seek(0,2)
    if lock.tell()==0:lock.write(b'0');lock.flush()
    lock.seek(0)
    if os.name=='nt':
        import msvcrt
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:raise SystemExit(0)
    try:main()
    except Exception:
        (local/'replay_error.log').write_text(traceback.format_exc(),encoding='utf-8')
        if os.name=='nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(0,'Replay failed. See .local/replay_error.log in the project folder.','Spray demo',16)
        raise
