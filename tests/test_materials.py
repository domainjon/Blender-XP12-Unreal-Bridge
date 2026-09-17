"""
test_materials.py - Features 12, 13: Principled BSDF v2 PBR Shaders & Normal Z Math.
"""

import os
import math
import tempfile
import shutil
import unittest
import bpy

from io_scene_xpobj.materials import create_xplane_pbr_material
from io_scene_xpobj.import_obj8 import parse_obj8, build_mesh
from tests.synthetic_assets import (
    create_synthetic_albedo_texture,
    create_synthetic_normal_metalness_texture,
    create_minimal_obj8,
)


def safe_clean_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh, do_unlink=True)
    for mat in list(bpy.data.materials):
        bpy.data.materials.remove(mat, do_unlink=True)
    for img in list(bpy.data.images):
        bpy.data.images.remove(img, do_unlink=True)


class TestMaterials(unittest.TestCase):
    """Tests Blender 4.3 Principled BSDF v2 shader networks and X-Plane 12 Normal Z derivation."""

    def setUp(self):
        safe_clean_scene()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        safe_clean_scene()
        if os.path.isdir(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_principled_bsdf_v2_sockets(self):
        """Verify Principled BSDF v2 socket identifiers in Blender 4.3."""
        mat = bpy.data.materials.new("TestMat")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        self.assertIsNotNone(bsdf)

        required = ['Base Color', 'Metallic', 'Roughness', 'Normal', 'IOR', 'Alpha', 'Emission Color', 'Emission Strength']
        for s in required:
            self.assertIn(s, bsdf.inputs)

    def test_normal_z_derivation_numerical(self):
        """Verify formula Normal Z = sqrt(max(0, 1 - X^2 - Y^2))."""
        # (0.0, 0.0) -> 1.0
        self.assertAlmostEqual(math.sqrt(max(0.0, 1.0 - (0.0**2 + 0.0**2))), 1.0)
        # (0.6, 0.8) -> 0.0
        self.assertAlmostEqual(math.sqrt(max(0.0, 1.0 - (0.6**2 + 0.8**2))), 0.0)
        # (0.5, 0.5) -> sqrt(0.5)
        self.assertAlmostEqual(math.sqrt(max(0.0, 1.0 - (0.5**2 + 0.5**2))), math.sqrt(0.5))
        # Clamping when > 1.0
        self.assertEqual(math.sqrt(max(0.0, 1.0 - (1.0**2 + 1.0**2))), 0.0)

    def test_create_xplane_pbr_material_full_network(self):
        """Verify create_xplane_pbr_material constructs complete shader network with procedural Normal Z."""
        albedo_path = os.path.join(self.temp_dir, "test_paint.png")
        create_synthetic_albedo_texture(albedo_path, 32, 32)

        normal_path = os.path.join(self.temp_dir, "test_paint_norm.png")
        create_synthetic_normal_metalness_texture(normal_path, 32, 32)

        lit_path = os.path.join(self.temp_dir, "test_paint_lit.png")
        create_synthetic_albedo_texture(lit_path, 32, 32, r=255, g=240, b=100)

        mat = create_xplane_pbr_material(
            mat_name="Aircraft_PBR",
            texture_path=albedo_path,
            normal_texture_path=normal_path,
            lit_texture_path=lit_path,
            use_procedural_normal_z=True
        )

        self.assertIsNotNone(mat)
        self.assertTrue(mat.use_nodes)
        nodes = mat.node_tree.nodes

        # Verify essential node presence
        self.assertIn("Principled_BSDF", nodes)
        self.assertIn("Material_Output", nodes)
        self.assertIn("Albedo_Texture", nodes)
        self.assertIn("Emissive_Texture", nodes)
        self.assertIn("Normal_Texture", nodes)
        self.assertIn("Separate_RGBA", nodes)
        self.assertIn("Combine_XYZ", nodes)
        self.assertIn("Normal_Map", nodes)

        # Verify math nodes for Normal Z
        self.assertIn("Normal_X2", nodes)
        self.assertIn("Normal_Y2", nodes)
        self.assertIn("Normal_X2_plus_Y2", nodes)
        self.assertIn("Normal_1_minus_sum", nodes)
        self.assertIn("Normal_Max_Zero", nodes)
        self.assertIn("Normal_Sqrt_Z", nodes)

        bsdf = nodes["Principled_BSDF"]

        # Base Color from Albedo
        base_color_link = bsdf.inputs["Base Color"].links[0]
        self.assertEqual(base_color_link.from_node.name, "Albedo_Texture")
        self.assertEqual(base_color_link.from_socket.name, "Color")

        # Roughness from Normal Texture Alpha
        roughness_link = bsdf.inputs["Roughness"].links[0]
        self.assertEqual(roughness_link.from_node.name, "Normal_Texture")
        self.assertEqual(roughness_link.from_socket.name, "Alpha")

        # Metallic from Separate Color Blue
        metallic_link = bsdf.inputs["Metallic"].links[0]
        self.assertEqual(metallic_link.from_node.name, "Separate_RGBA")
        self.assertEqual(metallic_link.from_socket.name, "Blue")

        # Emission Color from Lit Texture
        emiss_link = bsdf.inputs["Emission Color"].links[0]
        self.assertEqual(emiss_link.from_node.name, "Emissive_Texture")
        self.assertEqual(emiss_link.from_socket.name, "Color")
        self.assertEqual(bsdf.inputs["Emission Strength"].default_value, 1.0)

        # Normal from Normal Map
        normal_link = bsdf.inputs["Normal"].links[0]
        self.assertEqual(normal_link.from_node.name, "Normal_Map")

        # Normal Map from Combine XYZ
        nmap = nodes["Normal_Map"]
        nmap_color_link = nmap.inputs["Color"].links[0]
        self.assertEqual(nmap_color_link.from_node.name, "Combine_XYZ")

        # Combine XYZ from Red, Green, and Sqrt(Z)
        comb = nodes["Combine_XYZ"]
        self.assertEqual(comb.inputs["X"].links[0].from_node.name, "Separate_RGBA")
        self.assertEqual(comb.inputs["X"].links[0].from_socket.name, "Red")
        self.assertEqual(comb.inputs["Y"].links[0].from_node.name, "Separate_RGBA")
        self.assertEqual(comb.inputs["Y"].links[0].from_socket.name, "Green")
        self.assertEqual(comb.inputs["Z"].links[0].from_node.name, "Normal_Sqrt_Z")

    def test_colorspace_configuration(self):
        """Verify color spaces are strictly 'sRGB' for albedo/lit and 'Non-Color' for normal."""
        albedo_path = os.path.join(self.temp_dir, "colorspace_albedo.png")
        create_synthetic_albedo_texture(albedo_path, 16, 16)

        normal_path = os.path.join(self.temp_dir, "colorspace_norm.png")
        create_synthetic_normal_metalness_texture(normal_path, 16, 16)

        mat = create_xplane_pbr_material(
            mat_name="ColorspaceMat",
            texture_path=albedo_path,
            normal_texture_path=normal_path,
        )

        nodes = mat.node_tree.nodes
        albedo_img = nodes["Albedo_Texture"].image
        normal_img = nodes["Normal_Texture"].image

        self.assertIsNotNone(albedo_img)
        self.assertIsNotNone(normal_img)
        self.assertEqual(albedo_img.colorspace_settings.name, 'sRGB')
        self.assertEqual(normal_img.colorspace_settings.name, 'Non-Color')

    def test_direct_normal_mode(self):
        """Verify use_procedural_normal_z=False links normal texture directly to Normal Map."""
        normal_path = os.path.join(self.temp_dir, "direct_norm.png")
        create_synthetic_normal_metalness_texture(normal_path, 16, 16)

        mat = create_xplane_pbr_material(
            mat_name="DirectNormMat",
            normal_texture_path=normal_path,
            use_procedural_normal_z=False
        )

        nodes = mat.node_tree.nodes
        self.assertNotIn("Combine_XYZ", nodes)
        self.assertNotIn("Normal_Sqrt_Z", nodes)

        nmap = nodes["Normal_Map"]
        self.assertEqual(nmap.inputs["Color"].links[0].from_node.name, "Normal_Texture")

    def test_material_integration_with_import_obj8(self):
        """Verify build_mesh attaches PBR material when TEXTURE directives exist."""
        obj_path = os.path.join(self.temp_dir, "textured_cube.obj")
        create_minimal_obj8(obj_path)

        norm_path = os.path.join(self.temp_dir, "synthetic_norm.png")
        create_synthetic_normal_metalness_texture(norm_path, 32, 32)

        # Append normal texture directive to synthetic model
        with open(obj_path, "a", encoding="utf-8") as f:
            f.write(f"\nTEXTURE_NORMAL {os.path.basename(norm_path)}\n")

        parsed = parse_obj8(obj_path)
        mesh_obj = build_mesh(parsed, name="TexturedMesh")

        self.assertEqual(len(mesh_obj.data.materials), 1)
        mat = mesh_obj.data.materials[0]
        self.assertIn("Principled_BSDF", mat.node_tree.nodes)
        self.assertIn("Normal_Texture", mat.node_tree.nodes)


if __name__ == '__main__':
    unittest.main()
