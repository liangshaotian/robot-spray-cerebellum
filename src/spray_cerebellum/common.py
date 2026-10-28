from __future__ import annotations
import json,pathlib,os,math

REPO=pathlib.Path(__file__).resolve().parents[2]
DEMO=pathlib.Path(os.environ.get("SPRAY_DEMO_DIR",str(REPO/"demo")))
TERMINAL={"succeeded","failed","cancelled"}

class TaskError(Exception):
    def __init__(self,code,message,details=None):
        super().__init__(message);self.code=code;self.message=message;self.details=details or {}
    def payload(self):return {"code":self.code,"message":self.message,"details":self.details}

def atomic_json(path,value):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    tmp.replace(path)

def read_json(path):return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))

def filter_policy_action(action, previous, settings):
    """Causal slew limit shared by SAC training and trajectory inference."""
    if not settings:return [float(v) for v in action]
    alpha=float(settings.get('alpha',.25));limit=float(settings.get('max_delta',.12))
    return [max(-1.,min(1.,float(p)+max(-limit,min(limit,alpha*(float(a)-float(p))))))
            for a,p in zip(action,previous)]

def orientation(normal):
    z=[-float(v) for v in normal];length=math.sqrt(sum(v*v for v in z));z=[v/length for v in z]
    tangent=[1.,0.,0.] if abs(z[0])<.9 else [0.,1.,0.]
    dot=sum(a*b for a,b in zip(tangent,z));x=[a-dot*b for a,b in zip(tangent,z)]
    length=math.sqrt(sum(v*v for v in x));x=[v/length for v in x]
    y=[z[1]*x[2]-z[2]*x[1],z[2]*x[0]-z[0]*x[2],z[0]*x[1]-z[1]*x[0]]
    return [[x[i],y[i],z[i]] for i in range(3)]

def make_moves(history,request):
    moves=[];spray=request.process.standoff_mm;transfer=spray+100
    def push(h,d,on,kind,motion="MoveL"):
        p=h["surface_xyz_mm"];n=h.get('spray_axis_normal',h["surface_normal"])
        moves.append({"id":len(moves),"source_policy_step":h["step"],"segment":h["segment"],
            "spray_on":on,"motion":motion,"kind":kind,"surface_xyz_mm":p,"surface_normal":h["surface_normal"],
            "nozzle_xyz_mm":[float(a+d*b) for a,b in zip(p,n)],"rotation_matrix":orientation(n),
            "speed_mm_s":float(h["speed_mm_s"] if on else 160),"standoff_mm":float(d),
            "coordinate_frame":"workpiece","rounding_mm":0.})
        if 'spray_axis_normal' in h:moves[-1]['spray_axis_normal']=n
    last=None
    for h in history:
        if h["start"]:
            if last is not None:push(last,transfer,False,"retract")
            push(h,transfer,False,"approach","MoveJ");push(h,spray,False,"entry")
        else:push(h,spray,True,"spray")
        last=h
    if last is not None:push(last,transfer,False,"final_retract")
    return moves
