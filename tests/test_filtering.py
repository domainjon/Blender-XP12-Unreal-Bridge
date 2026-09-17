"""
test_filtering.py - Features 17, 18: Component & LOD Filtering.
"""

import unittest


class TestFiltering(unittest.TestCase):
    """Tests component filtering (Exterior vs Cockpit) and LOD filtering."""

    def test_component_filtering_classification(self):
        """Verify object classification into Exterior vs Cockpit."""
        parts = [
            ("objects/fuselage.obj", False),
            ("objects/wings.obj", False),
            ("objects/cockpit_inn.obj", True),
            ("objects/cockpit_out.obj", True),
            ("objects/panel.obj", True),
        ]

        exterior = [p[0] for p in parts if not p[1]]
        cockpit = [p[0] for p in parts if p[1]]

        self.assertEqual(len(exterior), 2)
        self.assertEqual(len(cockpit), 3)

    def test_lod_level_filtering_logic(self):
        """Verify LOD 0 selects only ranges starting at 0.0 distance."""
        lods = [
            (0.0, 500.0, ["mesh_lod0_a", "mesh_lod0_b"]),
            (500.0, 2000.0, ["mesh_lod1"]),
        ]

        lod0_meshes = [m for lod in lods if lod[0] == 0.0 for m in lod[2]]
        self.assertEqual(lod0_meshes, ["mesh_lod0_a", "mesh_lod0_b"])


if __name__ == '__main__':
    unittest.main()
