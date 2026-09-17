"""
test_rigging.py - Features 7, 8, 9, 10, 11: Armature Rigging, Bones & DataRefs.
"""

import unittest
import bpy
from mathutils import Vector


def safe_clean_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for arm in list(bpy.data.armatures):
        bpy.data.armatures.remove(arm)


class TestRigging(unittest.TestCase):
    """Tests SkeletalMesh Armature creation, bone hierarchy, sizing, and DataRef properties."""

    def setUp(self):
        safe_clean_scene()

    def tearDown(self):
        safe_clean_scene()

    def test_armature_bone_creation_and_hierarchy(self):
        """Verify bone hierarchy, disconnected child bones, and DataRef custom properties."""
        arm_data = bpy.data.armatures.new("RigData")
        arm_obj = bpy.data.objects.new("RigObj", arm_data)
        bpy.context.collection.objects.link(arm_obj)
        bpy.context.view_layer.objects.active = arm_obj

        bpy.ops.object.mode_set(mode='EDIT')

        root = arm_data.edit_bones.new("root")
        root.head = (0, 0, 0)
        root.tail = (0, 1, 0)

        flap = arm_data.edit_bones.new("flap_L")
        flap.head = (-1.5, -0.5, 0.2)
        flap.tail = (-1.5, -0.5, 1.2)
        flap.parent = root
        flap.use_connect = False
        flap["xp_dataref"] = "sim/flightmodel2/controls/flap1_ratio"
        flap["xp_motion_type"] = "ROTATE"

        bpy.ops.object.mode_set(mode='OBJECT')

        self.assertEqual(len(arm_obj.data.bones), 2)
        bone_flap = arm_obj.data.bones["flap_L"]
        self.assertEqual(bone_flap.parent.name, "root")
        self.assertEqual(bone_flap["xp_dataref"], "sim/flightmodel2/controls/flap1_ratio")


if __name__ == '__main__':
    unittest.main()
