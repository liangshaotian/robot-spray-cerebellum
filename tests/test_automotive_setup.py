import json
import tempfile
import unittest
from spray_cerebellum.automotive_setup import ASSET_ID, BUNDLE, install_automotive_demo
from spray_cerebellum.assets import AssetRegistry, validate_asset_request
from spray_cerebellum.models import TaskRequest


class AutomotiveBundleTests(unittest.TestCase):
    def test_existing_modified_policy_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as state:
            asset = install_automotive_demo(state)
            self.assertEqual(install_automotive_demo(state), asset)
            manifest = json.loads((asset / "manifest.json").read_text(encoding="utf-8"))
            policy = asset / manifest["policy_file"]
            policy.write_bytes(b"local policy replacement")
            with self.assertRaisesRegex(ValueError, "Existing automotive asset differs"):
                install_automotive_demo(state)
            self.assertEqual(policy.read_bytes(), b"local policy replacement")

    def test_v1_task_binds_current_car_geometry_and_policy(self):
        with tempfile.TemporaryDirectory() as state:
            asset = install_automotive_demo(state)
            request = TaskRequest.model_validate_json((BUNDLE.parents[1] / "examples/task_precise_door.json").read_text(encoding="utf-8"))
            manifest, directory, region = validate_asset_request(request, AssetRegistry(state))
            self.assertEqual(manifest["asset_id"], ASSET_ID)
            self.assertEqual(directory, asset)
            self.assertEqual(manifest["recommended_process"], request.process.model_dump())
            self.assertEqual(manifest["policy_observation_version"], "spray_v2_70")
            self.assertGreater((asset / manifest["mesh_file"]).stat().st_size, 50000000)
            self.assertEqual(region, manifest["allowed_roi"])


if __name__ == "__main__":
    unittest.main()
