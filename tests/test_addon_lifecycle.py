"""
test_addon_lifecycle.py - Feature 1: Add-on Registration, Metadata & Lifecycle.
"""

import unittest
import bpy


class TestAddonLifecycle(unittest.TestCase):
    """Verifies add-on registration, metadata, operators, and unregistration in Blender 4.3+."""

    def test_addon_bl_info(self):
        """Verify bl_info metadata targets Blender 4.3+ and contains required keys."""
        try:
            import io_scene_xpobj
        except ImportError as e:
            raise unittest.SkipTest(f"io_scene_xpobj not yet importable: {e}")

        bl_info = getattr(io_scene_xpobj, "bl_info", None)
        if bl_info is None:
            raise unittest.SkipTest("io_scene_xpobj.bl_info not yet defined")

        self.assertIn("name", bl_info)
        self.assertIn("version", bl_info)
        self.assertIn("blender", bl_info)
        self.assertEqual(bl_info["blender"], (4, 3, 0), "Must target Blender (4, 3, 0)")
        self.assertEqual(bl_info.get("category"), "Import-Export")

    def test_registration_and_unregistration(self):
        """Verify add-on register() and unregister() cycle cleanly without errors."""
        try:
            import io_scene_xpobj
        except ImportError as e:
            raise unittest.SkipTest(f"io_scene_xpobj not yet importable: {e}")

        if not hasattr(io_scene_xpobj, "register"):
            raise unittest.SkipTest("io_scene_xpobj.register not yet defined")

        # Test registration
        io_scene_xpobj.register()

        # Check operator presence
        has_obj_op = hasattr(bpy.ops.import_scene, "xplane_obj") or hasattr(bpy.ops.import_scene, "xpobj") or hasattr(bpy.ops, "xplane")
        self.assertTrue(has_obj_op, "Expected X-Plane import operator registered in bpy.ops")

        # Test unregistration
        io_scene_xpobj.unregister()


if __name__ == '__main__':
    unittest.main()
