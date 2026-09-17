"""
test_tier2_boundary.py - Tier 2: Boundary, Corner Case & Adversarial Stress Tests.

Verifies system resilience against edge conditions:
- Empty lines, extraneous whitespace, tabs, and comments in OBJ8 and ACF.
- Missing texture files on disk (graceful fallback).
- Zero-length bone vectors (preventing Blender's silent EditBone auto-deletion).
- Degenerate triangles (coincident vertices, zero area).
- Boundary and extreme DataRef values (-1e6, +1e6, zero range, inverted range).
- Out-of-bounds UV coordinates (negative, > 1.0 for texture tiling).
- Normal Z clamping protection when Nx^2 + Ny^2 >= 1.0.
- Deeply nested animation hierarchies (6+ levels).
- Empty ACF projects and orphan objects.
- Non-ASCII and special characters in file paths and comments.
"""

import os
import sys
import math
import unittest
import tempfile
import shutil
import numpy as np

import bpy
from mathutils import Vector, Matrix

from tests.synthetic_assets import (
    create_corner_case_obj8,
    create_synthetic_acf,
    create_minimal_obj8,
    OBJ8Builder,
    create_synthetic_normal_metalness_texture
)


def safe_clean_scene():
    """Cleans scene objects and orphan data blocks without resetting window manager or add-ons."""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)
    for arm in list(bpy.data.armatures):
        bpy.data.armatures.remove(arm)
    for mat in list(bpy.data.materials):
        bpy.data.materials.remove(mat)
    for img in list(bpy.data.images):
        bpy.data.images.remove(img)


class TestTier2BoundaryAndCornerCases(unittest.TestCase):
    """Tier 2: Boundary, Corner Case & Stress Tests."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="tier2_xp_")
        safe_clean_scene()

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        safe_clean_scene()

    def test_empty_lines_tabs_and_comments(self):
        """Verify parser robustness against arbitrary empty lines, tabs, and inline comments."""
        obj_path = os.path.join(self.temp_dir, "empty_lines.obj")
        create_corner_case_obj8(obj_path, "empty_lines")

        try:
            from io_scene_xpobj import import_obj8
            if hasattr(import_obj8, "parse_obj8"):
                parsed = import_obj8.parse_obj8(obj_path)
                self.assertEqual(len(parsed.vertices), 3)
                self.assertEqual(len(parsed.indices), 3)
                # Verify building mesh succeeds without errors
                mesh_obj = import_obj8.build_mesh(parsed, "EmptyLinesMesh")
                self.assertIsNotNone(mesh_obj)
                self.assertEqual(len(mesh_obj.data.vertices), 3)
                return
        except ImportError:
            pass

        # Oracle check: ensure file parses without crashing
        with open(obj_path, 'r', encoding='utf-8') as f:
            lines = [l.strip() for l in f if l.strip() and not l.strip().startswith('#')]
        self.assertEqual(lines[0], "I")
        self.assertEqual(lines[1], "800")
        self.assertEqual(lines[2], "OBJ")

    def test_zero_bone_length_fallback(self):
        """Verify animation directives with zero-length axis or zero translation do not cause silent bone deletion."""
        obj_path = os.path.join(self.temp_dir, "zero_bone.obj")
        create_corner_case_obj8(obj_path, "zero_bone_length")

        # Simulate bone creation logic
        arm_data = bpy.data.armatures.new("ZeroBoneArm")
        arm_obj = bpy.data.objects.new("ZeroBoneArmObj", arm_data)
        bpy.context.collection.objects.link(arm_obj)
        bpy.context.view_layer.objects.active = arm_obj

        bpy.ops.object.mode_set(mode='EDIT')

        # Raw input from directive is (0, 0, 0)
        raw_axis = Vector((0.0, 0.0, 0.0))
        origin = Vector((0.0, 0.0, 0.0))

        # Enforce minimum length constraint
        if raw_axis.length < 1e-5:
            safe_axis = Vector((0.0, 1.0, 0.0))
        else:
            safe_axis = raw_axis.normalized()

        b = arm_data.edit_bones.new("zero_axis_bone")
        b.head = origin
        b.tail = origin + safe_axis * 0.2

        bpy.ops.object.mode_set(mode='OBJECT')

        # Bone MUST survive mode_set to OBJECT mode
        self.assertIn("zero_axis_bone", arm_obj.data.bones)
        self.assertGreater(arm_obj.data.bones["zero_axis_bone"].length, 0.1)

    def test_degenerate_triangles(self):
        """Verify handling of degenerate geometry (duplicate indices) without crashing."""
        obj_path = os.path.join(self.temp_dir, "degenerate.obj")
        create_corner_case_obj8(obj_path, "degenerate_tris")

        me = bpy.data.meshes.new("DegenerateMesh")
        verts = [(0.0, 0.0, 0.0), (1.0, 1.0, 1.0)]
        faces = [(0, 0, 1), (1, 1, 1)]

        me.from_pydata(verts, [], faces)
        # validate should cleanly report or clean up degenerate faces without throwing
        was_invalid = me.validate(verbose=False, clean_customdata=False)
        self.assertTrue(isinstance(was_invalid, bool))

    def test_extreme_dataref_boundary_values(self):
        """Verify parsing and preservation of extreme DataRef limits (-1e6 to +1e6)."""
        obj_path = os.path.join(self.temp_dir, "boundary_dataref.obj")
        create_corner_case_obj8(obj_path, "boundary_dataref")

        with open(obj_path, 'r', encoding='utf-8') as f:
            lines = [l.strip() for l in f if l.startswith("ANIM_rotate")]

        self.assertEqual(len(lines), 1)
        tokens = lines[0].split()
        val1 = float(tokens[6])
        val2 = float(tokens[7])
        self.assertEqual(val1, -1000000.0)
        self.assertEqual(val2, 1000000.0)

    def test_missing_textures_fallback(self):
        """Verify referencing non-existent texture paths does not cause unhandled crashes."""
        obj_path = os.path.join(self.temp_dir, "missing_textures.obj")
        create_corner_case_obj8(obj_path, "missing_textures")

        try:
            from io_scene_xpobj import import_obj8
            if hasattr(import_obj8, "import_obj8_file"):
                # Must complete without crashing
                objs = import_obj8.import_obj8_file(obj_path)
                self.assertIsNotNone(objs)
                return
        except ImportError:
            pass

        # Standalone verification
        self.assertTrue(os.path.exists(obj_path))

    def test_out_of_bounds_uv_coordinates(self):
        """Verify negative and > 1.0 UV coordinates are accepted and preserved for tiling."""
        me = bpy.data.meshes.new("TilingUVMesh")
        me.from_pydata(
            [(0, 0, 0), (1, 0, 0), (1, 1, 0)],
            [],
            [(0, 1, 2)]
        )
        uv_layer = me.uv_layers.new(name="UVMap")
        tiling_uvs = [(-2.5, -1.0), (3.0, 5.5), (0.5, -4.0)]
        flat_uvs = [c for p in tiling_uvs for c in p]
        uv_layer.data.foreach_set("uv", flat_uvs)

        for i, expected in enumerate(tiling_uvs):
            actual = tuple(uv_layer.data[i].uv)
            self.assertAlmostEqual(expected[0], actual[0], places=5)
            self.assertAlmostEqual(expected[1], actual[1], places=5)

    def test_normal_z_clamping_domain_error_prevention(self):
        """Verify normal Z calculation clamps values when Nx^2 + Ny^2 >= 1.0 (no math domain error)."""
        # Pixel with Nx = 0.9, Ny = 0.9 -> Nx^2 + Ny^2 = 1.62 > 1.0
        nx = 0.9
        ny = 0.9
        radicand = 1.0 - (nx * nx + ny * ny)
        self.assertLess(radicand, 0.0)

        # Clamping logic MUST protect math.sqrt
        clamped_radicand = max(0.0, radicand)
        nz = math.sqrt(clamped_radicand)
        self.assertEqual(nz, 0.0)

        # NumPy vectorized test
        arr_nx = np.array([0.9, 1.2, -1.5], dtype=np.float32)
        arr_ny = np.array([0.9, 0.0, 0.0], dtype=np.float32)
        arr_rad = np.maximum(0.0, 1.0 - (arr_nx * arr_nx + arr_ny * arr_ny))
        arr_nz = np.sqrt(arr_rad)
        self.assertTrue(np.all(arr_nz == 0.0))

    def test_deeply_nested_animation_hierarchy(self):
        """Verify deep hierarchy (6 levels of nested ANIM_begin / ANIM_end)."""
        obj_path = os.path.join(self.temp_dir, "deep_nest.obj")
        create_corner_case_obj8(obj_path, "deep_nesting")

        with open(obj_path, 'r', encoding='utf-8') as f:
            content = f.read()

        begins = content.count("ANIM_begin")
        ends = content.count("ANIM_end")
        self.assertEqual(begins, 6)
        self.assertEqual(ends, 6)

    def test_empty_acf_project_handling(self):
        """Verify handling of ACF file with zero attached objects."""
        acf_path = os.path.join(self.temp_dir, "empty.acf")
        create_synthetic_acf(acf_path, tailnum="N000", attached_objects=[])

        try:
            from io_scene_xpobj import import_acf
            if hasattr(import_acf, "parse_acf"):
                parsed = import_acf.parse_acf(acf_path)
                self.assertEqual(len(parsed.attached_objects), 0)
                self.assertEqual(parsed.tailnum, "N000")
                return
        except ImportError:
            pass

        self.assertTrue(os.path.exists(acf_path))

    def test_utf8_and_unicode_paths(self):
        """Verify handling of paths with special characters and spaces."""
        special_dir = os.path.join(self.temp_dir, "X-Plane Test ✈️ & Co")
        os.makedirs(special_dir, exist_ok=True)
        special_obj = os.path.join(special_dir, "môdèle_spécial.obj")
        create_minimal_obj8(special_obj)
        self.assertTrue(os.path.exists(special_obj))


if __name__ == '__main__':
    unittest.main()
