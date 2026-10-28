"""Small standard-library client; the brain never imports RoboDK or torch."""
import json,os,time,urllib.request,urllib.error,urllib.parse

class SprayClient:
    def __init__(self,base_url='http://127.0.0.1:8765',token=None):
        self.base_url=base_url.rstrip('/');self.token=token if token is not None else os.environ.get('SPRAY_API_TOKEN','')
    def request(self,method,path,body=None):
        headers={'Accept':'application/json'}
        if self.token:headers['Authorization']='Bearer '+self.token
        data=None
        if body is not None:headers['Content-Type']='application/json';data=json.dumps(body).encode('utf-8')
        request=urllib.request.Request(self.base_url+path,data=data,headers=headers,method=method)
        try:
            with urllib.request.urlopen(request,timeout=20) as response:return json.load(response)
        except urllib.error.HTTPError as e:
            try:detail=json.loads(e.read().decode('utf-8'))
            except ValueError:detail={'http_status':e.code}
            raise RuntimeError(json.dumps(detail,ensure_ascii=False)) from None
    def submit(self,task):return self.request('POST','/v1/tasks',task)
    def status(self,task_id):return self.request('GET','/v1/tasks/'+urllib.parse.quote(task_id,safe=''))
    def cancel(self,task_id):return self.request('POST','/v1/tasks/'+urllib.parse.quote(task_id,safe='')+'/cancel')
    def trajectory(self,task_id):return self.request('GET','/v1/tasks/'+urllib.parse.quote(task_id,safe='')+'/trajectory')
    def wait(self,task_id,timeout=600,poll=.25,on_status=None):
        start=time.monotonic()
        while time.monotonic()-start<timeout:
            row=self.status(task_id)
            if on_status:on_status(row)
            if row['state'] in ('succeeded','failed','cancelled'):return row
            time.sleep(poll)
        raise TimeoutError('Timed out waiting; task may still be running. Query status or cancel explicitly.')
