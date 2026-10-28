"""Run an HTTP acceptance job; --backend robodk requires a configured simulator host."""
import argparse,json,pathlib,time,uuid
from spray_cerebellum.client import SprayClient

def main():
    p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:8765')
    p.add_argument('--backend',choices=['mock','robodk'],default='mock');p.add_argument('--record',type=pathlib.Path)
    args=p.parse_args();root=pathlib.Path(__file__).resolve().parents[1]
    task=json.loads((root/'examples'/('task_'+args.backend+'.json')).read_text(encoding='utf-8'))
    task['task_id']='acceptance-'+args.backend+'-'+uuid.uuid4().hex[:10]
    c=SprayClient(args.url);c.submit(task)
    last=[None]
    def progress(s):
        if last[0]!=s['state']:print(s['state'],flush=True);last[0]=s['state']
    status=c.wait(task['task_id'],on_status=progress)
    if status['state']!='succeeded':raise SystemExit(json.dumps(status['error']))
    result=status['result'];trajectory=c.trajectory(task['task_id'])
    if args.backend=='robodk':
        assert result['validation']['executable'] and result['execution']['executed_in_simulator']
        assert result['execution']['waypoints_executed']==result['waypoint_count']==len(trajectory['waypoints'])
        assert result['execution']['maximum_tcp_position_error_mm']<.1
    else:
        assert not result['validation']['executable'] and not result['execution']['executed_in_simulator']
    if args.record:
        args.record.parent.mkdir(parents=True,exist_ok=True)
        args.record.write_text(json.dumps({'passed':True,'request':task,'result':result},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'task_id':task['task_id'],'backend':args.backend,'waypoints':result['waypoint_count'],'runtime_s':result['runtime_s']}),flush=True)

if __name__=='__main__':main()
