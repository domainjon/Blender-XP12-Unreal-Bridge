"""
test_roundtrip_obj8.py - Feature 23: Round-Trip OBJ8 Exporter & Geometric Parity.
"""

import unittest
from io_scene_xpobj.constants import (
    xp_to_blender_point,
    blender_to_xp_point,
    reverse_winding_triangle,
)


class TestRoundTripOBJ8(unittest.TestCase):
    """Tests round-trip export logic to valid X-Plane 12 OBJ8 format."""

    def test_roundtrip_coordinate_inversion(self):
        """Verify (X, Y, Z) point transforms to Blender and back with 100% precision."""
        xp_points = [
            (0.0, 0.0, 0.0),
            (10.5, -2.3, 4.8),
            (-100.25, 50.0, -12.5),
        ]

        for pt in xp_points:
            bl = xp_to_blender_point(*pt)
            xp_rec = blender_to_xp_point(*bl)
            self.assertAlmostEqual(pt[0], xp_rec[0], places=6)
            self.assertAlmostEqual(pt[1], xp_rec[1], places=6)
            self.assertAlmostEqual(pt[2], xp_rec[2], places=6)

    def test_roundtrip_winding_order(self):
        """Verify double reversal of face winding returns original index sequence."""
        cw_orig = (0, 1, 2)
        ccw = reverse_winding_triangle(*cw_orig)
        cw_roundtrip = reverse_winding_triangle(*ccw)
        self.assertEqual(cw_orig, cw_roundtrip)


if __name__ == '__main__':
    unittest.main()
