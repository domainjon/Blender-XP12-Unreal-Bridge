"""
anim_rigging.py - Skeletal Mesh Rigging & Animation Hierarchy Engine for Blender 4.3+.

Fulfills Milestone 2 (Features 7, 8, 9, 10, 11 in PROJECT.md):
- Feature 7: Hierarchical OBJ8 animation directives parsing (ANIM_begin/end, ANIM_rotate, ANIM_trans, DataRefs).
- Feature 8: Unified Armature generation representing the full kinematic chain.
- Feature 9: EditBone creation, positioning, and minimum non-zero length sizing (enforcing Blender 4.3 safety).
- Feature 10: Mesh skinning via vertex groups (weight 1.0) and Armature modifier.
- Feature 11: Comprehensive DataRef metadata preservation on Bone and PoseBone custom properties.
"""

import math
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Set, Any, Optional

try:
    import bpy
    from mathutils import Vector, Matrix
except ImportError:
    bpy = None
    Vector = None
    Matrix = None

from .constants import (
    xp_to_blender_point,
    xp_to_blender_vector,
    TOKEN_ANIM_BEGIN,
    TOKEN_ANIM_END,
    TOKEN_ANIM_ROTATE,
    TOKEN_ANIM_ROTATE_BEGIN,
    TOKEN_ANIM_ROTATE_KEY,
    TOKEN_ANIM_ROTATE_END,
    TOKEN_ANIM_TRANS,
    TOKEN_ANIM_TRANS_BEGIN,
    TOKEN_ANIM_TRANS_KEY,
    TOKEN_ANIM_TRANS_END,
    TOKEN_ANIM_HIDE,
    TOKEN_ANIM_SHOW,
    TOKEN_ANIM_KEYFRAME_LOOP,
    TOKEN_TRIS,
)
from .import_obj8 import (
    ParsedOBJ8,
    TrisCommand,
    AnimBeginCommand,
    AnimEndCommand,
    AnimRotateCommand,
    AnimRotateBeginCommand,
    AnimRotateKeyCommand,
    AnimRotateEndCommand,
    AnimTransCommand,
    AnimTransBeginCommand,
    AnimTransKeyCommand,
    AnimTransEndCommand,
    AnimHideCommand,
    AnimShowCommand,
    AnimKeyframeLoopCommand,
)


# ==============================================================================
# Animation Hierarchy Data Structures
# ==============================================================================

@dataclass
class AnimNode:
    """Represents an animated component node in the kinematic hierarchy."""
    id: int = 0
    name: str = ""
    bone_name: str = ""
    parent: Optional['AnimNode'] = None
    children: List['AnimNode'] = field(default_factory=list)

    # Animation properties
    dataref: str = ""
    motion_type: str = "ROTATE"  # "ROTATE", "TRANSLATE", or "NONE"
    axis: Tuple[float, float, float] = (0.0, 1.0, 0.0)  # Blender coordinate space
    pivot: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # Blender coordinate space (bone head)
    tail: Tuple[float, float, float] = (0.0, 0.2, 0.0)  # Blender coordinate space (bone tail)
    keyframes: List[Tuple[float, float]] = field(default_factory=list)  # [(input_val, output_val), ...]
    input_min: float = 0.0
    input_max: float = 0.0
    output_min: float = 0.0
    output_max: float = 0.0
    unit: str = "deg"  # "deg" for ROTATE, "m" for TRANSLATE

    # Visibility / loop metadata
    hide_range: Optional[Tuple[float, float, str]] = None
    show_range: Optional[Tuple[float, float, str]] = None
    loop_modulus: Optional[float] = None

    # Geometry references (for vertex group assignment)
    vertex_indices: Set[int] = field(default_factory=set)
    vertex_positions: List[Tuple[float, float, float]] = field(default_factory=list)


# ==============================================================================
# Animation Directives Detection & Hierarchy Parser (Feature 7)
# ==============================================================================

def has_animation_commands(parsed_data: ParsedOBJ8) -> bool:
    """
    Determines whether a ParsedOBJ8 asset contains animated flight controls or components.
    """
    if not parsed_data or not parsed_data.commands:
        return False

    anim_tokens = {
        TOKEN_ANIM_BEGIN,
        TOKEN_ANIM_ROTATE,
        TOKEN_ANIM_ROTATE_BEGIN,
        TOKEN_ANIM_TRANS,
        TOKEN_ANIM_TRANS_BEGIN,
    }

    for cmd in parsed_data.commands:
        cmd_type = getattr(cmd, 'cmd_type', None)
        if cmd_type in anim_tokens:
            return True
        if isinstance(cmd, (AnimBeginCommand, AnimRotateCommand, AnimRotateBeginCommand, AnimTransCommand, AnimTransBeginCommand)):
            return True
        if isinstance(cmd, (tuple, list)) and len(cmd) > 0 and str(cmd[0]).startswith("ANIM_"):
            return True

    return False


def parse_animation_hierarchy(parsed_data: ParsedOBJ8) -> Tuple[AnimNode, List[AnimNode]]:
    """
    Parses hierarchical OBJ8 animation blocks from parsed_data.commands.
    Maintains an animation stack pushing and popping nested states, capturing
    kinematic parent-child relationships and mapping geometry to bones.

    :param parsed_data: ParsedOBJ8 instance with populated commands
    :return: (root_node, all_animated_nodes)
    """
    root_node = AnimNode(
        id=0,
        name="root",
        bone_name="root",
        motion_type="NONE",
        axis=(0.0, 1.0, 0.0),
        pivot=(0.0, 0.0, 0.0),
        tail=(0.0, 1.0, 0.0),
    )

    all_animated_nodes: List[AnimNode] = []
    stack: List[AnimNode] = []
    node_counter = 0

    used_bone_names: Set[str] = {"root"}

    def generate_bone_name(base_name: str) -> str:
        clean_name = base_name.strip() or "bone"
        clean_name = clean_name.replace("/", "_").replace("\\", "_").replace(" ", "_").replace(".", "_")
        candidate = clean_name
        counter = 1
        while candidate in used_bone_names:
            candidate = f"{clean_name}.{counter:03d}"
            counter += 1
        used_bone_names.add(candidate)
        return candidate

    for cmd in parsed_data.commands:
        cmd_type = getattr(cmd, 'cmd_type', None)
        if cmd_type is None and isinstance(cmd, (tuple, list)) and len(cmd) > 0:
            cmd_type = cmd[0]

        # 1. ANIM_begin
        if cmd_type == TOKEN_ANIM_BEGIN or isinstance(cmd, AnimBeginCommand):
            node_counter += 1
            parent_node = stack[-1] if stack else root_node
            new_node = AnimNode(
                id=node_counter,
                parent=parent_node
            )
            parent_node.children.append(new_node)
            all_animated_nodes.append(new_node)
            stack.append(new_node)

        # 2. ANIM_end
        elif cmd_type == TOKEN_ANIM_END or isinstance(cmd, AnimEndCommand):
            if stack:
                stack.pop()

        # 3. ANIM_rotate
        elif cmd_type == TOKEN_ANIM_ROTATE or isinstance(cmd, AnimRotateCommand):
            target_node = stack[-1] if stack else None
            if target_node is None:
                node_counter += 1
                target_node = AnimNode(id=node_counter, parent=root_node)
                root_node.children.append(target_node)
                all_animated_nodes.append(target_node)
                stack.append(target_node)
            elif target_node.motion_type in ("ROTATE", "TRANSLATE") and target_node.dataref:
                # Compound animation in same block: chain child node
                node_counter += 1
                child_node = AnimNode(id=node_counter, parent=target_node)
                target_node.children.append(child_node)
                all_animated_nodes.append(child_node)
                stack[-1] = child_node
                target_node = child_node

            target_node.motion_type = "ROTATE"
            target_node.unit = "deg"
            target_node.dataref = getattr(cmd, 'dataref', cmd[8] if len(cmd) > 8 else "")

            # Normalized rotation axis in Blender coordinate space
            if hasattr(cmd, 'axis'):
                ax, ay, az = cmd.axis
            else:
                ax, ay, az = float(cmd[1]), float(cmd[2]), float(cmd[3])

            alen = math.sqrt(ax * ax + ay * ay + az * az)
            norm_axis = (ax / alen, ay / alen, az / alen) if alen > 1e-5 else (0.0, 1.0, 0.0)
            target_node.axis = norm_axis

            angle1 = getattr(cmd, 'angle1', float(cmd[4]))
            angle2 = getattr(cmd, 'angle2', float(cmd[5]))
            val1 = getattr(cmd, 'val1', float(cmd[6]))
            val2 = getattr(cmd, 'val2', float(cmd[7]))

            target_node.keyframes = [(val1, angle1), (val2, angle2)]
            target_node.input_min = min(val1, val2)
            target_node.input_max = max(val1, val2)
            target_node.output_min = min(angle1, angle2)
            target_node.output_max = max(angle1, angle2)

        # 4. ANIM_rotate_begin / keys / end
        elif cmd_type == TOKEN_ANIM_ROTATE_BEGIN or isinstance(cmd, AnimRotateBeginCommand):
            target_node = stack[-1] if stack else None
            if target_node is None:
                node_counter += 1
                target_node = AnimNode(id=node_counter, parent=root_node)
                root_node.children.append(target_node)
                all_animated_nodes.append(target_node)
                stack.append(target_node)
            elif target_node.motion_type in ("ROTATE", "TRANSLATE") and target_node.dataref:
                node_counter += 1
                child_node = AnimNode(id=node_counter, parent=target_node)
                target_node.children.append(child_node)
                all_animated_nodes.append(child_node)
                stack[-1] = child_node
                target_node = child_node

            target_node.motion_type = "ROTATE"
            target_node.unit = "deg"
            target_node.dataref = getattr(cmd, 'dataref', cmd[4] if len(cmd) > 4 else "")

            if hasattr(cmd, 'axis'):
                ax, ay, az = cmd.axis
            else:
                ax, ay, az = float(cmd[1]), float(cmd[2]), float(cmd[3])

            alen = math.sqrt(ax * ax + ay * ay + az * az)
            norm_axis = (ax / alen, ay / alen, az / alen) if alen > 1e-5 else (0.0, 1.0, 0.0)
            target_node.axis = norm_axis

            if hasattr(cmd, 'keys') and cmd.keys:
                target_node.keyframes = [(k[0], k[1]) for k in cmd.keys]
                target_node.input_min = min(k[0] for k in cmd.keys)
                target_node.input_max = max(k[0] for k in cmd.keys)
                target_node.output_min = min(k[1] for k in cmd.keys)
                target_node.output_max = max(k[1] for k in cmd.keys)

        # 5. ANIM_trans
        elif cmd_type == TOKEN_ANIM_TRANS or isinstance(cmd, AnimTransCommand):
            target_node = stack[-1] if stack else None
            if target_node is None:
                node_counter += 1
                target_node = AnimNode(id=node_counter, parent=root_node)
                root_node.children.append(target_node)
                all_animated_nodes.append(target_node)
                stack.append(target_node)
            elif target_node.motion_type in ("ROTATE", "TRANSLATE") and target_node.dataref:
                node_counter += 1
                child_node = AnimNode(id=node_counter, parent=target_node)
                target_node.children.append(child_node)
                all_animated_nodes.append(child_node)
                stack[-1] = child_node
                target_node = child_node

            target_node.motion_type = "TRANSLATE"
            target_node.unit = "m"
            target_node.dataref = getattr(cmd, 'dataref', cmd[9] if len(cmd) > 9 else "")

            p1 = getattr(cmd, 'p1', (float(cmd[1]), float(cmd[2]), float(cmd[3])))
            p2 = getattr(cmd, 'p2', (float(cmd[4]), float(cmd[5]), float(cmd[6])))
            val1 = getattr(cmd, 'val1', float(cmd[7]))
            val2 = getattr(cmd, 'val2', float(cmd[8]))

            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            dz = p2[2] - p1[2]
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)

            if dist > 1e-5:
                norm_axis = (dx / dist, dy / dist, dz / dist)
            else:
                norm_axis = (0.0, 1.0, 0.0)

            target_node.axis = norm_axis
            target_node.pivot = p1
            target_node.keyframes = [(val1, 0.0), (val2, dist)]
            target_node.input_min = min(val1, val2)
            target_node.input_max = max(val1, val2)
            target_node.output_min = 0.0
            target_node.output_max = dist

        # 6. ANIM_trans_begin / keys / end
        elif cmd_type == TOKEN_ANIM_TRANS_BEGIN or isinstance(cmd, AnimTransBeginCommand):
            target_node = stack[-1] if stack else None
            if target_node is None:
                node_counter += 1
                target_node = AnimNode(id=node_counter, parent=root_node)
                root_node.children.append(target_node)
                all_animated_nodes.append(target_node)
                stack.append(target_node)
            elif target_node.motion_type in ("ROTATE", "TRANSLATE") and target_node.dataref:
                node_counter += 1
                child_node = AnimNode(id=node_counter, parent=target_node)
                target_node.children.append(child_node)
                all_animated_nodes.append(child_node)
                stack[-1] = child_node
                target_node = child_node

            target_node.motion_type = "TRANSLATE"
            target_node.unit = "m"
            target_node.dataref = getattr(cmd, 'dataref', cmd[1] if len(cmd) > 1 else "")

            if hasattr(cmd, 'keys') and cmd.keys:
                p0 = (cmd.keys[0][1], cmd.keys[0][2], cmd.keys[0][3])
                p_last = (cmd.keys[-1][1], cmd.keys[-1][2], cmd.keys[-1][3])
                dx = p_last[0] - p0[0]
                dy = p_last[1] - p0[1]
                dz = p_last[2] - p0[2]
                dist = math.sqrt(dx * dx + dy * dy + dz * dz)
                norm_axis = (dx / dist, dy / dist, dz / dist) if dist > 1e-5 else (0.0, 1.0, 0.0)

                target_node.axis = norm_axis
                target_node.pivot = p0
                target_node.keyframes = [
                    (k[0], math.sqrt((k[1] - p0[0]) ** 2 + (k[2] - p0[1]) ** 2 + (k[3] - p0[2]) ** 2))
                    for k in cmd.keys
                ]
                target_node.input_min = min(k[0] for k in target_node.keyframes)
                target_node.input_max = max(k[0] for k in target_node.keyframes)
                target_node.output_min = min(k[1] for k in target_node.keyframes)
                target_node.output_max = max(k[1] for k in target_node.keyframes)

        # 7. ANIM_hide / show / loop
        elif cmd_type == TOKEN_ANIM_HIDE or isinstance(cmd, AnimHideCommand):
            if stack:
                min_v = getattr(cmd, 'min_val', float(cmd[1]))
                max_v = getattr(cmd, 'max_val', float(cmd[2]))
                dref = getattr(cmd, 'dataref', str(cmd[3]))
                stack[-1].hide_range = (min_v, max_v, dref)

        elif cmd_type == TOKEN_ANIM_SHOW or isinstance(cmd, AnimShowCommand):
            if stack:
                min_v = getattr(cmd, 'min_val', float(cmd[1]))
                max_v = getattr(cmd, 'max_val', float(cmd[2]))
                dref = getattr(cmd, 'dataref', str(cmd[3]))
                stack[-1].show_range = (min_v, max_v, dref)

        elif cmd_type == TOKEN_ANIM_KEYFRAME_LOOP or isinstance(cmd, AnimKeyframeLoopCommand):
            if stack:
                modulus = getattr(cmd, 'modulus', float(cmd[1]))
                stack[-1].loop_modulus = modulus

        # 8. TRIS (geometry associated with current hierarchy level)
        elif cmd_type == TOKEN_TRIS or isinstance(cmd, TrisCommand):
            target_node = stack[-1] if stack else root_node
            faces = getattr(cmd, 'faces', [])
            if not faces and hasattr(cmd, 'offset') and hasattr(cmd, 'count'):
                idx_slice = parsed_data.indices[cmd.offset : cmd.offset + cmd.count]
                for i in range(0, len(idx_slice), 3):
                    if i + 2 < len(idx_slice):
                        faces.append((idx_slice[i], idx_slice[i + 2], idx_slice[i + 1]))

            for f in faces:
                for v_idx in (f[0], f[1], f[2]):
                    target_node.vertex_indices.add(v_idx)
                    if v_idx < len(parsed_data.vertices):
                        target_node.vertex_positions.append(parsed_data.vertices[v_idx])

    # Finalize node names and pivot/head/tail positions
    for node in all_animated_nodes:
        if node.dataref:
            base_name = node.dataref.strip("/").split("/")[-1]
            base_name = base_name.replace("[", "_").replace("]", "").replace(".", "_")
        else:
            base_name = f"bone_{node.id:02d}"
        node.bone_name = generate_bone_name(base_name)
        node.name = node.bone_name

        # Calculate pivot / head
        if node.motion_type == "TRANSLATE":
            head = node.pivot
        else:
            # ROTATE
            if node.vertex_positions:
                # Compute centroid of vertices for this animated part
                cx = sum(p[0] for p in node.vertex_positions) / len(node.vertex_positions)
                cy = sum(p[1] for p in node.vertex_positions) / len(node.vertex_positions)
                cz = sum(p[2] for p in node.vertex_positions) / len(node.vertex_positions)
                head = (cx, cy, cz)
            elif node.parent and node.parent.pivot != (0.0, 0.0, 0.0):
                head = node.parent.pivot
            else:
                head = (0.0, 0.0, 0.0)
            node.pivot = head

        # Calculate tail enforcing Blender 4.3 minimum 0.2m non-zero length
        axis = node.axis
        alen = math.sqrt(axis[0] * axis[0] + axis[1] * axis[1] + axis[2] * axis[2])
        if alen < 1e-5:
            axis = (0.0, 1.0, 0.0)
            node.axis = axis

        tail = (head[0] + axis[0] * 0.2, head[1] + axis[1] * 0.2, head[2] + axis[2] * 0.2)
        dx, dy, dz = tail[0] - head[0], tail[1] - head[1], tail[2] - head[2]
        cur_len = math.sqrt(dx * dx + dy * dy + dz * dz)
        if cur_len < 0.19:
            tail = (head[0], head[1] + 0.2, head[2])
        node.tail = tail

    return root_node, all_animated_nodes


# ==============================================================================
# Unified Armature Builder & Skinning Engine (Features 8, 9, 10, 11)
# ==============================================================================

def build_armature(
    parsed_data: ParsedOBJ8,
    context: Optional[Any] = None,
    mesh_objects: Optional[Any] = None,
    armature_name: Optional[str] = None,
) -> Optional[Any]:
    """
    Constructs a unified Blender Armature representing the full hierarchical kinematic chain.
    Compliant with Blender 4.3+ Python API:
    - Creates EditBone for each animated component and root.
    - Sets child_bone.parent = parent_bone and child_bone.use_connect = False.
    - Enforces minimum 0.2m bone length to prevent Blender silent auto-deletion.
    - Stores comprehensive DataRef custom properties on Bone and PoseBone.
    - Binds mesh objects to bones with vertex groups (weight 1.0) and Armature modifiers.

    :param parsed_data: ParsedOBJ8 instance
    :param context: Blender bpy.context
    :param mesh_objects: List of bpy.types.Object meshes or single Object to skin
    :param armature_name: Custom name for the Armature object
    :return: Created bpy.types.Object Armature
    """
    if bpy is None:
        raise RuntimeError("Blender 'bpy' module is required to build Armatures.")

    if not has_animation_commands(parsed_data):
        return None

    # Parse animation hierarchy
    root_node, all_nodes = parse_animation_hierarchy(parsed_data)
    if not all_nodes:
        return None

    arm_name = armature_name or f"{parsed_data.name}_Armature"
    arm_data = bpy.data.armatures.new(name=f"{arm_name}_Data")
    arm_obj = bpy.data.objects.new(arm_name, arm_data)

    # 1. Link Armature to collection
    target_collection = None
    if context and hasattr(context, "collection") and context.collection:
        target_collection = context.collection
    elif bpy.context and hasattr(bpy.context, "scene") and bpy.context.scene:
        target_collection = bpy.context.scene.collection

    if target_collection is not None and arm_obj.name not in target_collection.objects:
        target_collection.objects.link(arm_obj)

    # 2. Enter EDIT mode to create bones (Blender 4.3 requirement)
    if bpy.context.active_object and bpy.context.active_object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode='EDIT')

    edit_bones = arm_data.edit_bones

    # 3. Create root bone
    root_eb = edit_bones.new(root_node.bone_name)
    root_eb.head = Vector(root_node.pivot)
    root_eb.tail = Vector(root_node.tail)
    root_eb.use_connect = False
    root_eb["xp_dataref"] = ""
    root_eb["xp_motion_type"] = "NONE"
    root_eb["xp_axis"] = [0.0, 1.0, 0.0]

    created_ebs: Dict[str, Any] = {root_node.bone_name: root_eb}

    # 4. Create EditBones for all animated nodes
    for node in all_nodes:
        eb = edit_bones.new(node.bone_name)
        eb.head = Vector(node.pivot)
        eb.tail = Vector(node.tail)
        eb.use_connect = False

        # Parenting hierarchy
        if node.parent and node.parent.bone_name in created_ebs:
            eb.parent = created_ebs[node.parent.bone_name]
        else:
            eb.parent = root_eb

        # Store custom properties on EditBone (Feature 11)
        eb["xp_dataref"] = str(node.dataref)
        eb["xp_motion_type"] = str(node.motion_type)
        eb["xp_axis"] = [float(node.axis[0]), float(node.axis[1]), float(node.axis[2])]
        eb["xp_keyframes"] = [[float(k[0]), float(k[1])] for k in node.keyframes]
        eb["xp_input_min"] = float(node.input_min)
        eb["xp_input_max"] = float(node.input_max)
        eb["xp_output_min"] = float(node.output_min)
        eb["xp_output_max"] = float(node.output_max)
        eb["xp_unit"] = str(node.unit)

        if node.hide_range:
            eb["xp_hide_min"] = float(node.hide_range[0])
            eb["xp_hide_max"] = float(node.hide_range[1])
            eb["xp_hide_dataref"] = str(node.hide_range[2])
        if node.show_range:
            eb["xp_show_min"] = float(node.show_range[0])
            eb["xp_show_max"] = float(node.show_range[1])
            eb["xp_show_dataref"] = str(node.show_range[2])
        if node.loop_modulus is not None:
            eb["xp_loop_modulus"] = float(node.loop_modulus)

        created_ebs[node.bone_name] = eb

    # 5. Exit EDIT mode to finalize bones
    bpy.ops.object.mode_set(mode='OBJECT')

    # 6. Propagate custom properties to PoseBones for telemetry / FBX export
    for bone in arm_data.bones:
        if bone.name in arm_obj.pose.bones:
            pb = arm_obj.pose.bones[bone.name]
            for k, v in bone.items():
                if k.startswith("xp_"):
                    pb[k] = v

    # 7. Mesh Skinning & Vertex Groups (Feature 10)
    if mesh_objects:
        if not isinstance(mesh_objects, (list, tuple, set)):
            mesh_objects = [mesh_objects]

        all_nodes_with_root = [root_node] + all_nodes
        for mesh_obj in mesh_objects:
            if not mesh_obj or mesh_obj.type != 'MESH':
                continue

            num_verts = len(mesh_obj.data.vertices)
            for node in all_nodes_with_root:
                if node.vertex_indices:
                    valid_indices = [idx for idx in node.vertex_indices if idx < num_verts]
                    if valid_indices:
                        vg = mesh_obj.vertex_groups.get(node.bone_name)
                        if vg is None:
                            vg = mesh_obj.vertex_groups.new(name=node.bone_name)
                        vg.add(valid_indices, 1.0, 'REPLACE')

            # Add Armature modifier
            arm_mod = None
            for mod in mesh_obj.modifiers:
                if mod.type == 'ARMATURE':
                    arm_mod = mod
                    break
            if arm_mod is None:
                arm_mod = mesh_obj.modifiers.new(name="Armature", type='ARMATURE')
            arm_mod.object = arm_obj

            # Parent mesh object to armature
            mesh_obj.parent = arm_obj

    return arm_obj
