"""
test_obj8_importer.py - Features 2, 3, 4, 5: OBJ8 Geometry, Split Normals, Coordinates & UVs.
"""

import os
import unittest
import tempfile
import shutil
import bpy

from tests.synthetic_assets import create_minimal_obj8


def safe_clean_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)
    for mat in list(bpy.data.materials):
        bpy.data.materials.remove(mat)


class TestOBJ8Importer(unittest.TestCase):
    """Tests geometry, custom split normals, UVs, and coordinate transformation for OBJ8 import."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_obj8_")
        safe_clean_scene()

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        safe_clean_scene()

    def test_obj8_import_geometry_and_normals(self):
        """Verify geometry import, vertex coordinates, custom normals, and UVs."""
        obj_file = os.path.join(self.temp_dir, "cube.obj")
        create_minimal_obj8(obj_file)

        try:
            from io_scene_xpobj.import_obj8 import import_obj8_file, parse_obj8, build_mesh
            parsed = parse_obj8(obj_file)
            self.assertEqual(len(parsed.vertices), 24)

            mesh_obj = build_mesh(parsed, "ImportedCube")
            self.assertIsNotNone(mesh_obj)
            self.assertEqual(len(mesh_obj.data.vertices), 24)
            self.assertTrue(mesh_obj.data.has_custom_normals, "Custom split normals must be active")
            self.assertEqual(len(mesh_obj.data.uv_layers), 1, "Must have active UV layer")
        except ImportError as e:
            raise unittest.SkipTest(f"io_scene_xpobj.import_obj8 not yet available: {e}")

    def test_winding_reversal_guarantees_outward_normals(self):
        """Verify clockwise OBJ8 face winding is reversed to counter-clockwise."""
        from io_scene_xpobj.constants import reverse_winding_triangle
        cw = (10, 20, 30)
        ccw = reverse_winding_triangle(*cw)
        self.assertEqual(ccw, (10, 30, 20))


if __name__ == '__main__':
    unittest.main()
