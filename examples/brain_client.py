import argparse,json,pathlib,sys
from spray_cerebellum.client import SprayClient

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:8765')
    parser.add_argument('--task',type=pathlib.Path,default=pathlib.Path(__file__).with_name('task_mock.json'))
    args=parser.parse_args();client=SprayClient(args.url);task=json.loads(args.task.read_text(encoding='utf-8'))
    row=client.submit(task);last=[None,-1.]
    print('Accepted:',row['task_id'],flush=True)
    def feedback(row):
        if row['state']!=last[0] or row['progress']-last[1]>=.1:
            print(row['state'],round(row['progress']*100),'%',row['message'],flush=True);last[:]=[row['state'],row['progress']]
    row=client.wait(task['task_id'],on_status=feedback)
    print(json.dumps(row['result'] or row['error'],ensure_ascii=False,indent=2))
    if row['state']!='succeeded':raise SystemExit(1)
    path=args.task.parent/(task['task_id']+'_trajectory.local.json')
    path.write_text(json.dumps(client.trajectory(task['task_id']),ensure_ascii=False,indent=2),encoding='utf-8')
    print('Trajectory downloaded:',path)

if __name__=='__main__':main()
