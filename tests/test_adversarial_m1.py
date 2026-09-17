"""
test_adversarial_m1.py - Empirical Adversarial Stress Suite for M1 Geometry & Custom Normals.

Designed by challenger_m1_1 to rigorously challenge:
- Extreme coordinates (microscopic, gigantic, mixed scales)
- Degenerate triangles and zero-area faces (duplicate indices, collinear, coincident)
- Inverted normal vectors (opposite to face normals, inward enclosed volumes)
- Non-normalized normals (zero-length, sub-threshold, massive magnitude)
- Multiple TRIS blocks (multiple blocks, non-contiguous, out-of-order, partial slices)
- Out-of-bounds indices and corrupted VT lines
- Custom split normal preservation accuracy (oracle dot-product verification)
"""

import os
import sys
import math
import unittest
import tempfile
import shutil
from typing import List, Tuple

import bpy
from mathutils import Vector

from io_scene_xpobj.constants import xp_to_blender_point, xp_to_blender_vector, reverse_winding_triangle
from io_scene_xpobj.import_obj8 import parse_obj8, build_mesh, import_obj8_file, ParsedOBJ8, TrisCommand


def safe_clean_scene():
    """Cleans all scene objects and meshes between test cases."""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)
    for mat in list(bpy.data.materials):
        bpy.data.materials.remove(mat)


class TestAdversarialCoordinates(unittest.TestCase):
    """Stress-tests geometry with extreme floating-point coordinates."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="adv_coord_")
        safe_clean_scene()

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        safe_clean_scene()

    def test_gigantic_coordinates(self):
        """Verify vertices with magnitudes up to 1e12 survive coordinate conversion and validation."""
        obj_path = os.path.join(self.temp_dir, "gigantic.obj")
        with open(obj_path, "w", encoding="utf-8") as f:
            f.write("I\n800\nOBJ\nTEXTURE none\nPOINT_COUNTS 3 0 0 3\n")
            f.write("VT 1.0e12 -2.0e12 3.0e12 0.0 1.0 0.0 0.0 0.0\n")
            f.write("VT -1.0e12 2.0e12 -3.0e12 0.0 1.0 0.0 1.0 0.0\n")
            f.write("VT 5.0e11 -5.0e11 5.0e11 0.0 1.0 0.0 0.0 1.0\n")
            f.write("IDX10 0 1 2\n")
            f.write("TRIS 0 3\n")

        parsed = parse_obj8(obj_path)
        self.assertEqual(len(parsed.vertices), 3)
        mesh_obj = build_mesh(parsed, "GiganticMesh")
        self.assertIsNotNone(mesh_obj)
        self.assertEqual(len(mesh_obj.data.vertices), 3)
        self.assertEqual(len(mesh_obj.data.polygons), 1)
        self.assertTrue(mesh_obj.data.has_custom_normals)

        # Verify coordinates match transformed XP values (within float32 precision)
        v0 = mesh_obj.data.vertices[0].co
        expected_v0 = xp_to_blender_point(1.0e12, -2.0e12, 3.0e12)
        self.assertAlmostEqual(v0[0] / 1e12, expected_v0[0] / 1e12, places=4)
        self.assertAlmostEqual(v0[1] / 1e12, expected_v0[1] / 1e12, places=4)
        self.assertAlmostEqual(v0[2] / 1e12, expected_v0[2] / 1e12, places=4)

    def test_microscopic_coordinates(self):
        """Verify sub-normal / microscopic coordinates (1e-15) do not underflow or crash."""
        obj_path = os.path.join(self.temp_dir, "microscopic.obj")
        with open(obj_path, "w", encoding="utf-8") as f:
            f.write("I\n800\nOBJ\nTEXTURE none\nPOINT_COUNTS 3 0 0 3\n")
            f.write("VT 1.0e-15 0.0 0.0 0.0 1.0 0.0 0.0 0.0\n")
            f.write("VT 0.0 1.0e-15 0.0 0.0 1.0 0.0 1.0 0.0\n")
            f.write("VT 0.0 0.0 1.0e-15 0.0 1.0 0.0 0.0 1.0\n")
            f.write("IDX10 0 1 2\n")
            f.write("TRIS 0 3\n")

        parsed = parse_obj8(obj_path)
        mesh_obj = build_mesh(parsed, "MicroMesh")
        self.assertIsNotNone(mesh_obj)
        self.assertEqual(len(mesh_obj.data.vertices), 3)
        self.assertTrue(mesh_obj.data.has_custom_normals)

    def test_mixed_scale_coordinates(self):
        """Verify triangle with mixed extreme scales (1e9 to 1e-9) builds cleanly."""
        obj_path = os.path.join(self.temp_dir, "mixed_scale.obj")
        with open(obj_path, "w", encoding="utf-8") as f:
            f.write("I\n800\nOBJ\nTEXTURE none\nPOINT_COUNTS 3 0 0 3\n")
            f.write("VT 1.0e9 0.0 0.0 0.0 1.0 0.0 0.0 0.0\n")
            f.write("VT 0.0 1.0e-9 0.0 0.0 1.0 0.0 1.0 0.0\n")
            f.write("VT 0.0 0.0 1.0 0.0 1.0 0.0 0.0 1.0\n")
            f.write("IDX10 0 1 2\n")
            f.write("TRIS 0 3\n")

        parsed = parse_obj8(obj_path)
        mesh_obj = build_mesh(parsed, "MixedScaleMesh")
        self.assertEqual(len(mesh_obj.data.vertices), 3)
        self.assertTrue(mesh_obj.data.has_custom_normals)


class TestAdversarialTrianglesAndTopology(unittest.TestCase):
    """Stress-tests degenerate triangles, collinear vertices, zero-area faces."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="adv_topo_")
        safe_clean_scene()

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        safe_clean_scene()

    def test_identical_indices_degenerate_triangles(self):
        """Verify degenerate triangles with repeated vertex indices are handled cleanly."""
        obj_path = os.path.join(self.temp_dir, "identical_idx.obj")
        with open(obj_path, "w", encoding="utf-8") as f:
            f.write("I\n800\nOBJ\nTEXTURE none\nPOINT_COUNTS 4 0 0 9\n")
            f.write("VT 0.0 0.0 0.0 0.0 1.0 0.0 0.0 0.0\n")
            f.write("VT 1.0 0.0 0.0 0.0 1.0 0.0 1.0 0.0\n")
            f.write("VT 0.0 0.0 1.0 0.0 1.0 0.0 0.0 1.0\n")
            f.write("VT 2.0 2.0 2.0 0.0 1.0 0.0 0.5 0.5\n")
            # Tri 1: (0, 0, 0) all identical; Tri 2: (1, 1, 2) two identical; Tri 3: (0, 1, 2) valid
            f.write("IDX10 0 0 0 1 1 2 0 1 2\n")
            f.write("TRIS 0 9\n")

        parsed = parse_obj8(obj_path)
        mesh_obj = build_mesh(parsed, "DegenerateIndicesMesh")
        # Degenerate faces should be pruned by me.validate(), surviving valid face remains
        self.assertEqual(len(mesh_obj.data.polygons), 1)
        self.assertEqual(len(mesh_obj.data.vertices), 4)
        self.assertTrue(mesh_obj.data.has_custom_normals)

    def test_collinear_zero_area_triangles(self):
        """Verify collinear vertices (area = 0.0) with distinct indices do not crash validation."""
        obj_path = os.path.join(self.temp_dir, "collinear.obj")
        with open(obj_path, "w", encoding="utf-8") as f:
            f.write("I\n800\nOBJ\nTEXTURE none\nPOINT_COUNTS 3 0 0 3\n")
            f.write("VT 0.0 0.0 0.0 0.0 1.0 0.0 0.0 0.0\n")
            f.write("VT 1.0 0.0 0.0 0.0 1.0 0.0 1.0 0.0\n")
            f.write("VT 2.0 0.0 0.0 0.0 1.0 0.0 0.0 1.0\n")
            f.write("IDX10 0 1 2\n")
            f.write("TRIS 0 3\n")

        parsed = parse_obj8(obj_path)
        mesh_obj = build_mesh(parsed, "CollinearMesh")
        self.assertEqual(len(mesh_obj.data.vertices), 3)
        self.assertTrue(mesh_obj.data.has_custom_normals)

    def test_coincident_distinct_vertices(self):
        """Verify multiple distinct vertices at the exact same 3D position maintain split normals."""
        obj_path = os.path.join(self.temp_dir, "coincident.obj")
        with open(obj_path, "w", encoding="utf-8") as f:
            f.write("I\n800\nOBJ\nTEXTURE none\nPOINT_COUNTS 3 0 0 3\n")
            f.write("VT 5.0 5.0 5.0 0.0 1.0 0.0 0.0 0.0\n")
            f.write("VT 5.0 5.0 5.0 0.0 1.0 0.0 1.0 0.0\n")
            f.write("VT 5.0 5.0 5.0 0.0 1.0 0.0 0.0 1.0\n")
            f.write("IDX10 0 1 2\n")
            f.write("TRIS 0 3\n")

        parsed = parse_obj8(obj_path)
        mesh_obj = build_mesh(parsed, "CoincidentMesh")
        self.assertEqual(len(mesh_obj.data.vertices), 3)
        self.assertTrue(mesh_obj.data.has_custom_normals)


class TestAdversarialNormalVectors(unittest.TestCase):
    """Stress-tests inverted, non-normalized, and split custom normals."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="adv_norm_")
        safe_clean_scene()

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        safe_clean_scene()

    def test_inverted_normal_vectors_preservation(self):
        """Verify custom split normals pointing opposite to face geometric normal are preserved."""
        obj_path = os.path.join(self.temp_dir, "inverted_norm.obj")
        with open(obj_path, "w", encoding="utf-8") as f:
            f.write("I\n800\nOBJ\nTEXTURE none\nPOINT_COUNTS 3 0 0 3\n")
            # Face lies on X-Z plane, geometric normal points +Y in XP (+Z in Blender).
            # Custom normal points -Y in XP (-Z in Blender: 0, 0, -1).
            f.write("VT 0.0 0.0 0.0 0.0 -1.0 0.0 0.0 0.0\n")
            f.write("VT 1.0 0.0 0.0 0.0 -1.0 0.0 1.0 0.0\n")
            f.write("VT 0.0 0.0 1.0 0.0 -1.0 0.0 0.0 1.0\n")
            f.write("IDX10 0 1 2\n")
            f.write("TRIS 0 3\n")

        parsed = parse_obj8(obj_path)
        mesh_obj = build_mesh(parsed, "InvertedNormMesh")
        me = mesh_obj.data

        self.assertTrue(me.has_custom_normals)
        # Check geometric face normal is +Z (due to CCW winding)
        face_normal = me.polygons[0].normal
        self.assertAlmostEqual(face_normal[2], 1.0, places=3)

        # Check loop split normals point downwards (-Z: 0, 0, -1)
        for loop in me.loops:
            ln = loop.normal
            self.assertAlmostEqual(ln[0], 0.0, places=3)
            self.assertAlmostEqual(ln[1], 0.0, places=3)
            self.assertAlmostEqual(ln[2], -1.0, places=3)

    def test_zero_and_subthreshold_normals_fallback(self):
        """Verify zero-length and microscopic normal vectors normalize to fallback unit normal."""
        obj_path = os.path.join(self.temp_dir, "zero_norm.obj")
        with open(obj_path, "w", encoding="utf-8") as f:
            f.write("I\n800\nOBJ\nTEXTURE none\nPOINT_COUNTS 3 0 0 3\n")
            f.write("VT 0.0 0.0 0.0 0.0 0.0 0.0 0.0 0.0\n")          # Zero normal
            f.write("VT 1.0 0.0 0.0 1.0e-8 1.0e-8 1.0e-8 1.0 0.0\n")  # Subthreshold (< 1e-6)
            f.write("VT 0.0 0.0 1.0 0.0 1.0 0.0 0.0 1.0\n")          # Standard normal
            f.write("IDX10 0 1 2\n")
            f.write("TRIS 0 3\n")

        parsed = parse_obj8(obj_path)
        # Check all parsed normals have unit magnitude
        for i, n in enumerate(parsed.normals):
            mag = math.sqrt(n[0]**2 + n[1]**2 + n[2]**2)
            self.assertAlmostEqual(mag, 1.0, places=5, msg=f"Normal {i} must be unit length")

        mesh_obj = build_mesh(parsed, "ZeroNormMesh")
        self.assertTrue(mesh_obj.data.has_custom_normals)

    def test_massive_unnormalized_normals(self):
        """Verify massive unnormalized normal vectors are normalized to unit length."""
        obj_path = os.path.join(self.temp_dir, "massive_norm.obj")
        with open(obj_path, "w", encoding="utf-8") as f:
            f.write("I\n800\nOBJ\nTEXTURE none\nPOINT_COUNTS 3 0 0 3\n")
            f.write("VT 0.0 0.0 0.0 1000.0 -2500.0 5000.0 0.0 0.0\n")
            f.write("VT 1.0 0.0 0.0 -300.0 400.0 0.0 1.0 0.0\n")
            f.write("VT 0.0 0.0 1.0 0.0 0.0 -9999.0 0.0 1.0\n")
            f.write("IDX10 0 1 2\n")
            f.write("TRIS 0 3\n")

        parsed = parse_obj8(obj_path)
        for i, n in enumerate(parsed.normals):
            mag = math.sqrt(n[0]**2 + n[1]**2 + n[2]**2)
            self.assertAlmostEqual(mag, 1.0, places=5, msg=f"Massive normal {i} must be normalized to unit length")

        mesh_obj = build_mesh(parsed, "MassiveNormMesh")
        self.assertTrue(mesh_obj.data.has_custom_normals)

    def test_sharp_crease_split_normals(self):
        """Verify coincident vertices with different normals preserve independent corner normals."""
        obj_path = os.path.join(self.temp_dir, "sharp_crease.obj")
        with open(obj_path, "w", encoding="utf-8") as f:
            f.write("I\n800\nOBJ\nTEXTURE none\nPOINT_COUNTS 6 0 0 6\n")
            # Face 1: normal pointing +Y in XP (+Z in Blender)
            f.write("VT 0.0 0.0 0.0 0.0 1.0 0.0 0.0 0.0\n") # v0
            f.write("VT 1.0 0.0 0.0 0.0 1.0 0.0 1.0 0.0\n") # v1
            f.write("VT 0.0 0.0 1.0 0.0 1.0 0.0 0.0 1.0\n") # v2
            # Face 2: sharing coincident position at v0 and v1, but normal pointing +X in XP (+X in Blender)
            f.write("VT 0.0 0.0 0.0 1.0 0.0 0.0 0.0 0.0\n") # v3 (coincident with v0)
            f.write("VT 1.0 0.0 0.0 1.0 0.0 0.0 1.0 0.0\n") # v4 (coincident with v1)
            f.write("VT 0.0 1.0 0.0 1.0 0.0 0.0 0.0 1.0\n") # v5
            f.write("IDX10 0 1 2 3 4 5\n")
            f.write("TRIS 0 6\n")

        parsed = parse_obj8(obj_path)
        mesh_obj = build_mesh(parsed, "SharpCreaseMesh")
        me = mesh_obj.data
        self.assertEqual(len(me.vertices), 6)
        self.assertEqual(len(me.polygons), 2)
        self.assertTrue(me.has_custom_normals)

        # Loop 0 (from face 1, vert 0) must have normal +Z (0, 0, 1)
        # Loop 3 (from face 2, vert 3) must have normal +X (1, 0, 0)
        loops = list(me.loops)
        self.assertAlmostEqual(loops[0].normal[2], 1.0, places=3)
        self.assertAlmostEqual(loops[3].normal[0], 1.0, places=3)

    def test_oracle_normal_preservation_fidelity(self):
        """Mathematical oracle: verify arbitrary 3D direction normals maintain dot product >= 0.9999."""
        obj_path = os.path.join(self.temp_dir, "oracle_norm.obj")
        # 3 arbitrary, non-axis-aligned unit vectors in X-Plane space
        raw_norms = [
            (1.0 / math.sqrt(3), 1.0 / math.sqrt(3), 1.0 / math.sqrt(3)),
            (-0.36, 0.48, 0.8),
            (0.2, -0.6, 0.774596669),
        ]
        with open(obj_path, "w", encoding="utf-8") as f:
            f.write("I\n800\nOBJ\nTEXTURE none\nPOINT_COUNTS 3 0 0 3\n")
            f.write(f"VT 0.0 0.0 0.0 {raw_norms[0][0]} {raw_norms[0][1]} {raw_norms[0][2]} 0.0 0.0\n")
            f.write(f"VT 1.0 0.0 0.0 {raw_norms[1][0]} {raw_norms[1][1]} {raw_norms[1][2]} 1.0 0.0\n")
            f.write(f"VT 0.0 0.0 1.0 {raw_norms[2][0]} {raw_norms[2][1]} {raw_norms[2][2]} 0.0 1.0\n")
            f.write("IDX10 0 1 2\n")
            f.write("TRIS 0 3\n")

        parsed = parse_obj8(obj_path)
        mesh_obj = build_mesh(parsed, "OracleNormMesh")
        me = mesh_obj.data
        self.assertTrue(me.has_custom_normals)

        # In CCW winding reversed triangle (0, 2, 1):
        # Loop 0 is vertex 0, Loop 1 is vertex 2, Loop 2 is vertex 1
        expected_blender_norms = [xp_to_blender_vector(*n) for n in raw_norms]
        for loop in me.loops:
            v_idx = loop.vertex_index
            exp_n = Vector(expected_blender_norms[v_idx]).normalized()
            act_n = Vector(loop.normal).normalized()
            dot_prod = exp_n.dot(act_n)
            self.assertGreaterEqual(
                dot_prod, 0.9999,
                f"Vertex {v_idx} normal dot product {dot_prod:.6f} < 0.9999 (expected {exp_n}, got {act_n})"
            )


class TestAdversarialTRISBlocks(unittest.TestCase):
    """Stress-tests multiple TRIS blocks, non-contiguous slices, and boundary counts."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="adv_tris_")
        safe_clean_scene()

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        safe_clean_scene()

    def test_multiple_distinct_tris_blocks(self):
        """Verify multiple separate TRIS blocks accumulate all triangles."""
        obj_path = os.path.join(self.temp_dir, "multi_tris.obj")
        with open(obj_path, "w", encoding="utf-8") as f:
            f.write("I\n800\nOBJ\nTEXTURE none\nPOINT_COUNTS 9 0 0 9\n")
            # 3 distinct triangles (9 vertices)
            for i in range(3):
                f.write(f"VT {i*2}.0 0.0 0.0 0.0 1.0 0.0 0.0 0.0\n")
                f.write(f"VT {i*2+1}.0 0.0 0.0 0.0 1.0 0.0 1.0 0.0\n")
                f.write(f"VT {i*2}.0 0.0 1.0 0.0 1.0 0.0 0.0 1.0\n")
            f.write("IDX10 0 1 2 3 4 5 6 7 8\n")
            # Separate TRIS blocks
            f.write("TRIS 0 3\n")
            f.write("TRIS 3 3\n")
            f.write("TRIS 6 3\n")

        parsed = parse_obj8(obj_path)
        self.assertEqual(len(parsed.commands), 3)
        mesh_obj = build_mesh(parsed, "MultiTrisMesh")
        self.assertEqual(len(mesh_obj.data.polygons), 3)
        self.assertEqual(len(mesh_obj.data.vertices), 9)
        self.assertTrue(mesh_obj.data.has_custom_normals)

    def test_non_contiguous_and_out_of_order_tris(self):
        """Verify TRIS blocks referencing non-contiguous and out-of-order index slices."""
        obj_path = os.path.join(self.temp_dir, "non_contiguous_tris.obj")
        with open(obj_path, "w", encoding="utf-8") as f:
            f.write("I\n800\nOBJ\nTEXTURE none\nPOINT_COUNTS 9 0 0 9\n")
            for i in range(3):
                f.write(f"VT {i*2}.0 0.0 0.0 0.0 1.0 0.0 0.0 0.0\n")
                f.write(f"VT {i*2+1}.0 0.0 0.0 0.0 1.0 0.0 1.0 0.0\n")
                f.write(f"VT {i*2}.0 0.0 1.0 0.0 1.0 0.0 0.0 1.0\n")
            f.write("IDX10 0 1 2 3 4 5 6 7 8\n")
            # Draw slice 6..8 first, then slice 0..2 (skipping 3..5)
            f.write("TRIS 6 3\n")
            f.write("TRIS 0 3\n")

        parsed = parse_obj8(obj_path)
        mesh_obj = build_mesh(parsed, "NonContigTrisMesh")
        self.assertEqual(len(mesh_obj.data.polygons), 2)
        self.assertEqual(len(mesh_obj.data.vertices), 9)
        self.assertTrue(mesh_obj.data.has_custom_normals)

    def test_tris_count_not_divisible_by_three(self):
        """Verify non-multiple-of-three TRIS count safely discards orphan indices."""
        obj_path = os.path.join(self.temp_dir, "partial_tris.obj")
        with open(obj_path, "w", encoding="utf-8") as f:
            f.write("I\n800\nOBJ\nTEXTURE none\nPOINT_COUNTS 6 0 0 6\n")
            for i in range(2):
                f.write(f"VT {i*2}.0 0.0 0.0 0.0 1.0 0.0 0.0 0.0\n")
                f.write(f"VT {i*2+1}.0 0.0 0.0 0.0 1.0 0.0 1.0 0.0\n")
                f.write(f"VT {i*2}.0 0.0 1.0 0.0 1.0 0.0 0.0 1.0\n")
            f.write("IDX10 0 1 2 3 4 5\n")
            # TRIS count is 5 (1 complete triangle + 2 leftover indices)
            f.write("TRIS 0 5\n")

        parsed = parse_obj8(obj_path)
        mesh_obj = build_mesh(parsed, "PartialTrisMesh")
        self.assertEqual(len(mesh_obj.data.polygons), 1)
        self.assertTrue(mesh_obj.data.has_custom_normals)

    def test_out_of_bounds_index_resilience(self):
        """Verify indices referencing nonexistent vertex indices are safely handled by validate()."""
        obj_path = os.path.join(self.temp_dir, "oob_idx.obj")
        with open(obj_path, "w", encoding="utf-8") as f:
            f.write("I\n800\nOBJ\nTEXTURE none\nPOINT_COUNTS 3 0 0 6\n")
            f.write("VT 0.0 0.0 0.0 0.0 1.0 0.0 0.0 0.0\n")
            f.write("VT 1.0 0.0 0.0 0.0 1.0 0.0 1.0 0.0\n")
            f.write("VT 0.0 0.0 1.0 0.0 1.0 0.0 0.0 1.0\n")
            # First triangle references invalid vertex index 999; second is valid
            f.write("IDX10 0 1 999 0 1 2\n")
            f.write("TRIS 0 6\n")

        parsed = parse_obj8(obj_path)
        mesh_obj = build_mesh(parsed, "OOBIdxMesh")
        self.assertEqual(len(mesh_obj.data.polygons), 1)
        self.assertEqual(len(mesh_obj.data.vertices), 3)
        self.assertTrue(mesh_obj.data.has_custom_normals)


class TestEmptyAndMalformedModels(unittest.TestCase):
    """Stress-tests empty files, point clouds, corrupt lines, and edge formats."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="adv_empty_")
        safe_clean_scene()

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        safe_clean_scene()

    def test_point_cloud_with_zero_tris(self):
        """Verify OBJ8 with vertices but no TRIS commands creates valid point cloud mesh."""
        obj_path = os.path.join(self.temp_dir, "point_cloud.obj")
        with open(obj_path, "w", encoding="utf-8") as f:
            f.write("I\n800\nOBJ\nTEXTURE none\nPOINT_COUNTS 5 0 0 0\n")
            for i in range(5):
                f.write(f"VT {float(i)} 0.0 0.0 0.0 1.0 0.0 0.0 0.0\n")

        parsed = parse_obj8(obj_path)
        mesh_obj = build_mesh(parsed, "PointCloudMesh")
        self.assertEqual(len(mesh_obj.data.vertices), 5)
        self.assertEqual(len(mesh_obj.data.polygons), 0)
        self.assertTrue(mesh_obj.data.has_custom_normals)

    def test_corrupt_vt_lines_skip_and_survive(self):
        """Verify corrupted VT lines are skipped gracefully while surviving geometry imports."""
        obj_path = os.path.join(self.temp_dir, "corrupt_lines.obj")
        with open(obj_path, "w", encoding="utf-8") as f:
            f.write("I\n800\nOBJ\nTEXTURE none\nPOINT_COUNTS 4 0 0 3\n")
            f.write("VT 0.0 0.0 0.0 0.0 1.0 0.0 0.0 0.0\n")
            f.write("VT NOT_A_FLOAT 0.0 0.0 0.0 1.0 0.0 0.0 0.0\n") # Corrupt line
            f.write("VT 1.0 0.0 0.0 0.0 1.0 0.0 1.0 0.0\n")
            f.write("VT 0.0 0.0 1.0 0.0 1.0 0.0 0.0 1.0\n")
            f.write("IDX10 0 1 2\n")
            f.write("TRIS 0 3\n")

        parsed = parse_obj8(obj_path)
        self.assertEqual(len(parsed.vertices), 3) # Corrupt line skipped
        mesh_obj = build_mesh(parsed, "CorruptLinesMesh")
        self.assertEqual(len(mesh_obj.data.vertices), 3)
        self.assertEqual(len(mesh_obj.data.polygons), 1)
        self.assertTrue(mesh_obj.data.has_custom_normals)


if __name__ == '__main__':
    unittest.main()
