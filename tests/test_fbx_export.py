"""
test_fbx_export.py - Feature 22: Unreal Engine SkeletalMesh FBX Exporter Parameters.
"""

import unittest


class TestFBXExport(unittest.TestCase):
    """Tests Blender 4.3 FBX exporter parameter configuration for Unreal Engine 5 compatibility."""

    def test_fbx_exporter_flags(self):
        """Verify parameter configurations for SkeletalMesh FBX export."""
        params = {
            'axis_forward': '-Z',
            'axis_up': 'Y',
            'add_leaf_bones': False,
            'armature_nodetype': 'NULL',
            'bake_space_transform': False,
            'primary_bone_axis': 'Y',
            'secondary_bone_axis': 'X',
            'use_armature_deform_only': False,
            'use_tspace': True,
        }

        self.assertEqual(params['axis_forward'], '-Z')
        self.assertEqual(params['axis_up'], 'Y')
        self.assertFalse(params['add_leaf_bones'], "add_leaf_bones must be False to prevent extra bones in UE")
        self.assertEqual(params['armature_nodetype'], 'NULL')
        self.assertFalse(params['bake_space_transform'], "bake_space_transform is known to corrupt bone matrices")
        self.assertTrue(params['use_tspace'], "Tangent space must be embedded for UE normal mapping")


if __name__ == '__main__':
    unittest.main()
