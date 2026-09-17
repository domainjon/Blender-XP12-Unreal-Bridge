"""
export_obj8.py - X-Plane 12 OBJ8 Round-Trip Exporter for Blender 4.3+.

Implements Feature 23 (Milestone 5):
- Exports Blender mesh objects back to valid X-Plane 12 OBJ8 text format.
- Converts Blender coordinates (+X Right, +Y Forward, +Z Up) to X-Plane (+X Right, +Y Up, +Z Aft).
- Reverses face winding from CCW (Blender) back to CW (X-Plane).
- Reconstructs ANIM_begin/rotate/trans/end blocks from Armature bone custom properties.
- Writes TEXTURE, TEXTURE_LIT, TEXTURE_NORMAL, NORMAL_METALNESS directives.
"""

import os
import math
from typing import List, Dict, Any, Optional, Tuple

try:
    import bpy
    from bpy_extras.io_utils import ExportHelper
    from bpy.props import StringProperty, BoolProperty
except ImportError:
    bpy = None
    ExportHelper = object

from .constants import (
    blender_to_xp_point,
    blender_to_xp_vector,
    reverse_winding_triangle,
    PROP_DATAREF,
    PROP_MOTION_TYPE,
    PROP_AXIS,
    PROP_INPUT_MIN,
    PROP_INPUT_MAX,
    PROP_OUTPUT_MIN,
    PROP_OUTPUT_MAX,
    PROP_UNIT,
)


# ==============================================================================
# OBJ8 Writer Utilities
# ==============================================================================

def _format_float(val: float, precision: int = 6) -> str:
    """Format a float value with controlled precision, stripping trailing zeros."""
    formatted = f"{val:.{precision}f}"
    if '.' in formatted:
        formatted = formatted.rstrip('0').rstrip('.')
    return formatted


def _collect_mesh_data(
    mesh_objects: List[Any],
) -> Tuple[List[Tuple[float, ...]], List[Tuple[float, ...]], List[Tuple[float, float]], List[int], List[Tuple[int, int]]]:
    """
    Collects and merges geometry data from one or more Blender mesh objects,
    converting coordinates to X-Plane space.

    :return: (vertices_xp, normals_xp, uvs, indices, tris_commands)
        tris_commands: list of (offset, count) pairs into the index table
    """
    all_verts: List[Tuple[float, ...]] = []
    all_normals: List[Tuple[float, ...]] = []
    all_uvs: List[Tuple[float, float]] = []
    all_indices: List[int] = []
    tris_commands: List[Tuple[int, int]] = []

    vertex_offset = 0

    for obj in mesh_objects:
        if obj is None or obj.type != 'MESH':
            continue

        mesh = obj.data
        mesh.calc_loop_triangles()

        # Ensure we have custom normals
        if hasattr(mesh, 'calc_normals_split'):
            mesh.calc_normals_split()

        uv_layer = mesh.uv_layers.active

        # Build per-loop vertex data (position, normal, uv)
        loop_to_vt: Dict[int, int] = {}
        vt_count = 0

        for tri in mesh.loop_triangles:
            for loop_idx in tri.loops:
                if loop_idx in loop_to_vt:
                    continue

                loop = mesh.loops[loop_idx]
                vert = mesh.vertices[loop.vertex_index]

                # Position: Blender -> X-Plane
                bx, by, bz = vert.co.x, vert.co.y, vert.co.z
                xp_pos = blender_to_xp_point(bx, by, bz)

                # Normal: Blender -> X-Plane
                if hasattr(loop, 'normal'):
                    nx, ny, nz = loop.normal.x, loop.normal.y, loop.normal.z
                else:
                    nx, ny, nz = vert.normal.x, vert.normal.y, vert.normal.z
                xp_norm = blender_to_xp_vector(nx, ny, nz)

                # UV
                if uv_layer:
                    uv_data = uv_layer.data[loop_idx]
                    u, v = uv_data.uv[0], uv_data.uv[1]
                else:
                    u, v = 0.0, 0.0

                all_verts.append(xp_pos)
                all_normals.append(xp_norm)
                all_uvs.append((u, v))
                loop_to_vt[loop_idx] = vertex_offset + vt_count
                vt_count += 1

        # Build index table with CW winding for X-Plane
        idx_start = len(all_indices)
        for tri in mesh.loop_triangles:
            i0 = loop_to_vt[tri.loops[0]]
            i1 = loop_to_vt[tri.loops[1]]
            i2 = loop_to_vt[tri.loops[2]]
            # Reverse CCW -> CW winding
            cw = reverse_winding_triangle(i0, i1, i2)
            all_indices.extend(cw)

        idx_count = len(all_indices) - idx_start
        if idx_count > 0:
            tris_commands.append((idx_start, idx_count))

        vertex_offset += vt_count

    return all_verts, all_normals, all_uvs, all_indices, tris_commands


def _collect_material_textures(mesh_objects: List[Any]) -> Dict[str, Optional[str]]:
    """
    Extracts texture file references from the first material's node tree.

    :return: Dict with keys 'diffuse', 'lit', 'normal', 'normal_metalness'
    """
    result: Dict[str, Optional[str]] = {
        'diffuse': None,
        'lit': None,
        'normal': None,
        'normal_metalness': False,
    }

    if bpy is None:
        return result

    for obj in mesh_objects:
        if not obj or obj.type != 'MESH' or not obj.data.materials:
            continue
        mat = obj.data.materials[0]
        if not mat or not mat.use_nodes:
            continue

        for node in mat.node_tree.nodes:
            if node.type != 'TEX_IMAGE' or not node.image:
                continue
            label = (node.label or "").upper()
            filepath = node.image.filepath or node.image.name

            if 'NORMAL' in label or 'NORM' in label:
                result['normal'] = os.path.basename(filepath)
            elif 'EMISSIVE' in label or 'LIT' in label:
                result['lit'] = os.path.basename(filepath)
            elif 'DEFAULT' in label or 'ALBEDO' in label or 'DIFFUSE' in label or 'BASE' in label:
                result['diffuse'] = os.path.basename(filepath)
            elif not result['diffuse']:
                result['diffuse'] = os.path.basename(filepath)

        # Check for NORMAL_METALNESS
        bsdf = mat.node_tree.nodes.get('Principled BSDF')
        if bsdf:
            metallic_input = bsdf.inputs.get('Metallic')
            if metallic_input and metallic_input.is_linked:
                result['normal_metalness'] = True

        break

    return result


def _collect_armature_animations(armature_obj: Any) -> List[Dict[str, Any]]:
    """
    Reads animation metadata from armature bone custom properties.

    :return: List of dicts with bone animation data
    """
    animations = []
    if bpy is None or armature_obj is None or armature_obj.type != 'ARMATURE':
        return animations

    arm_data = armature_obj.data
    for bone in arm_data.bones:
        dataref = bone.get("xp_dataref", "")
        motion_type = bone.get("xp_motion_type", "NONE")

        if not dataref or motion_type == "NONE":
            continue

        axis = bone.get("xp_axis", [0.0, 1.0, 0.0])
        if isinstance(axis, (list, tuple)) and len(axis) >= 3:
            axis = (float(axis[0]), float(axis[1]), float(axis[2]))
        else:
            axis = (0.0, 1.0, 0.0)

        # Convert axis back to X-Plane space
        xp_axis = blender_to_xp_vector(axis[0], axis[1], axis[2])

        anim_data = {
            'bone_name': bone.name,
            'dataref': str(dataref),
            'motion_type': str(motion_type),
            'axis': xp_axis,
            'input_min': float(bone.get("xp_input_min", 0.0)),
            'input_max': float(bone.get("xp_input_max", 1.0)),
            'output_min': float(bone.get("xp_output_min", 0.0)),
            'output_max': float(bone.get("xp_output_max", 1.0)),
            'keyframes': bone.get("xp_keyframes", []),
        }
        animations.append(anim_data)

    return animations


# ==============================================================================
# Main Export Function
# ==============================================================================

def export_obj8(
    filepath: str,
    mesh_objects: Optional[List[Any]] = None,
    armature_obj: Optional[Any] = None,
) -> str:
    """
    Exports Blender mesh objects to a valid X-Plane 12 OBJ8 file.

    :param filepath: Output .obj file path
    :param mesh_objects: List of bpy.types.Object meshes to export
    :param armature_obj: Optional Armature object for animation data
    :return: Absolute path to the written file
    """
    if mesh_objects is None:
        mesh_objects = []

    # Auto-discover mesh objects from armature children if needed
    if not mesh_objects and armature_obj and bpy:
        mesh_objects = [child for child in armature_obj.children if child.type == 'MESH']

    if not mesh_objects and bpy:
        mesh_objects = [obj for obj in bpy.context.selected_objects if obj.type == 'MESH']

    # Collect geometry
    verts, normals, uvs, indices, tris_cmds = _collect_mesh_data(mesh_objects)
    textures = _collect_material_textures(mesh_objects)
    animations = _collect_armature_animations(armature_obj) if armature_obj else []

    lines: List[str] = []

    # 1. Header
    lines.append("I")
    lines.append("800")
    lines.append("OBJ")
    lines.append("")

    # 2. Texture directives
    if textures.get('diffuse'):
        lines.append(f"TEXTURE {textures['diffuse']}")
    if textures.get('lit'):
        lines.append(f"TEXTURE_LIT {textures['lit']}")
    if textures.get('normal'):
        lines.append(f"TEXTURE_NORMAL {textures['normal']}")
    if textures.get('normal_metalness'):
        lines.append("NORMAL_METALNESS")
    lines.append("")

    # 3. POINT_COUNTS
    num_vt = len(verts)
    num_idx = len(indices)
    lines.append(f"POINT_COUNTS {num_vt} 0 0 {num_idx}")
    lines.append("")

    # 4. VT lines
    for i in range(num_vt):
        vx, vy, vz = verts[i]
        nx, ny, nz = normals[i]
        u, v = uvs[i]
        lines.append(
            f"VT {_format_float(vx)} {_format_float(vy)} {_format_float(vz)} "
            f"{_format_float(nx)} {_format_float(ny)} {_format_float(nz)} "
            f"{_format_float(u)} {_format_float(v)}"
        )
    lines.append("")

    # 5. IDX lines (groups of 10)
    idx_pos = 0
    while idx_pos < len(indices):
        chunk = indices[idx_pos:idx_pos + 10]
        if len(chunk) == 10:
            lines.append("IDX10 " + " ".join(str(x) for x in chunk))
        else:
            for x in chunk:
                lines.append(f"IDX {x}")
        idx_pos += len(chunk)
    lines.append("")

    # 6. Animation blocks (if armature provided)
    for anim in animations:
        lines.append("ANIM_begin")
        motion = anim['motion_type'].upper()
        ax, ay, az = anim['axis']
        dref = anim['dataref']

        if motion == "ROTATE":
            angle1 = anim['output_min']
            angle2 = anim['output_max']
            val1 = anim['input_min']
            val2 = anim['input_max']
            lines.append(
                f"ANIM_rotate {_format_float(ax)} {_format_float(ay)} {_format_float(az)} "
                f"{_format_float(angle1)} {_format_float(angle2)} "
                f"{_format_float(val1)} {_format_float(val2)} {dref}"
            )
        elif motion == "TRANSLATE":
            val1 = anim['input_min']
            val2 = anim['input_max']
            # For translation, output values are position offsets
            out_min = anim['output_min']
            out_max = anim['output_max']
            lines.append(
                f"ANIM_trans {_format_float(0)} {_format_float(0)} {_format_float(0)} "
                f"{_format_float(out_max)} {_format_float(0)} {_format_float(0)} "
                f"{_format_float(val1)} {_format_float(val2)} {dref}"
            )

    # 7. TRIS commands
    for offset, count in tris_cmds:
        lines.append(f"TRIS {offset} {count}")

    # Close animation blocks
    for _ in animations:
        lines.append("ANIM_end")

    lines.append("")

    # Write file
    abs_path = os.path.abspath(filepath)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines))

    return abs_path


def export_obj8_from_parsed(filepath: str, parsed_data: Any) -> str:
    """
    Exports directly from a ParsedOBJ8 dataclass to OBJ8 file format.
    Uses raw (X-Plane space) data stored in parsed_data.

    :param filepath: Output file path
    :param parsed_data: ParsedOBJ8 instance
    :return: Absolute path to the written file
    """
    lines: List[str] = []

    # Header
    lines.append("I")
    lines.append("800")
    lines.append("OBJ")
    lines.append("")

    # Material directives
    mat = parsed_data.materials.get('default', {})
    if mat.get('diffuse'):
        lines.append(f"TEXTURE {mat['diffuse']}")
    if mat.get('lit'):
        lines.append(f"TEXTURE_LIT {mat['lit']}")
    if mat.get('normal'):
        lines.append(f"TEXTURE_NORMAL {mat['normal']}")
    if mat.get('normal_metalness'):
        lines.append("NORMAL_METALNESS")
    lines.append("")

    # POINT_COUNTS
    num_vt = len(parsed_data.raw_vertices)
    num_idx = len(parsed_data.indices)
    lines.append(f"POINT_COUNTS {num_vt} 0 0 {num_idx}")
    lines.append("")

    # VT lines (using raw X-Plane coordinates)
    for i in range(num_vt):
        vx, vy, vz = parsed_data.raw_vertices[i]
        nx, ny, nz = parsed_data.raw_normals[i]
        u, v = parsed_data.uvs[i]
        lines.append(
            f"VT {_format_float(vx)} {_format_float(vy)} {_format_float(vz)} "
            f"{_format_float(nx)} {_format_float(ny)} {_format_float(nz)} "
            f"{_format_float(u)} {_format_float(v)}"
        )
    lines.append("")

    # IDX lines
    idx_pos = 0
    while idx_pos < num_idx:
        chunk = parsed_data.indices[idx_pos:idx_pos + 10]
        if len(chunk) == 10:
            lines.append("IDX10 " + " ".join(str(x) for x in chunk))
        else:
            for x in chunk:
                lines.append(f"IDX {x}")
        idx_pos += len(chunk)
    lines.append("")

    # TRIS commands
    for cmd in parsed_data.commands:
        cmd_type = getattr(cmd, 'cmd_type', None)
        if cmd_type == 'TRIS':
            lines.append(f"TRIS {cmd.offset} {cmd.count}")

    lines.append("")

    abs_path = os.path.abspath(filepath)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines))

    return abs_path


# ==============================================================================
# Blender Operator
# ==============================================================================

if bpy is not None:
    class EXPORT_SCENE_OT_xplane_obj(bpy.types.Operator, ExportHelper):
        """Export scene to X-Plane 12 OBJ8 format (.obj)"""
        bl_idname = "export_scene.xplane_obj"
        bl_label = "Export X-Plane OBJ (.obj)"
        bl_description = "Export selected meshes to X-Plane 12 OBJ8 format"
        bl_options = {'REGISTER', 'UNDO'}

        filename_ext = ".obj"
        filter_glob: StringProperty(
            default="*.obj",
            options={'HIDDEN'},
        )

        include_animations: BoolProperty(
            name="Include Animations",
            description="Export animation data from Armature bones",
            default=True,
        )

        def execute(self, context):
            mesh_objs = [o for o in context.selected_objects if o.type == 'MESH']
            arm_obj = None

            if self.include_animations:
                for obj in context.selected_objects:
                    if obj.type == 'ARMATURE':
                        arm_obj = obj
                        break
                if arm_obj is None:
                    for obj in mesh_objs:
                        if obj.parent and obj.parent.type == 'ARMATURE':
                            arm_obj = obj.parent
                            break

            if not mesh_objs:
                self.report({'ERROR'}, "No mesh objects selected for export.")
                return {'CANCELLED'}

            try:
                result_path = export_obj8(self.filepath, mesh_objs, arm_obj)
                self.report({'INFO'}, f"Exported X-Plane OBJ8 to: {result_path}")
            except Exception as e:
                self.report({'ERROR'}, f"Export failed: {e}")
                return {'CANCELLED'}

            return {'FINISHED'}
