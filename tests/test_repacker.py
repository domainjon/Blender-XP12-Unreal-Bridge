"""
test_repacker.py - Features 14, 15, 16: DirectX Normal & ORM Texture Repacker.
"""

import os
import time
import tempfile
import shutil
import unittest
import numpy as np
import bpy

from io_scene_xpobj.texture_repacker import (
    repack_xplane_normal_texture,
    repack_textures,
    repack_normal_and_orm_arrays,
)
from tests.synthetic_assets import create_synthetic_normal_metalness_texture


def safe_clean_scene():
    for img in list(bpy.data.images):
        bpy.data.images.remove(img, do_unlink=True)


class TestRepacker(unittest.TestCase):
    """Tests vectorized NumPy conversion from NORMAL_METALNESS to DirectX Normal and ORM."""

    def setUp(self):
        safe_clean_scene()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        safe_clean_scene()
        if os.path.isdir(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_vectorized_repacker_logic(self):
        """Verify vectorization of DirectX Normal (-Y Green) and ORM packing."""
        # Known pixel: R=0.5, G=0.8, B=0.75, A=0.25
        # Reconstructed Normal Z: sqrt(max(0, 1 - 0.0^2 - 0.6^2)) = 0.8
        # DirectX: R=0.5, G=0.2, B=0.8*0.5+0.5=0.9, A=1.0
        # ORM: R=1.0 (AO), G=0.25 (Roughness), B=0.75 (Metallic), A=1.0
        raw = np.array([[[0.5, 0.8, 0.75, 0.25]]], dtype=np.float32)

        dx_normal, orm = repack_normal_and_orm_arrays(raw)

        self.assertAlmostEqual(float(dx_normal[0, 0, 0]), 0.5, places=3)
        self.assertAlmostEqual(float(dx_normal[0, 0, 1]), 0.2, places=3)
        self.assertAlmostEqual(float(dx_normal[0, 0, 2]), 0.9, places=3)
        self.assertAlmostEqual(float(dx_normal[0, 0, 3]), 1.0, places=3)

        self.assertAlmostEqual(float(orm[0, 0, 0]), 1.0, places=3)
        self.assertAlmostEqual(float(orm[0, 0, 1]), 0.25, places=3)
        self.assertAlmostEqual(float(orm[0, 0, 2]), 0.75, places=3)
        self.assertAlmostEqual(float(orm[0, 0, 3]), 1.0, places=3)

    def test_repack_normal_and_orm_arrays_boundaries(self):
        """Verify boundary cases, custom AO, and clamping when Nx^2 + Ny^2 >= 1.0."""
        # Flat normal: R=0.5, G=0.5 -> Nx=0, Ny=0 -> Nz=1.0 -> Blue_DX=1.0
        # Extreme pixel: R=1.0, G=1.0 -> Nx=1, Ny=1 -> Nx^2 + Ny^2 = 2.0 -> Nz=0.0 -> Blue_DX=0.5
        pixels = np.array([
            [[0.5, 0.5, 0.0, 1.0]],
            [[1.0, 1.0, 1.0, 0.0]]
        ], dtype=np.float32)

        dx_normal, orm = repack_normal_and_orm_arrays(pixels, default_ao=0.8)

        # Flat normal checks
        self.assertAlmostEqual(float(dx_normal[0, 0, 0]), 0.5, places=3)
        self.assertAlmostEqual(float(dx_normal[0, 0, 1]), 0.5, places=3)
        self.assertAlmostEqual(float(dx_normal[0, 0, 2]), 1.0, places=3)
        self.assertAlmostEqual(float(orm[0, 0, 0]), 0.8, places=3)

        # Clamped normal checks
        self.assertAlmostEqual(float(dx_normal[1, 0, 0]), 1.0, places=3)
        self.assertAlmostEqual(float(dx_normal[1, 0, 1]), 0.0, places=3)
        self.assertAlmostEqual(float(dx_normal[1, 0, 2]), 0.5, places=3)
        self.assertAlmostEqual(float(orm[1, 0, 1]), 0.0, places=3)
        self.assertAlmostEqual(float(orm[1, 0, 2]), 1.0, places=3)

    def test_repack_xplane_normal_texture_file_io(self):
        """Verify full file I/O pipeline using Blender C-buffers and PNG saving."""
        src_path = os.path.join(self.temp_dir, "fuselage_norm.png")
        create_synthetic_normal_metalness_texture(src_path, 64, 64, norm_x=0.5, norm_y=0.8, metallic=0.75, roughness=0.25)

        out_dict = repack_xplane_normal_texture(
            source_normal_path=src_path,
            output_dir=self.temp_dir
        )

        self.assertIn('directx_normal', out_dict)
        self.assertIn('orm', out_dict)

        dx_path = out_dict['directx_normal']
        orm_path = out_dict['orm']

        self.assertTrue(os.path.isfile(dx_path))
        self.assertTrue(os.path.isfile(orm_path))
        self.assertTrue(dx_path.endswith("fuselage_Normal_DX.png"))
        self.assertTrue(orm_path.endswith("fuselage_ORM.png"))

        # Load back repacked images and verify pixel precision
        img_dx = bpy.data.images.load(dx_path)
        raw_dx = np.empty(64 * 64 * 4, dtype=np.float32)
        img_dx.pixels.foreach_get(raw_dx)

        # R=0.5, G=0.2, B=0.9
        self.assertAlmostEqual(float(raw_dx[0]), 0.5, delta=0.01)
        self.assertAlmostEqual(float(raw_dx[1]), 0.2, delta=0.01)
        self.assertAlmostEqual(float(raw_dx[2]), 0.9, delta=0.01)
        self.assertAlmostEqual(float(raw_dx[3]), 1.0, delta=0.01)

        img_orm = bpy.data.images.load(orm_path)
        raw_orm = np.empty(64 * 64 * 4, dtype=np.float32)
        img_orm.pixels.foreach_get(raw_orm)

        # R=1.0 (AO), G=0.25 (Roughness), B=0.75 (Metallic), A=1.0
        self.assertAlmostEqual(float(raw_orm[0]), 1.0, delta=0.01)
        self.assertAlmostEqual(float(raw_orm[1]), 0.25, delta=0.01)
        self.assertAlmostEqual(float(raw_orm[2]), 0.75, delta=0.01)
        self.assertAlmostEqual(float(raw_orm[3]), 1.0, delta=0.01)

        bpy.data.images.remove(img_dx)
        bpy.data.images.remove(img_orm)

    def test_repack_textures_interface_contract(self):
        """Verify repack_textures alias contract matching PROJECT.md."""
        src_path = os.path.join(self.temp_dir, "wing_normal.png")
        create_synthetic_normal_metalness_texture(src_path, 32, 32)

        res = repack_textures(src_path, output_dir=self.temp_dir)
        self.assertIn('directx_normal', res)
        self.assertIn('orm', res)
        self.assertTrue(os.path.isfile(res['directx_normal']))
        self.assertTrue(os.path.isfile(res['orm']))

    def test_performance_2k_vectorization(self):
        """Verify 2048x2048 repacking computation completes in <0.20s."""
        w, h = 2048, 2048
        raw = np.full((h, w, 4), 0.5, dtype=np.float32)
        raw[..., 1] = 0.8
        raw[..., 2] = 0.75
        raw[..., 3] = 0.25

        t0 = time.perf_counter()
        dx_normal, orm = repack_normal_and_orm_arrays(raw)
        elapsed = time.perf_counter() - t0

        self.assertLess(elapsed, 0.20, f"Vectorization took {elapsed:.4f}s, expected < 0.20s")

    def test_no_pil_pillow_dependency(self):
        """Verify implementation strictly avoids PIL / Pillow external dependency."""
        import sys
        import io_scene_xpobj.texture_repacker as tr
        # Check module imports
        self.assertNotIn("PIL", sys.modules)
        self.assertNotIn("Pillow", sys.modules)


if __name__ == '__main__':
    unittest.main()
