"""Upload a visible, pre-aligned surface; read API_CONTRACT.md before choosing transforms."""
import argparse,json,os,pathlib,urllib.request,uuid

def main():
    parser=argparse.ArgumentParser();parser.add_argument('point_cloud',type=pathlib.Path)
    parser.add_argument('metadata',type=pathlib.Path);parser.add_argument('--url',default='http://127.0.0.1:8765')
    args=parser.parse_args();boundary='spray-'+uuid.uuid4().hex
    metadata=args.metadata.read_text(encoding='utf-8');json.loads(metadata)
    parts=[f'--{boundary}\r\nContent-Disposition: form-data; name="metadata"\r\n\r\n'.encode(),metadata.encode(),b'\r\n',
        f'--{boundary}\r\nContent-Disposition: form-data; name="point_cloud"; filename="{args.point_cloud.name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode(),
        args.point_cloud.read_bytes(),f'\r\n--{boundary}--\r\n'.encode()]
    headers={'Content-Type':'multipart/form-data; boundary='+boundary}
    if os.environ.get('SPRAY_API_TOKEN'):headers['Authorization']='Bearer '+os.environ['SPRAY_API_TOKEN']
    request=urllib.request.Request(args.url.rstrip('/')+'/v1/assets/upload',data=b''.join(parts),headers=headers,method='POST')
    with urllib.request.urlopen(request,timeout=120) as response:print(json.dumps(json.load(response),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
