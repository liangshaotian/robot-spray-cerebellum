from __future__ import annotations
import concurrent.futures,hashlib,json,pathlib,threading,time,traceback
from datetime import datetime,timezone
from .models import TaskRequest
from .common import TaskError,TERMINAL,atomic_json,read_json
from .assets import AssetRegistry,validate_asset_request

def now():return datetime.now(timezone.utc).isoformat()

class JobContext:
    def __init__(self,service,task_id):
        self.service=service;self.task_id=task_id;self.directory=service.root/'tasks'/task_id
        self.started=time.monotonic();self.timeout=service.requests[task_id].execution.timeout_s
    def cancelled(self):return self.service.cancellations[self.task_id].is_set()
    def check(self):
        if self.cancelled():raise TaskError('CANCELLED','Task was cancelled')
        if time.monotonic()-self.started>self.timeout:raise TaskError('TASK_TIMEOUT','Task exceeded execution.timeout_s')
    def update(self,state,progress,message):
        self.check()
        with self.service.lock:
            row=self.service.jobs[self.task_id]
            row.update(state=state,progress=round(float(progress),4),message=message,updated_at=now())
            events=row['events']
            # State transitions and coarse progress are retained; polling does not grow the log.
            if not events or state!=events[-1]['state'] or progress-events[-1]['progress']>=.02:
                events.append({'sequence':len(events)+1,'at':now(),'state':state,'progress':float(progress),'message':message})
            self.service._save(self.task_id)
    def trajectory(self,moves):
        atomic_json(self.directory/'trajectory.json',{'schema_version':'1.0','task_id':self.task_id,
            'units':{'position':'mm','speed':'mm/s','joints':'deg','rotation':'dimensionless 3x3'},
            'coordinate_frame':'workpiece','tcp_axis':'+Z points toward surface','waypoints':moves})
    def artifact(self,name,value):atomic_json(self.directory/name,value)

class TaskService:
    def __init__(self,state_dir,demo_dir=None):
        self.root=pathlib.Path(state_dir);(self.root/'tasks').mkdir(parents=True,exist_ok=True)
        self.registry=AssetRegistry(self.root,**({'demo_dir':demo_dir} if demo_dir is not None else {}))
        self.lock=threading.RLock();self.jobs={};self.requests={};self.cancellations={}
        self.pool=concurrent.futures.ThreadPoolExecutor(max_workers=1,thread_name_prefix='spray-worker')
        for file in sorted((self.root/'tasks').glob('*/status.json')):
            row=read_json(file);task_id=row['task_id']
            self.jobs[task_id]=row;self.requests[task_id]=TaskRequest.model_validate(read_json(file.parent/'request.json'))
            self.cancellations[task_id]=threading.Event()
            if row['state'] not in TERMINAL:
                row.update(state='failed',message='Server restarted; no automatic motion resume',error=TaskError('SERVER_RESTARTED','Resubmit with a new task_id').payload(),updated_at=now())
                self._save(task_id)
    def _save(self,task_id):atomic_json(self.root/'tasks'/task_id/'status.json',self.jobs[task_id])
    def get(self,task_id):
        with self.lock:
            if task_id not in self.jobs:raise TaskError('TASK_NOT_FOUND','Unknown task_id')
            return json.loads(json.dumps(self.jobs[task_id]))
    def submit(self,request):
        manifest,directory,region=validate_asset_request(request,self.registry)
        value=request.model_dump(mode='json');fingerprint=hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
        task_id=request.task_id
        with self.lock:
            if task_id in self.jobs:
                if fingerprint!=self.jobs[task_id]['request_sha256']:raise TaskError('TASK_ID_CONFLICT','task_id already exists with a different request')
                return self.get(task_id),False
            if sum(j['state'] not in TERMINAL for j in self.jobs.values())>=8:raise TaskError('QUEUE_FULL','At most 8 unfinished tasks are allowed')
            row={'schema_version':'1.0','task_id':task_id,'state':'queued','progress':0.,'message':'Accepted; one simulator worker executes tasks in order',
                'created_at':now(),'updated_at':now(),'request_sha256':fingerprint,'context':request.context,'result':None,'error':None,
                'events':[{'sequence':1,'at':now(),'state':'queued','progress':0.,'message':'Task accepted'}]}
            self.jobs[task_id]=row;self.requests[task_id]=request;self.cancellations[task_id]=threading.Event()
            atomic_json(self.root/'tasks'/task_id/'request.json',value);self._save(task_id)
            self.pool.submit(self._run,request,manifest,directory,region)
            return self.get(task_id),True
    def cancel(self,task_id):
        with self.lock:
            row=self.get(task_id)
            if row['state'] not in TERMINAL:
                self.cancellations[task_id].set();self.jobs[task_id]['message']='Cancellation requested; waiting for current simulator call to return';self._save(task_id)
            return self.get(task_id)
    def _run(self,request,manifest,directory,region):
        task_id=request.task_id;context=JobContext(self,task_id)
        try:
            context.check()
            from .backends import run_mock,run_robodk
            result=(run_mock if request.execution.backend=='mock' else run_robodk)(request,manifest,directory,region,context)
            context.check()
            result.update(schema_version='1.0',task_id=task_id,backend=request.execution.backend,mode=request.execution.mode,simulation_only=True,
                robot_id=request.robot.model_id,asset_id=request.target.asset_id,region_uv_mm=region,
                units={'position':'mm','speed':'mm/s','joints':'deg','rotation':'dimensionless 3x3'},
                trajectory_url=f'/v1/tasks/{task_id}/trajectory',runtime_s=round(time.monotonic()-context.started,3))
            atomic_json(context.directory/'result.json',result)
            with self.lock:
                self.jobs[task_id].update(result=result,state='succeeded',progress=1.,message='Task complete',error=None,updated_at=now())
        except TaskError as e:
            with self.lock:self.jobs[task_id].update(state='cancelled' if e.code=='CANCELLED' else 'failed',error=e.payload(),message=e.message,updated_at=now())
        except Exception as e:
            (context.directory/'debug.log').write_text(traceback.format_exc(),encoding='utf-8')
            with self.lock:self.jobs[task_id].update(state='failed',error=TaskError('BACKEND_ERROR',str(e)).payload(),message='Backend failed; see server-local debug.log',updated_at=now())
        finally:
            with self.lock:
                row=self.jobs[task_id];row['events'].append({'sequence':len(row['events'])+1,'at':now(),'state':row['state'],'progress':row['progress'],'message':row['message']});self._save(task_id)
    def artifact_path(self,task_id,name):
        self.get(task_id)
        if name not in ('trajectory.json','validation.json','result.json','preview.png'):raise TaskError('ARTIFACT_NOT_FOUND','Artifact name is not exposed')
        path=self.root/'tasks'/task_id/name
        if not path.is_file():raise TaskError('ARTIFACT_NOT_READY','Artifact is not available yet')
        return path
    def close(self):
        for event in self.cancellations.values():event.set()
        self.pool.shutdown(wait=True,cancel_futures=False)
