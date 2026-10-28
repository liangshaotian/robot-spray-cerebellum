import importlib.util,io,json,struct,tempfile,time,unittest,pathlib
GEOMETRY=all(importlib.util.find_spec(x) is not None for x in ('numpy','scipy','trimesh'))

@unittest.skipUnless(GEOMETRY,'Install geometry extras')
class GeometryTests(unittest.TestCase):
    def test_binary_pcd_uses_declared_fields_not_assumed_xyz_only(self):
        from spray_cerebellum.cloud import xyz_from_bytes
        header=b'VERSION .7\nFIELDS rgb z x y\nSIZE 4 4 4 4\nTYPE U F F F\nCOUNT 1 1 1 1\nWIDTH 16\nHEIGHT 1\nPOINTS 16\nDATA binary\n'
        content=header+b''.join(struct.pack('<Ifff',123,float(i+2),float(i),float(i+1)) for i in range(16))
        p=xyz_from_bytes('points.pcd',content)
        self.assertEqual(p[5].tolist(),[5.,6.,7.])
    def test_import_explicit_metres_and_transform_then_reject_untrained_policy(self):
        import numpy as np
        from fastapi.testclient import TestClient
        from spray_cerebellum.api import create_app
        points=np.array([[u/1000,v/1000,.03] for u in range(-150,151,15) for v in range(450,751,15)])
        content='\n'.join(' '.join(map(str,p)) for p in points).encode()
        identity=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]
        meta={'asset_id':'uploaded-panel','input_units':'m','T_workpiece_input':identity,
          'T_robot_base_workpiece':[[0,0,-1,1200],[-1,0,0,0],[0,1,0,0],[0,0,0,1]],'grid_mm':15}
        with tempfile.TemporaryDirectory() as d:
            with TestClient(create_app(d)) as c:
                response=c.post('/v1/assets/upload',data={'metadata':json.dumps(meta)},files={'point_cloud':('panel.xyz',content,'text/plain')})
                self.assertEqual(response.status_code,201,response.text);asset=response.json()
                self.assertGreater(asset['allowed_roi']['v_min_mm'],400)
                self.assertLess(asset['allowed_roi']['u_max_mm'],200)
                self.assertIsNone(asset['policy_id'])
                with np.load(pathlib.Path(d)/'assets/uploaded-panel/surface.npz') as data:
                    self.assertAlmostEqual(float(data['h'][10,10]),30,places=4)
                r=c.post('/v1/tasks',json={'task_id':'no-policy','target':{'asset_id':'uploaded-panel'},'execution':{'backend':'robodk'}})
                self.assertEqual(r.status_code,422);self.assertEqual(r.json()['error']['code'],'POLICY_ASSET_MISMATCH')
                again=c.post('/v1/assets/upload',data={'metadata':json.dumps(meta)},files={'point_cloud':('panel.xyz',content,'text/plain')})
                self.assertEqual(again.status_code,409)
    def test_raster_parameters_change_real_path_and_dose(self):
        from spray_cerebellum.models import TaskRequest
        from spray_cerebellum.assets import DEMO_MANIFEST
        from spray_cerebellum.common import DEMO
        from spray_cerebellum.planning import plan_surface
        class Context:
            def check(self):pass
        region=DEMO_MANIFEST['allowed_roi']
        a=TaskRequest.model_validate({'task_id':'raster-a','planning':{'method':'raster'}})
        b=TaskRequest.model_validate({'task_id':'raster-b','planning':{'method':'raster'},'process':{'standoff_mm':240,'speed_mm_s':300,'passes':2}})
        pa=plan_surface(a,DEMO_MANIFEST,DEMO,region,Context());pb=plan_surface(b,DEMO_MANIFEST,DEMO,region,Context())
        ma=next(x for x in pa['moves'] if x['spray_on']);mb=next(x for x in pb['moves'] if x['spray_on'])
        import numpy as np
        self.assertAlmostEqual(np.linalg.norm(np.array(mb['nozzle_xyz_mm'])-ma['nozzle_xyz_mm']),40,places=5)
        self.assertEqual(mb['speed_mm_s'],300)
        self.assertGreater(len(pb['moves']),len(pa['moves']))
        self.assertGreater(pb['quality']['relative_dose_mean'],pa['quality']['relative_dose_mean'])
    def test_unknown_gap_between_samples_is_not_bridged(self):
        import numpy as np
        from spray_cerebellum.models import TaskRequest
        from spray_cerebellum.planning import plan_surface
        class Context:
            def check(self):pass
        u=np.arange(-200.,201.,10.);v=np.arange(500.,901.,10.);U,V=np.meshgrid(u,v)
        mask=U!=0;zeros=np.zeros_like(U)
        region={'u_min_mm':-200.,'u_max_mm':200.,'v_min_mm':500.,'v_max_mm':900.}
        with tempfile.TemporaryDirectory() as directory:
            np.savez(pathlib.Path(directory)/'surface.npz',u=u,v=v,h=zeros,du=zeros,dv=zeros,area=np.ones_like(U)*100,observed=mask,safe=mask)
            task=TaskRequest.model_validate({'task_id':'hole-test','planning':{'method':'raster'}})
            result=plan_surface(task,{'surface_file':'surface.npz'},pathlib.Path(directory),region,Context())
            for a,b in zip(result['history'],result['history'][1:]):
                if not b['start']:self.assertFalse(a['u']<0<b['u'] or b['u']<0<a['u'])

    def test_smoothed_support_keeps_raw_scan_and_excludes_masked_coating(self):
        import numpy as np
        from spray_cerebellum.models import TaskRequest
        from spray_cerebellum.planning import plan_surface
        class Context:
            def check(self):pass
        u=np.arange(-200.,201.,10.);v=np.arange(500.,901.,10.);U,V=np.meshgrid(u,v)
        raw=np.zeros_like(U);raw[:,20]=40.;support=np.zeros_like(U)
        mask=np.ones_like(U,dtype=bool);coat=~((abs(U)<40)&(abs(V-700)<40))
        region={'u_min_mm':-200.,'u_max_mm':200.,'v_min_mm':500.,'v_max_mm':900.}
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory)/'surface.npz'
            np.savez(path,u=u,v=v,h=raw,path_h=support,du=support,dv=support,
                area=np.ones_like(U)*100,observed=mask,safe=mask,coverage_mask=coat)
            task=TaskRequest.model_validate({'task_id':'smooth-mask','planning':{'method':'raster'}})
            result=plan_surface(task,{'surface_file':'surface.npz'},path.parent,region,Context())
            self.assertTrue(all(m['surface_xyz_mm'][2]==0 for m in result['moves']))
            self.assertTrue(np.all(result['relative_dose'][~coat]==0))
            self.assertGreater(float(result['relative_dose'][coat].max()),0)
            with np.load(path) as original:self.assertEqual(float(original['h'].max()),40.)
            tilted=plan_surface(task,{'surface_file':'surface.npz','spray_tilt_deg':-10.},path.parent,region,Context())
            move=next(m for m in tilted['moves'] if m['spray_on'])
            axis=np.array(move['spray_axis_normal']);p=np.array(move['surface_xyz_mm']);tcp=np.array(move['nozzle_xyz_mm'])
            self.assertAlmostEqual(float(np.linalg.norm(tcp-p)),200.)
            self.assertTrue(np.allclose(tcp-p,200*axis))
            self.assertEqual(move['surface_normal'],[0.,0.,1.])

if __name__=='__main__':unittest.main()
