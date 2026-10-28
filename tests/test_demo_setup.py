import pathlib,tempfile,unittest
from spray_cerebellum.demo_setup import install_precise_demo,ASSET_ID

class DemoBundleTests(unittest.TestCase):
    def test_install_is_reusable_and_does_not_overwrite_different_geometry(self):
        with tempfile.TemporaryDirectory() as state:
            asset=install_precise_demo(state)
            self.assertEqual(asset.name,ASSET_ID)
            self.assertTrue((asset/'car_body_highres_smooth.ply').stat().st_size>50_000_000)
            self.assertEqual(install_precise_demo(state),asset)
            surface=asset/'surface.npz';surface.write_bytes(b'different local geometry')
            with self.assertRaisesRegex(ValueError,'Existing demo differs'):install_precise_demo(state)
            self.assertEqual(surface.read_bytes(),b'different local geometry')

if __name__=='__main__':unittest.main()
