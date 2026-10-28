import argparse,os,pathlib
from .common import REPO

def main():
    parser=argparse.ArgumentParser(description='Brain-to-cerebellum spray API (simulation only)')
    parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--state-dir',default=str(REPO/'.local'));args=parser.parse_args()
    if args.host not in ('127.0.0.1','localhost','::1') and not os.environ.get('SPRAY_API_TOKEN'):
        parser.error('Set SPRAY_API_TOKEN before listening outside localhost')
    import uvicorn
    from .api import create_app
    uvicorn.run(create_app(args.state_dir),host=args.host,port=args.port,workers=1)

if __name__=='__main__':main()
