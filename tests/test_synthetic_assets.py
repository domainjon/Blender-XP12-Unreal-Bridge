"""
test_synthetic_assets.py - Unit tests verifying the synthetic asset generator (Feature 24).
"""

import os
import unittest
import tempfile
import shutil
import struct

from tests.synthetic_assets import (
    write_rgba_png,
    create_synthetic_normal_metalness_texture,
    create_synthetic_albedo_texture,
    OBJ8Builder,
    create_minimal_obj8,
    create_animated_aircraft_obj8,
    create_lod_obj8,
    create_corner_case_obj8,
    create_synthetic_acf,
    create_full_synthetic_aircraft_project
)


class TestSyntheticAssets(unittest.TestCase):
    """Verifies synthetic asset generation functions producing valid X-Plane 12 test fixtures."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_synthetic_")

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_png_writer_produces_valid_png_header(self):
        """Verify PNG writer generates valid standard PNG signature and chunks."""
        filepath = os.path.join(self.temp_dir, "test.png")
        # 2x2 image = 16 bytes
        rgba = bytes([255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 128, 128, 128, 255])
        write_rgba_png(filepath, 2, 2, rgba)

        self.assertTrue(os.path.exists(filepath))
        with open(filepath, 'rb') as f:
            data = f.read()

        # PNG Signature
        self.assertEqual(data[:8], b'\x89PNG\r\n\x1a\n')

        # IHDR chunk: 4 bytes length, 'IHDR', 13 bytes data
        ihdr_len = struct.unpack('>I', data[8:12])[0]
        self.assertEqual(ihdr_len, 13)
        self.assertEqual(data[12:16], b'IHDR')
        w, h, depth, ctype = struct.unpack('>IIBB', data[16:26])
        self.assertEqual(w, 2)
        self.assertEqual(h, 2)
        self.assertEqual(depth, 8)
        self.assertEqual(ctype, 6)  # RGBA

        # Ends with IEND
        self.assertTrue(data.endswith(b'IEND\xaeB`\x82'))

    def test_normal_metalness_texture_creation(self):
        """Verify 4-channel normal metalness texture is generated."""
        filepath = os.path.join(self.temp_dir, "normal_metalness.png")
        out_path = create_synthetic_normal_metalness_texture(filepath, 16, 16, 0.5, 0.5, 0.25, 0.75)
        self.assertTrue(os.path.exists(out_path))
        self.assertGreater(os.path.getsize(out_path), 50)

    def test_albedo_texture_creation(self):
        """Verify albedo diffuse texture is generated."""
        filepath = os.path.join(self.temp_dir, "albedo.png")
        out_path = create_synthetic_albedo_texture(filepath, 16, 16, 200, 210, 220, 255)
        self.assertTrue(os.path.exists(out_path))
        self.assertGreater(os.path.getsize(out_path), 50)

    def test_minimal_obj8_generation(self):
        """Verify minimal cube OBJ8 file syntax and data tables."""
        filepath = os.path.join(self.temp_dir, "cube.obj")
        out_path = create_minimal_obj8(filepath, "diffuse.png", "normal.png")
        self.assertTrue(os.path.exists(out_path))

        with open(out_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]

        # Header
        self.assertEqual(lines[0], "I")
        self.assertEqual(lines[1], "800")
        self.assertEqual(lines[2], "OBJ")

        # Directives
        self.assertIn("TEXTURE diffuse.png", lines)
        self.assertIn("TEXTURE_NORMAL normal.png", lines)
        self.assertIn("NORMAL_METALNESS", lines)

        # POINT_COUNTS
        pt_lines = [l for l in lines if l.startswith("POINT_COUNTS")]
        self.assertEqual(len(pt_lines), 1)
        tokens = pt_lines[0].split()
        vt_count = int(tokens[1])
        idx_count = int(tokens[4])
        self.assertEqual(vt_count, 24)
        self.assertEqual(idx_count, 36)  # 12 triangles * 3

        # VT lines count
        vt_lines = [l for l in lines if l.startswith("VT ")]
        self.assertEqual(len(vt_lines), 24)

        # TRIS command
        tris_lines = [l for l in lines if l.startswith("TRIS ")]
        self.assertGreaterEqual(len(tris_lines), 1)
        tris_tokens = tris_lines[0].split()
        self.assertEqual(tris_tokens[1], "0")
        self.assertEqual(tris_tokens[2], "36")

    def test_animated_obj8_generation(self):
        """Verify animated OBJ8 file contains ANIM_begin, ANIM_rotate, ANIM_trans, DataRefs, and nesting."""
        filepath = os.path.join(self.temp_dir, "animated.obj")
        out_path = create_animated_aircraft_obj8(filepath)
        self.assertTrue(os.path.exists(out_path))

        with open(out_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("ANIM_begin", content)
        self.assertIn("ANIM_end", content)
        self.assertIn("ANIM_rotate", content)
        self.assertIn("ANIM_trans", content)
        self.assertIn("sim/flightmodel2/controls/left_aileron", content)
        self.assertIn("sim/flightmodel2/controls/elevator", content)
        self.assertIn("sim/flightmodel2/controls/rudder", content)
        self.assertIn("sim/flightmodel2/gear/deploy_ratio", content)
        self.assertIn("sim/flightmodel2/gear/steer_deg", content)

        # Check begin / end balance
        begin_count = content.count("ANIM_begin")
        end_count = content.count("ANIM_end")
        self.assertEqual(begin_count, end_count, "ANIM_begin and ANIM_end counts must match")
        self.assertEqual(begin_count, 5, "Expected 5 animation blocks (aileron, elev, rudder, gear, steer)")

    def test_lod_obj8_generation(self):
        """Verify ATTR_LOD commands are properly formatted in LOD OBJ8."""
        filepath = os.path.join(self.temp_dir, "lod.obj")
        out_path = create_lod_obj8(filepath)
        self.assertTrue(os.path.exists(out_path))

        with open(out_path, 'r', encoding='utf-8') as f:
            lines = [l.strip() for l in f if l.startswith("ATTR_LOD")]

        self.assertEqual(len(lines), 2)
        self.assertIn("ATTR_LOD 0.0 500.0", lines[0])
        self.assertIn("ATTR_LOD 500.0 2500.0", lines[1])

    def test_corner_cases_generation(self):
        """Verify corner case generator outputs valid specialized fixtures."""
        cases = ['empty_lines', 'zero_bone_length', 'degenerate_tris', 'boundary_dataref', 'deep_nesting', 'missing_textures']
        for case in cases:
            filepath = os.path.join(self.temp_dir, f"corner_{case}.obj")
            out_path = create_corner_case_obj8(filepath, case)
            self.assertTrue(os.path.exists(out_path), f"Failed to create corner case {case}")
            self.assertGreater(os.path.getsize(out_path), 0)

    def test_synthetic_acf_generation(self):
        """Verify Plane Maker ACF file generation with attached objects and spatial coordinates."""
        filepath = os.path.join(self.temp_dir, "test.acf")
        attached = [
            {'path': 'objects/fuselage.obj', 'xyz': (0.0, 0.0, 0.0), 'is_cockpit': 0, 'lighting': 0},
            {'path': 'objects/cockpit.obj', 'xyz': (0.0, 1.2, -1.5), 'is_cockpit': 1, 'lighting': 1}
        ]
        out_path = create_synthetic_acf(filepath, tailnum="N999XP", aircraft_name="Test Plane", icao="TEST", attached_objects=attached)
        self.assertTrue(os.path.exists(out_path))

        with open(out_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertTrue(content.startswith("I\n1200 Version\nACF\n"))
        self.assertIn("P acf/_tailnum N999XP", content)
        self.assertIn("P acf/_misc_obj_name/0 objects/fuselage.obj", content)
        self.assertIn("P acf/_misc_obj_is_cockpit/0 0", content)
        self.assertIn("P acf/_misc_obj_name/1 objects/cockpit.obj", content)
        self.assertIn("P acf/_misc_obj_is_cockpit/1 1", content)

    def test_full_synthetic_project_assembly(self):
        """Verify complete aircraft project assembly directory structure."""
        proj_dir = os.path.join(self.temp_dir, "full_aircraft")
        res = create_full_synthetic_aircraft_project(proj_dir)

        for key, path in res.items():
            self.assertTrue(os.path.exists(path), f"File {key} at {path} does not exist")


if __name__ == '__main__':
    unittest.main()
