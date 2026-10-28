from __future__ import annotations
import os,pathlib,json,secrets,importlib.util
from contextlib import asynccontextmanager
from fastapi import FastAPI,APIRouter,Depends,HTTPException,UploadFile,File,Form,Request
from fastapi.responses import JSONResponse,FileResponse
from fastapi.exceptions import RequestValidationError
from fastapi.security import HTTPBearer,HTTPAuthorizationCredentials
from pydantic import ValidationError
from .models import TaskRequest,AssetImport,TaskStatus,TaskAccepted
from .service import TaskService
from .common import REPO,TaskError,read_json
from . import __version__

def create_app(state_dir=None,token=None,demo_dir=None):
    service=TaskService(state_dir or os.environ.get('SPRAY_STATE_DIR',str(REPO/'.local')),demo_dir)
    configured_token=token if token is not None else os.environ.get('SPRAY_API_TOKEN','')
    @asynccontextmanager
    async def lifespan(app):
        yield
        service.close()
    app=FastAPI(title='Spray Cerebellum API',version=__version__,lifespan=lifespan,
        description='Versioned brain -> cerebellum tasks. Mock protocol integration or validated RoboDK simulation. No hardware execution.')
    app.state.service=service
    bearer=HTTPBearer(auto_error=False)
    def authorize(credentials:HTTPAuthorizationCredentials|None=Depends(bearer)):
        if configured_token and (credentials is None or not secrets.compare_digest(credentials.credentials,configured_token)):
            raise HTTPException(401,detail='Missing or invalid bearer token',headers={'WWW-Authenticate':'Bearer'})
    router=APIRouter(prefix='/v1',dependencies=[Depends(authorize)])
    @app.exception_handler(TaskError)
    async def task_error(request,error):
        status=404 if error.code in ('TASK_NOT_FOUND','ASSET_NOT_FOUND','ARTIFACT_NOT_FOUND','ARTIFACT_NOT_READY') else 409 if error.code in ('TASK_ID_CONFLICT','ASSET_EXISTS','QUEUE_FULL') else 422
        return JSONResponse(status_code=status,content={'error':error.payload()})
    @app.exception_handler(HTTPException)
    async def http_error(request,error):
        return JSONResponse(status_code=error.status_code,content={'error':{'code':'AUTH_REQUIRED' if error.status_code==401 else 'HTTP_ERROR','message':str(error.detail),'details':{}}},headers=error.headers)
    @app.exception_handler(RequestValidationError)
    async def invalid_request(request,error):
        details=[{'path':'.'.join(map(str,x['loc'])),'message':x['msg']} for x in error.errors()]
        return JSONResponse(status_code=422,content={'error':{'code':'INVALID_REQUEST','message':'Request does not match schema; unknown fields are rejected','details':details}})
    @app.middleware('http')
    async def size_limit(request,call_next):
        length=request.headers.get('content-length')
        if length and int(length)>64*1024*1024:return JSONResponse(status_code=413,content={'error':{'code':'REQUEST_TOO_LARGE','message':'Maximum request size is 64 MiB'}})
        return await call_next(request)
    @app.get('/healthz')
    def health():return {'status':'ok','api_version':'1.0','server_version':__version__,'simulation_only':True}
    @router.get('/capabilities')
    def capabilities():
        return {'schema_version':'1.0','skills':['spray_surface.v1'],'robots':['huayan_e12'],
            'backends':['mock','robodk'],'modes':['plan_only','simulate'],'hardware_execution':False,
            'point_cloud_formats':['PLY','PCD ascii','PCD binary','XYZ','CSV numeric'],
            'geometry_scope':'Explicitly aligned visible single-valued heightfield h(u,v); unknown cells excluded',
            'task_units':{'position':'mm','speed':'mm/s','joint_angles':'deg','rotation':'3x3 matrix'},
            'process_parameters':['standoff_mm','speed_mm_s','spray_width_mm','overlap_ratio','passes'],
            'unsupported_process_parameters':['atomization_pressure','fan_pressure','paint_flow','physical_film_thickness'],
            'installed_optional_modules':{p:importlib.util.find_spec(p) is not None for p in ['numpy','scipy','trimesh','stable_baselines3','robodk']},
            'queue_capacity':8,'simulator_workers':1,'maximum_request_bytes':64*1024*1024}
    @router.get('/assets')
    def assets():return {'assets':service.registry.list()}
    @router.get('/schemas/asset-import')
    def asset_schema():return AssetImport.model_json_schema()
    @router.post('/assets/upload',status_code=201)
    async def upload(metadata:str=Form(...),point_cloud:UploadFile=File(...)):
        try:model=AssetImport.model_validate_json(metadata)
        except ValidationError as e:raise TaskError('INVALID_ASSET_METADATA','Metadata does not match AssetImport schema',{'errors':[{'path':'.'.join(map(str,x['loc'])),'message':x['msg']} for x in e.errors()]})
        content=await point_cloud.read(64*1024*1024+1)
        if len(content)>64*1024*1024:raise TaskError('REQUEST_TOO_LARGE','Maximum point cloud size is 64 MiB')
        try:return service.registry.import_cloud(model,point_cloud.filename or '',content)
        except ImportError as e:raise TaskError('DEPENDENCY_MISSING','Install geometry extras to import point clouds') from e
        except TaskError:raise
        except (ValueError,KeyError,UnicodeError,IndexError,AttributeError,TypeError,OSError) as e:raise TaskError('INVALID_POINT_CLOUD',str(e)) from e
    @router.post('/tasks',response_model=TaskAccepted,status_code=202)
    def submit(task:TaskRequest):
        row,created=service.submit(task)
        return JSONResponse(status_code=202 if created else 200,content={**row,'status_url':f'/v1/tasks/{task.task_id}'},headers={'Location':f'/v1/tasks/{task.task_id}'})
    @router.get('/tasks/{task_id}',response_model=TaskStatus)
    def task(task_id:str):return service.get(task_id)
    @router.get('/tasks/{task_id}/events')
    def events(task_id:str):return {'task_id':task_id,'events':service.get(task_id)['events']}
    @router.post('/tasks/{task_id}/cancel',response_model=TaskStatus)
    def cancel(task_id:str):return service.cancel(task_id)
    @router.get('/tasks/{task_id}/trajectory')
    def trajectory(task_id:str):return read_json(service.artifact_path(task_id,'trajectory.json'))
    @router.get('/tasks/{task_id}/artifacts/{name}')
    def artifact(task_id:str,name:str):return FileResponse(service.artifact_path(task_id,name))
    app.include_router(router)
    return app
