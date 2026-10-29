import json
import tempfile
import unittest
from spray_cerebellum.multisurface_setup import BUNDLE, POLICY_ID, install_multisurface_demo, verify_bundle
from spray_cerebellum.models import TaskRequest


class MultiSurfaceBundleTests(unittest.TestCase):
    def test_source_splits_are_disjoint_before_augmentation(self):
        dataset = json.loads((BUNDLE / "dataset.json").read_text(encoding="utf-8"))
        sources = json.loads((BUNDLE / "sources.json").read_text(encoding="utf-8"))["splits"]
        groups = [set(sources[name]) for name in ("train", "validation", "test")]
        self.assertFalse(groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2])
        self.assertEqual([len(dataset[key]) for key in ("train", "validation", "test")], [45, 6, 10])
        self.assertEqual(len({row["asset_dir"] for row in dataset["train"]}), 31)
        self.assertTrue(all(not row["asset_dir"].endswith("e350_door_training") for row in dataset["test"]))

    def test_bundle_install_preserves_modified_local_assets(self):
        verify_bundle()
        with tempfile.TemporaryDirectory() as state:
            asset = install_multisurface_demo(state, ("saddle",))[0]
            self.assertEqual(asset.name, "sacgen_saddle_v2")
            self.assertEqual(install_multisurface_demo(state, ("saddle",)), [asset])
            policy = asset / (POLICY_ID + ".zip")
            policy.write_bytes(b"local replacement")
            with self.assertRaisesRegex(ValueError, "Existing multi-surface asset differs"):
                install_multisurface_demo(state, ("saddle",))
            self.assertEqual(policy.read_bytes(), b"local replacement")

    def test_public_examples_bind_new_policy_and_process(self):
        registry = json.loads((BUNDLE / "registry_assets.json").read_text(encoding="utf-8"))
        for case, filename in (("e350", "task_precise_door.json"), ("saddle", "task_unseen_saddle.json")):
            task = TaskRequest.model_validate_json((BUNDLE.parents[1] / "examples" / filename).read_text(encoding="utf-8"))
            manifest = registry[case]["manifest"]
            self.assertEqual(task.target.asset_id, manifest["asset_id"])
            self.assertEqual(task.planning.policy_id, POLICY_ID)
            self.assertEqual(task.process.model_dump(), manifest["recommended_process"])


if __name__ == "__main__":
    unittest.main()
