import pathlib,json,tempfile
from spray_cerebellum.api import create_app
from spray_cerebellum.models import TaskRequest,TaskStatus,AssetImport
root=pathlib.Path(__file__).resolve().parents[1];out=root/'contracts';out.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='spray_contract_') as d:
    app=create_app(d)
    (out/'openapi.json').write_text(json.dumps(app.openapi(),ensure_ascii=False,indent=2),encoding='utf-8')
    app.state.service.close()
for name,model in [('task_request',TaskRequest),('task_status',TaskStatus),('asset_import',AssetImport)]:
    schema={'$schema':'https://json-schema.org/draft/2020-12/schema',**model.model_json_schema()}
    (out/(name+'.schema.json')).write_text(json.dumps(schema,ensure_ascii=False,indent=2),encoding='utf-8')
print('Exported OpenAPI and request/status/asset schemas')
