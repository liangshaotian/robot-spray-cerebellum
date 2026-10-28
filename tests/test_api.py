import json,tempfile,time,unittest
from fastapi.testclient import TestClient
from spray_cerebellum.api import create_app

class APITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='spray_api_test_')
        self.app=create_app(self.temp.name);self.client=TestClient(self.app);self.client.__enter__()
    def tearDown(self):
        self.client.__exit__(None,None,None);self.temp.cleanup()
    def finish(self,task_id):
        for _ in range(200):
            row=self.client.get('/v1/tasks/'+task_id).json()
            if row['state'] in ('succeeded','failed','cancelled'):return row
            time.sleep(.01)
        self.fail('Mock task did not finish')
    def test_mock_submit_feedback_and_explicit_non_executable_result(self):
        response=self.client.post('/v1/tasks',json={'task_id':'mock-ok','execution':{'backend':'mock','mode':'simulate'}})
        self.assertEqual(response.status_code,202)
        row=self.finish('mock-ok');self.assertEqual(row['state'],'succeeded')
        self.assertFalse(row['result']['validation']['executable'])
        self.assertIsNone(row['result']['validation']['collision_free'])
        self.assertFalse(row['result']['execution']['executed_in_simulator'])
        trajectory=self.client.get('/v1/tasks/mock-ok/trajectory').json()
        self.assertEqual(trajectory['units']['position'],'mm');self.assertGreater(len(trajectory['waypoints']),10)
        self.assertTrue(any(x['spray_on'] for x in trajectory['waypoints']))
        self.assertTrue(any(not x['spray_on'] for x in trajectory['waypoints']))
        self.assertEqual(row['events'][-1]['state'],'succeeded')
    def test_identical_id_is_idempotent_different_body_conflicts(self):
        body={'task_id':'idempotent'}
        self.assertEqual(self.client.post('/v1/tasks',json=body).status_code,202)
        self.assertEqual(self.client.post('/v1/tasks',json=body).status_code,200)
        conflict=self.client.post('/v1/tasks',json={**body,'process':{'speed_mm_s':300}})
        self.assertEqual(conflict.status_code,409);self.assertEqual(conflict.json()['error']['code'],'TASK_ID_CONFLICT')
    def test_pressure_unknown_units_and_bad_transforms_are_rejected(self):
        requests=[{'process':{'atomization_pressure_mpa':.2}}, {'target':{'units':'m'}},
          {'target':{'T_robot_base_workpiece':[[2,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]}},
          {'process':{'speed_mm_s':-1}}, {'process':{'passes':'2'}}, {'schema_version':'2.0'},
          {'target':{'region_uv_mm':{'u_min_mm':1,'u_max_mm':0,'v_min_mm':0,'v_max_mm':1}}}]
        for change in requests:
            with self.subTest(change=change):
                r=self.client.post('/v1/tasks',json={'task_id':'invalid',**change})
                self.assertEqual(r.status_code,422);self.assertEqual(r.json()['error']['code'],'INVALID_REQUEST')
    def test_unknown_robot_asset_and_out_of_bounds_region_fail_before_queue(self):
        for change,code in [({'robot':{'model_id':'ur10'}},'ROBOT_NOT_SUPPORTED'),
          ({'target':{'asset_id':'not-there'}},'ASSET_NOT_FOUND'),
          ({'target':{'region_uv_mm':{'u_min_mm':-1000,'u_max_mm':0,'v_min_mm':600,'v_max_mm':800}}},'REGION_OUT_OF_BOUNDS')]:
            with self.subTest(code=code):
                result=self.client.post('/v1/tasks',json={'task_id':'rejected',**change})
                self.assertIn(result.status_code,(404,422));self.assertEqual(result.json()['error']['code'],code)
    def test_cancel_interrupts_mock_and_terminal_task_is_stable(self):
        body={'task_id':'cancel-me','process':{'passes':3},'execution':{'backend':'mock','mode':'simulate'}}
        self.client.post('/v1/tasks',json=body)
        self.client.post('/v1/tasks/cancel-me/cancel')
        row=self.finish('cancel-me');self.assertEqual(row['state'],'cancelled');self.assertEqual(row['error']['code'],'CANCELLED')
        self.assertEqual(self.client.post('/v1/tasks/cancel-me/cancel').json()['state'],'cancelled')
    def test_openapi_has_machine_readable_input_output(self):
        schema=self.client.get('/openapi.json').json()
        self.assertIn('TaskRequest',schema['components']['schemas'])
        self.assertIn('TaskStatus',schema['components']['schemas'])
        self.assertFalse(schema['components']['schemas']['Process']['additionalProperties'])
        self.assertIn('T_robot_base_workpiece',schema['components']['schemas']['Target']['properties'])
        self.assertEqual(self.client.get('/v1/schemas/asset-import').status_code,200)
    def test_bearer_token_is_enforced_without_breaking_docs(self):
        with tempfile.TemporaryDirectory() as root:
            with TestClient(create_app(root,token='test-only-token')) as c:
                self.assertEqual(c.get('/healthz').status_code,200)
                self.assertEqual(c.get('/v1/capabilities').status_code,401)
                self.assertEqual(c.get('/v1/capabilities',headers={'Authorization':'Bearer wrong'}).status_code,401)
                self.assertEqual(c.get('/v1/capabilities',headers={'Authorization':'Bearer test-only-token'}).status_code,200)
    def test_completed_task_survives_server_restart(self):
        self.client.post('/v1/tasks',json={'task_id':'persistent'})
        self.assertEqual(self.finish('persistent')['state'],'succeeded')
        self.client.__exit__(None,None,None)
        self.client=TestClient(create_app(self.temp.name));self.client.__enter__()
        self.assertEqual(self.client.get('/v1/tasks/persistent').json()['state'],'succeeded')
    def test_artifact_allowlist_and_missing_task(self):
        self.assertEqual(self.client.get('/v1/tasks/unknown').status_code,404)
        self.client.post('/v1/tasks',json={'task_id':'artifacts'});self.finish('artifacts')
        response=self.client.get('/v1/tasks/artifacts/artifacts/request.json')
        self.assertEqual(response.status_code,404)

if __name__=='__main__':unittest.main()
