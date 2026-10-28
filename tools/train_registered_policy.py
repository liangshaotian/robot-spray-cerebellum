"""Short SAC training for a trusted, registered local heightfield asset."""
import argparse,pathlib,json,hashlib,time
import numpy as np
from scipy.ndimage import map_coordinates
import gymnasium as gym
from gymnasium import spaces
import torch
from stable_baselines3 import SAC
from stable_baselines3.common.callbacks import BaseCallback
from pydantic import TypeAdapter
from spray_cerebellum.models import TaskRequest,Identifier
from spray_cerebellum.planning import plan_surface
from spray_cerebellum.common import read_json,atomic_json,filter_policy_action

class Context:
    def check(self):pass

class SurfaceEnv(gym.Env):
    def __init__(self,directory,manifest):
        super().__init__()
        request=TaskRequest.model_validate({'task_id':'training-baseline','planning':{'method':'raster'}})
        baseline=plan_surface(request,manifest,directory,manifest['allowed_roi'],Context())
        self.anchors=baseline['history']
        self.filter_settings=manifest.get('policy_action_filter')
        with np.load(directory/manifest['surface_file'],allow_pickle=False) as data:
            for name in data.files:setattr(self,name,data[name].copy())
        self.path_h=getattr(self,'path_h',self.h)
        self.coverage_mask=getattr(self,'coverage_mask',self.safe)
        self.dx=float(self.u[1]-self.u[0]);self.U,self.V=np.meshgrid(self.u,self.v)
        self.action_space=spaces.Box(-1.,1.,shape=(2,),dtype=np.float32)
        self.observation_space=spaces.Box(-5.,5.,shape=(60,),dtype=np.float32)
        self.reset()
    def query(self,u,v):
        coordinates=np.array([[(v-self.v[0])/self.dx],[(u-self.u[0])/self.dx]])
        def at(a):return float(map_coordinates(a.astype(float),coordinates,order=1,mode='nearest')[0])
        n=np.array([-at(self.du),-at(self.dv),1.]);n/=np.linalg.norm(n)
        return np.array([u,v,at(self.path_h)]),n
    def valid(self,u,v):
        i=int(round((v-self.v[0])/self.dx));j=int(round((u-self.u[0])/self.dx))
        return 0<=i<len(self.v) and 0<=j<len(self.u) and bool(self.safe[i,j])
    def connected(self,a,b):
        steps=max(2,int(np.linalg.norm(np.asarray(b)-a)/(self.dx/2))+1)
        return all(self.valid(float(p[0]),float(p[1])) for p in np.linspace(a,b,steps))
    def reset(self,seed=None,options=None):
        super().reset(seed=seed);self.index=0;self.dose=np.zeros_like(self.h);self.last=np.zeros(2);self.previous=None;self.history=[]
        return self.obs(),{}
    def obs(self):
        a=self.anchors[min(self.index,len(self.anchors)-1)];p,n=self.query(a['u'],a['v'])
        i=int(round((a['v']-self.v[0])/self.dx));j=int(round((a['u']-self.u[0])/self.dx))
        crop=np.pad(self.dose/2.2,3)[i:i+7,j:j+7].ravel()
        features=[a['u']/600,(a['v']-750)/350,p[2]/900,*n,self.index/len(self.anchors),float(a['start']),float(a['end']),*self.last]
        return np.clip(np.r_[features,crop],-5,5).astype(np.float32)
    def step(self,action):
        action=np.asarray(filter_policy_action(np.clip(action,-1,1),self.last,self.filter_settings))
        a=self.anchors[self.index];y=a['v']+10*float(action[0])
        projected=not self.valid(a['u'],y)
        if projected:y=a['v']
        if self.history and not a['start'] and not self.connected((self.history[-1]['u'],self.history[-1]['v']),(a['u'],y)):
            y=a['v'];projected=True
        p,n=self.query(a['u'],y);speed=400*(1+.25*float(action[1]));reward=-.002*float(np.linalg.norm(action-self.last))
        if self.previous is not None and not a['start']:
            dt=float(np.linalg.norm(p-self.previous))/speed;mask=self.safe&self.coverage_mask;area=self.area[mask]
            before=float(np.average(((self.dose[mask]-2.2)/2.2)**2,weights=area))
            self.dose+=np.exp(-.5*(((self.U-a['u'])/35.)**2+((self.V-y)/60.)**2))*mask*dt*400/40
            after=float(np.average(((self.dose[mask]-2.2)/2.2)**2,weights=area))
            reward+=150*(before-after)-.012*dt
        if projected:reward-=.05
        self.history.append({**a,'v':y});self.previous=p;self.last=action;self.index+=1
        return self.obs(),reward,self.index>=len(self.anchors),False,{}

class Progress(BaseCallback):
    def _on_step(self):
        if self.num_timesteps%1000==0:print('TRAINING',self.num_timesteps,flush=True)
        return True

def main():
    p=argparse.ArgumentParser();p.add_argument('asset_directory',type=pathlib.Path);p.add_argument('--policy-id',required=True)
    p.add_argument('--timesteps',type=int,default=4000);args=p.parse_args()
    policy=TypeAdapter(Identifier).validate_python(args.policy_id);directory=args.asset_directory.resolve()
    manifest=read_json(directory/'manifest.json');env=SurfaceEnv(directory,manifest)
    torch.set_num_threads(2);torch.manual_seed(23)
    model=SAC('MlpPolicy',env,policy_kwargs={'net_arch':[64,64]},learning_rate=3e-4,buffer_size=12000,learning_starts=256,
        batch_size=64,tau=.02,gamma=.98,train_freq=1,gradient_steps=1,ent_coef=.02,seed=23,device='cpu',verbose=0)
    initial=torch.cat([p.detach().flatten() for p in model.actor.parameters()]).clone();start=time.monotonic()
    model.learn(total_timesteps=args.timesteps,callback=Progress());model.save(directory/policy)
    report={'algorithm':'SAC (Stable-Baselines3 2.4.1)','asset_id':manifest['asset_id'],'policy_id':policy,
      'timesteps':model.num_timesteps,'gradient_updates':model._n_updates,'training_seconds':round(time.monotonic()-start,2),
      'actor_parameter_l2_change':float(torch.linalg.norm(torch.cat([p.detach().flatten() for p in model.actor.parameters()])-initial)),
      'model_sha256':hashlib.sha256((directory/(policy+'.zip')).read_bytes()).hexdigest(),'anchors':len(env.anchors),
      'scope':'Single-asset short training; no held-out generalization or production coating quality claim'}
    atomic_json(directory/'training_report.json',report)
    manifest.update(policy_id=policy,policy_file=policy+'.zip');atomic_json(directory/'manifest.json',manifest)
    print('TRAINED',json.dumps(report),flush=True)

if __name__=='__main__':main()
