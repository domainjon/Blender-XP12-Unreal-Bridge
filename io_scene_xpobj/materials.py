"""
materials.py - Principled BSDF v2 PBR Shaders for X-Plane 12 models in Blender 4.3+.

Implements Feature 12 & Feature 13 (Milestone 3):
- Principled BSDF v2 shader networks interpreting X-Plane 12 NORMAL_METALNESS format.
- Procedural shader graph reconstruction of Normal Z:
    Red=X, Green=Y -> calculate X^2 + Y^2 -> 1 - (X^2 + Y^2) -> max(0, val) -> sqrt(val) = Normal Z
    -> Combine XYZ -> Normal Map node -> Principled BSDF 'Normal'.
- PBR channel routing:
    Texture Alpha channel -> Principled BSDF 'Roughness'
    Separate RGBA Blue channel -> Principled BSDF 'Metallic'
    Albedo texture -> Principled BSDF 'Base Color' & 'Alpha'
    Lit texture -> Principled BSDF 'Emission Color' & 'Emission Strength'
- Proper color space enforcement: 'sRGB' for albedo/lit, 'Non-Color' for normal/metalness.
"""

import os
import pathlib
from typing import Optional, Any, Union

try:
    import bpy
except ImportError:
    bpy = None


def resolve_texture_path(
    texture_ref: Union[str, pathlib.Path],
    base_filepath: Optional[str] = None
) -> Optional[str]:
    """
    Resolves an X-Plane texture reference (relative or absolute) to a file on disk.
    Searches adjacent paths, objects/, textures/, and alternates (.png <-> .dds).
    """
    if not texture_ref:
        return None

    tex_str = str(texture_ref).strip()
    if not tex_str:
        return None

    # 1. Absolute path check
    if os.path.isabs(tex_str) and os.path.isfile(tex_str):
        return os.path.normpath(tex_str)

    # 2. Check relative to base_filepath
    base_dir = os.path.dirname(os.path.abspath(base_filepath)) if base_filepath else ""
    candidate_dirs = [
        base_dir,
        os.path.join(base_dir, "objects"),
        os.path.join(base_dir, "textures"),
        os.path.join(base_dir, "..", "textures"),
    ]

    root, ext = os.path.splitext(tex_str)
    alt_ext = ".dds" if ext.lower() == ".png" else ".png"
    filenames_to_check = [tex_str, root + alt_ext]

    for d in candidate_dirs:
        if not d or not os.path.isdir(d):
            continue
        for fn in filenames_to_check:
            candidate = os.path.join(d, fn)
            if os.path.isfile(candidate):
                return os.path.normpath(candidate)

    return None


def get_or_load_image(
    image_or_path: Any,
    colorspace: str = 'sRGB',
    base_filepath: Optional[str] = None
) -> Optional[Any]:
    """
    Retrieves an existing bpy.types.Image or loads it from disk with the required color space.
    """
    if bpy is None or not image_or_path:
        return None

    # Already a Blender Image instance
    if isinstance(image_or_path, bpy.types.Image):
        try:
            image_or_path.colorspace_settings.name = colorspace
        except Exception:
            pass
        return image_or_path

    # String / Path reference
    resolved = resolve_texture_path(image_or_path, base_filepath=base_filepath)
    if resolved and os.path.isfile(resolved):
        filename = os.path.basename(resolved)
        # Check if already loaded by full path or filename
        for img in bpy.data.images:
            if img.filepath == resolved or img.name == filename:
                try:
                    img.colorspace_settings.name = colorspace
                except Exception:
                    pass
                return img
        try:
            loaded_img = bpy.data.images.load(resolved, check_existing=True)
            try:
                loaded_img.colorspace_settings.name = colorspace
            except Exception:
                pass
            return loaded_img
        except Exception:
            pass

    # Fallback: check if an image datablock exists by name
    name_str = os.path.basename(str(image_or_path))
    if name_str in bpy.data.images:
        img = bpy.data.images[name_str]
        try:
            img.colorspace_settings.name = colorspace
        except Exception:
            pass
        return img

    return None


def create_xplane_pbr_material(
    mat_name: str,
    texture_path: Optional[Any] = None,
    normal_texture_path: Optional[Any] = None,
    lit_texture_path: Optional[Any] = None,
    use_procedural_normal_z: bool = True,
    base_filepath: Optional[str] = None,
) -> Any:
    """
    Builds a Blender 4.3+ Material with a Principled BSDF v2 shader node network
    interpreting X-Plane 12 NORMAL_METALNESS textures and PBR properties.

    - Sockets: 'Base Color', 'Roughness', 'Metallic', 'Normal', 'Emission Color'.
    - Colorspace: 'sRGB' for albedo and lit textures; 'Non-Color' for normal textures.
    - Reconstructed Normal Z shader network (when use_procedural_normal_z is True):
        Separate RGBA -> Red=X, Green=Y -> calculate X^2 + Y^2 -> 1 - (X^2 + Y^2) ->
        max(0, val) -> sqrt(val) = Normal Z -> Combine XYZ -> Normal Map node -> Principled BSDF 'Normal'.
        Route Alpha channel to Principled BSDF 'Roughness'.
        Route Blue channel to Principled BSDF 'Metallic'.

    :param mat_name: Name of the material datablock to create
    :param texture_path: Filepath or bpy.types.Image for diffuse / albedo
    :param normal_texture_path: Filepath or bpy.types.Image for X-Plane NORMAL_METALNESS
    :param lit_texture_path: Filepath or bpy.types.Image for night / lit emissive texture
    :param use_procedural_normal_z: Whether to build the procedural Normal Z math tree
    :param base_filepath: Base OBJ file path for resolving relative texture paths
    :return: The created bpy.types.Material
    """
    if bpy is None:
        raise RuntimeError("Blender 'bpy' is required to create materials.")

    name = mat_name or "XPlane_PBR_Material"
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    node_tree = mat.node_tree
    nodes = node_tree.nodes
    links = node_tree.links

    # Clear default nodes for a deterministic graph
    nodes.clear()

    # --------------------------------------------------------------------------
    # 1. Output & Principled BSDF v2
    # --------------------------------------------------------------------------
    out_node = nodes.new('ShaderNodeOutputMaterial')
    out_node.name = "Material_Output"
    out_node.location = (650, 0)

    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.name = "Principled_BSDF"
    bsdf.label = "Principled BSDF"
    bsdf.location = (250, 0)
    links.new(bsdf.outputs['BSDF'], out_node.inputs['Surface'])

    # Set neutral defaults
    if 'Roughness' in bsdf.inputs:
        bsdf.inputs['Roughness'].default_value = 0.5
    if 'Metallic' in bsdf.inputs:
        bsdf.inputs['Metallic'].default_value = 0.0

    # --------------------------------------------------------------------------
    # 2. Albedo / Diffuse Texture ('sRGB')
    # --------------------------------------------------------------------------
    if texture_path:
        albedo_img = get_or_load_image(texture_path, colorspace='sRGB', base_filepath=base_filepath)
        albedo_node = nodes.new('ShaderNodeTexImage')
        albedo_node.name = "Albedo_Texture"
        albedo_node.label = "Albedo (Base Color)"
        albedo_node.location = (-450, 200)
        if albedo_img:
            albedo_node.image = albedo_img

        if 'Base Color' in bsdf.inputs and 'Color' in albedo_node.outputs:
            links.new(albedo_node.outputs['Color'], bsdf.inputs['Base Color'])
        if 'Alpha' in bsdf.inputs and 'Alpha' in albedo_node.outputs:
            links.new(albedo_node.outputs['Alpha'], bsdf.inputs['Alpha'])

    # --------------------------------------------------------------------------
    # 3. Night / Lit Texture ('sRGB')
    # --------------------------------------------------------------------------
    if lit_texture_path:
        lit_img = get_or_load_image(lit_texture_path, colorspace='sRGB', base_filepath=base_filepath)
        lit_node = nodes.new('ShaderNodeTexImage')
        lit_node.name = "Emissive_Texture"
        lit_node.label = "Emissive (Lit)"
        lit_node.location = (-450, -100)
        if lit_img:
            lit_node.image = lit_img

        if 'Emission Color' in bsdf.inputs and 'Color' in lit_node.outputs:
            links.new(lit_node.outputs['Color'], bsdf.inputs['Emission Color'])
        if 'Emission Strength' in bsdf.inputs:
            bsdf.inputs['Emission Strength'].default_value = 1.0

    # --------------------------------------------------------------------------
    # 4. Normal / Metalness Texture ('Non-Color') & Normal Z Network
    # --------------------------------------------------------------------------
    if normal_texture_path:
        norm_img = get_or_load_image(normal_texture_path, colorspace='Non-Color', base_filepath=base_filepath)
        norm_tex_node = nodes.new('ShaderNodeTexImage')
        norm_tex_node.name = "Normal_Texture"
        norm_tex_node.label = "X-Plane Normal/Metalness"
        norm_tex_node.location = (-950, -350)
        if norm_img:
            norm_tex_node.image = norm_img

        # Separate RGBA / Color
        sep = nodes.new('ShaderNodeSeparateColor')
        sep.name = "Separate_RGBA"
        sep.label = "Separate RGBA"
        sep.location = (-700, -350)
        links.new(norm_tex_node.outputs['Color'], sep.inputs['Color'])

        # Route Alpha -> Roughness
        if 'Roughness' in bsdf.inputs and 'Alpha' in norm_tex_node.outputs:
            links.new(norm_tex_node.outputs['Alpha'], bsdf.inputs['Roughness'])

        # Route Blue -> Metallic
        if 'Metallic' in bsdf.inputs and 'Blue' in sep.outputs:
            links.new(sep.outputs['Blue'], bsdf.inputs['Metallic'])

        if use_procedural_normal_z:
            # ------------------------------------------------------------------
            # Reconstructed Normal Z math node network:
            # Red=X, Green=Y -> calculate X^2 + Y^2 -> 1 - (X^2 + Y^2) ->
            # max(0, val) -> sqrt(val) = Normal Z -> Combine XYZ -> Normal Map node -> Principled BSDF 'Normal'
            # ------------------------------------------------------------------

            # X^2
            node_x2 = nodes.new('ShaderNodeMath')
            node_x2.name = "Normal_X2"
            node_x2.label = "X^2"
            node_x2.operation = 'POWER'
            node_x2.inputs[1].default_value = 2.0
            node_x2.location = (-500, -300)
            links.new(sep.outputs['Red'], node_x2.inputs[0])

            # Y^2
            node_y2 = nodes.new('ShaderNodeMath')
            node_y2.name = "Normal_Y2"
            node_y2.label = "Y^2"
            node_y2.operation = 'POWER'
            node_y2.inputs[1].default_value = 2.0
            node_y2.location = (-500, -450)
            links.new(sep.outputs['Green'], node_y2.inputs[0])

            # X^2 + Y^2
            node_add = nodes.new('ShaderNodeMath')
            node_add.name = "Normal_X2_plus_Y2"
            node_add.label = "X^2 + Y^2"
            node_add.operation = 'ADD'
            node_add.location = (-320, -350)
            links.new(node_x2.outputs['Value'], node_add.inputs[0])
            links.new(node_y2.outputs['Value'], node_add.inputs[1])

            # 1 - (X^2 + Y^2)
            node_sub = nodes.new('ShaderNodeMath')
            node_sub.name = "Normal_1_minus_sum"
            node_sub.label = "1 - (X^2 + Y^2)"
            node_sub.operation = 'SUBTRACT'
            node_sub.inputs[0].default_value = 1.0
            node_sub.location = (-140, -350)
            links.new(node_add.outputs['Value'], node_sub.inputs[1])

            # max(0, val)
            node_max = nodes.new('ShaderNodeMath')
            node_max.name = "Normal_Max_Zero"
            node_max.label = "max(0, val)"
            node_max.operation = 'MAXIMUM'
            node_max.inputs[1].default_value = 0.0
            node_max.location = (40, -350)
            links.new(node_sub.outputs['Value'], node_max.inputs[0])

            # sqrt(val) = Normal Z
            node_sqrt = nodes.new('ShaderNodeMath')
            node_sqrt.name = "Normal_Sqrt_Z"
            node_sqrt.label = "sqrt(val) = Normal Z"
            node_sqrt.operation = 'SQRT'
            node_sqrt.location = (220, -350)
            links.new(node_max.outputs['Value'], node_sqrt.inputs[0])

            # Combine XYZ (Red=X, Green=Y, Normal Z=Z)
            node_comb = nodes.new('ShaderNodeCombineXYZ')
            node_comb.name = "Combine_XYZ"
            node_comb.label = "Combine XYZ"
            node_comb.location = (400, -350)
            links.new(sep.outputs['Red'], node_comb.inputs['X'])
            links.new(sep.outputs['Green'], node_comb.inputs['Y'])
            links.new(node_sqrt.outputs['Value'], node_comb.inputs['Z'])

            # Normal Map node
            norm_map = nodes.new('ShaderNodeNormalMap')
            norm_map.name = "Normal_Map"
            norm_map.label = "Normal Map"
            norm_map.location = (580, -350)
            links.new(node_comb.outputs['Vector'], norm_map.inputs['Color'])

            # Principled BSDF Normal
            if 'Normal' in bsdf.inputs:
                links.new(norm_map.outputs['Normal'], bsdf.inputs['Normal'])

        else:
            # Direct Normal Map without procedural Normal Z reconstruction
            norm_map = nodes.new('ShaderNodeNormalMap')
            norm_map.name = "Normal_Map"
            norm_map.label = "Normal Map"
            norm_map.location = (-350, -500)
            links.new(norm_tex_node.outputs['Color'], norm_map.inputs['Color'])
            if 'Normal' in bsdf.inputs:
                links.new(norm_map.outputs['Normal'], bsdf.inputs['Normal'])

    return mat
