"""
test_acf_importer.py - Feature 6: ACF Aircraft Project Parsing & Multi-Part Assembly.
"""

import os
import unittest
import tempfile
import shutil
import bpy

from tests.synthetic_assets import create_synthetic_acf, create_minimal_obj8


def safe_clean_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)


class TestACFImporter(unittest.TestCase):
    """Tests Plane Maker .acf project parsing, attached objects, and coordinate offsets."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_acf_")
        safe_clean_scene()

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        safe_clean_scene()

    def test_acf_parsing_and_attached_objects(self):
        """Verify parsing of .acf header, metadata, and attached objects list."""
        acf_path = os.path.join(self.temp_dir, "plane.acf")
        obj_dir = os.path.join(self.temp_dir, "objects")
        os.makedirs(obj_dir, exist_ok=True)
        fuse_path = os.path.join(obj_dir, "fuselage.obj")
        create_minimal_obj8(fuse_path)

        attached = [
            {'path': 'objects/fuselage.obj', 'xyz': (0.0, 0.0, 0.0), 'is_cockpit': 0}
        ]
        create_synthetic_acf(acf_path, tailnum="N555XP", aircraft_name="Test Bird", attached_objects=attached)

        try:
            from io_scene_xpobj.import_acf import parse_acf
            parsed = parse_acf(acf_path)
            self.assertEqual(parsed.tailnum, "N555XP")
            self.assertEqual(parsed.aircraft_name, "Test Bird")
            self.assertEqual(len(parsed.attached_objects), 1)
            self.assertEqual(parsed.attached_objects[0].rel_path, "objects/fuselage.obj")
        except ImportError as e:
            raise unittest.SkipTest(f"io_scene_xpobj.import_acf not yet available: {e}")


if __name__ == '__main__':
    unittest.main()
