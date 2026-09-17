"""
dataref_exporter.py - Unreal Engine Telemetry & FBX Export Pipeline.

Implements Features 19, 20, 21, 22 (Milestone 5):
- Feature 19: 1-click Unreal Engine export (FBX + JSON + CSV)
- Feature 20: JSON telemetry schema with DataRef-to-Bone bindings
- Feature 21: Unreal Engine UDataTable CSV formatting
- Feature 22: FBX export with UE5-optimal parameters
"""

import os
import json
import csv
import io as io_module
from typing import List, Dict, Any, Optional, Tuple

try:
    import bpy
    from bpy_extras.io_utils import ExportHelper
    from bpy.props import StringProperty, BoolProperty
except ImportError:
    bpy = None
    ExportHelper = object


# ==============================================================================
# Bone DataRef Extraction
# ==============================================================================

def _extract_bindings_from_armature(armature_obj: Any) -> List[Dict[str, Any]]:
    """
    Reads animation metadata from Armature bone custom properties and
    returns a list of binding dictionaries for telemetry export.

    :param armature_obj: bpy.types.Object of type 'ARMATURE'
    :return: List of binding dicts
    """
    bindings: List[Dict[str, Any]] = []

    if armature_obj is None or armature_obj.type != 'ARMATURE':
        return bindings

    arm_data = armature_obj.data
    for bone in arm_data.bones:
        dataref = bone.get("xp_dataref", "")
        motion_type = bone.get("xp_motion_type", "NONE")

        if not dataref or motion_type == "NONE":
            continue

        axis_raw = bone.get("xp_axis", [0.0, 1.0, 0.0])
        if isinstance(axis_raw, (list, tuple)) and len(axis_raw) >= 3:
            axis = [float(axis_raw[0]), float(axis_raw[1]), float(axis_raw[2])]
        else:
            axis = [0.0, 1.0, 0.0]

        motion_label = "ROTATION" if motion_type.upper() == "ROTATE" else "TRANSLATION"
        unit = bone.get("xp_unit", "degrees" if motion_type.upper() == "ROTATE" else "meters")
        if unit == "deg":
            unit = "degrees"
        elif unit == "m":
            unit = "meters"

        binding = {
            "bone_name": bone.name,
            "dataref": str(dataref),
            "motion_type": motion_label,
            "motion_axis": axis,
            "input_min": float(bone.get("xp_input_min", 0.0)),
            "input_max": float(bone.get("xp_input_max", 1.0)),
            "output_min": float(bone.get("xp_output_min", 0.0)),
            "output_max": float(bone.get("xp_output_max", 1.0)),
            "unit": str(unit),
            "default_value": 0.0,
        }
        bindings.append(binding)

    return bindings


def _count_bones(armature_obj: Any) -> Tuple[int, int]:
    """Returns (total_bones, total_animated_bones) for the armature."""
    if armature_obj is None or armature_obj.type != 'ARMATURE':
        return 0, 0
    total = len(armature_obj.data.bones)
    animated = sum(
        1 for b in armature_obj.data.bones
        if b.get("xp_dataref", "") and b.get("xp_motion_type", "NONE") != "NONE"
    )
    return total, animated


# ==============================================================================
# JSON Telemetry Exporter (Feature 20)
# ==============================================================================

def export_telemetry_json(
    filepath: str,
    armature_obj: Any,
    fbx_filename: Optional[str] = None,
    aircraft_name: Optional[str] = None,
) -> str:
    """
    Exports DataRef-to-Bone telemetry mapping as a JSON file.

    :param filepath: Output .json file path
    :param armature_obj: Blender Armature object with xp_ custom properties
    :param fbx_filename: Associated FBX filename for the aircraft field
    :param aircraft_name: Aircraft display name
    :return: Absolute path to the written JSON file
    """
    bindings = _extract_bindings_from_armature(armature_obj)
    total_bones, animated_bones = _count_bones(armature_obj)

    if aircraft_name is None:
        aircraft_name = armature_obj.name.replace("_Armature", "") if armature_obj else "Unknown"

    if fbx_filename is None:
        fbx_filename = f"{aircraft_name}.fbx"

    document = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "aircraft": {
            "name": aircraft_name,
            "skeletal_mesh_fbx": fbx_filename,
            "total_bones": total_bones,
            "total_animated_bones": animated_bones,
        },
        "bindings": bindings,
    }

    abs_path = os.path.abspath(filepath)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(document, f, indent=2, ensure_ascii=False)

    return abs_path


# ==============================================================================
# CSV UDataTable Exporter (Feature 21)
# ==============================================================================

def export_telemetry_csv(
    filepath: str,
    armature_obj: Any,
) -> str:
    """
    Exports DataRef-to-Bone mapping as Unreal Engine UDataTable CSV.

    Format:
    ---,BoneName,DataRef,MotionType,MotionAxis,InputMin,InputMax,OutputMin,OutputMax,Unit,DefaultValue
    Row_001,rudder,sim/.../rudder,Rotation,"(X=0.000000,Y=0.000000,Z=1.000000)",-1.000000,...

    :param filepath: Output .csv file path
    :param armature_obj: Blender Armature object
    :return: Absolute path to the written CSV file
    """
    bindings = _extract_bindings_from_armature(armature_obj)

    abs_path = os.path.abspath(filepath)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)

    with open(abs_path, 'w', encoding='utf-8', newline='\n') as f:
        writer = csv.writer(f)
        # Header row matching Unreal Engine UDataTable format
        writer.writerow([
            "---", "BoneName", "DataRef", "MotionType", "MotionAxis",
            "InputMin", "InputMax", "OutputMin", "OutputMax", "Unit", "DefaultValue"
        ])

        for idx, binding in enumerate(bindings, start=1):
            row_name = f"Row_{idx:03d}"
            axis = binding["motion_axis"]
            axis_str = f'"(X={axis[0]:.6f},Y={axis[1]:.6f},Z={axis[2]:.6f})"'
            motion_label = "Rotation" if binding["motion_type"] == "ROTATION" else "Translation"

            writer.writerow([
                row_name,
                binding["bone_name"],
                binding["dataref"],
                motion_label,
                axis_str,
                f"{binding['input_min']:.6f}",
                f"{binding['input_max']:.6f}",
                f"{binding['output_min']:.6f}",
                f"{binding['output_max']:.6f}",
                binding["unit"],
                f"{binding['default_value']:.6f}",
            ])

    return abs_path


# ==============================================================================
# FBX Exporter for Unreal Engine (Feature 22)
# ==============================================================================

def export_fbx_for_unreal(
    filepath: str,
    objects: Optional[List[Any]] = None,
    armature_obj: Optional[Any] = None,
) -> str:
    """
    Wraps Blender's FBX exporter with UE5-optimal parameters for SkeletalMesh.

    :param filepath: Output .fbx file path
    :param objects: List of mesh objects to include
    :param armature_obj: Armature object
    :return: Absolute path to the written FBX file
    """
    if bpy is None:
        raise RuntimeError("Blender 'bpy' module is required for FBX export.")

    abs_path = os.path.abspath(filepath)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)

    # Select objects for export
    bpy.ops.object.select_all(action='DESELECT')

    if objects:
        for obj in objects:
            if obj:
                obj.select_set(True)

    if armature_obj:
        armature_obj.select_set(True)
        bpy.context.view_layer.objects.active = armature_obj

    bpy.ops.export_scene.fbx(
        filepath=abs_path,
        use_selection=True,
        object_types={'MESH', 'ARMATURE'},
        axis_forward='-Z',
        axis_up='Y',
        add_leaf_bones=False,
        armature_nodetype='NULL',
        bake_space_transform=False,
        primary_bone_axis='Y',
        secondary_bone_axis='X',
        use_armature_deform_only=False,
        use_tspace=True,
        mesh_smooth_type='FACE',
        use_mesh_modifiers=True,
    )

    return abs_path


# ==============================================================================
# 1-Click Full Unreal Engine Export (Feature 19)
# ==============================================================================

def export_all_for_unreal(
    output_dir: str,
    armature_obj: Any,
    mesh_objects: Optional[List[Any]] = None,
    aircraft_name: Optional[str] = None,
) -> Dict[str, str]:
    """
    1-click export generating FBX, JSON telemetry, and CSV DataTable.

    :param output_dir: Output directory for all files
    :param armature_obj: Armature object
    :param mesh_objects: Mesh objects to export (auto-discovered from armature children if None)
    :param aircraft_name: Aircraft display name
    :return: Dict with paths to 'fbx', 'json', 'csv' files
    """
    if aircraft_name is None:
        aircraft_name = armature_obj.name.replace("_Armature", "") if armature_obj else "Aircraft"

    if mesh_objects is None and armature_obj and bpy:
        mesh_objects = [child for child in armature_obj.children if child.type == 'MESH']

    os.makedirs(output_dir, exist_ok=True)

    fbx_filename = f"{aircraft_name}.fbx"
    fbx_path = os.path.join(output_dir, fbx_filename)
    json_path = os.path.join(output_dir, f"{aircraft_name}_telemetry.json")
    csv_path = os.path.join(output_dir, f"{aircraft_name}_datatable.csv")

    result = {}

    # Export FBX
    try:
        result['fbx'] = export_fbx_for_unreal(fbx_path, mesh_objects, armature_obj)
    except Exception as e:
        result['fbx_error'] = str(e)

    # Export JSON telemetry
    result['json'] = export_telemetry_json(json_path, armature_obj, fbx_filename, aircraft_name)

    # Export CSV DataTable
    result['csv'] = export_telemetry_csv(csv_path, armature_obj)

    return result


# ==============================================================================
# Blender Operators
# ==============================================================================

if bpy is not None:
    class EXPORT_SCENE_OT_xplane_unreal(bpy.types.Operator, ExportHelper):
        """Export aircraft to Unreal Engine (FBX + DataRef JSON/CSV)"""
        bl_idname = "export_scene.xplane_unreal"
        bl_label = "Export to Unreal Engine"
        bl_description = "Export rigged aircraft as FBX with DataRef telemetry mapping"
        bl_options = {'REGISTER', 'UNDO'}

        filename_ext = ".fbx"
        filter_glob: StringProperty(
            default="*.fbx",
            options={'HIDDEN'},
        )

        export_json: BoolProperty(
            name="Export JSON Telemetry",
            description="Export DataRef-to-Bone mapping as JSON",
            default=True,
        )

        export_csv: BoolProperty(
            name="Export CSV DataTable",
            description="Export UE DataTable-compatible CSV",
            default=True,
        )

        def execute(self, context):
            arm_obj = None
            mesh_objs = []

            for obj in context.selected_objects:
                if obj.type == 'ARMATURE':
                    arm_obj = obj
                elif obj.type == 'MESH':
                    mesh_objs.append(obj)

            if arm_obj is None:
                for obj in mesh_objs:
                    if obj.parent and obj.parent.type == 'ARMATURE':
                        arm_obj = obj.parent
                        break

            if not mesh_objs and arm_obj:
                mesh_objs = [c for c in arm_obj.children if c.type == 'MESH']

            if not mesh_objs:
                self.report({'ERROR'}, "No mesh objects found for export.")
                return {'CANCELLED'}

            output_dir = os.path.dirname(self.filepath)
            aircraft_name = os.path.splitext(os.path.basename(self.filepath))[0]

            try:
                # Export FBX
                export_fbx_for_unreal(self.filepath, mesh_objs, arm_obj)
                self.report({'INFO'}, f"Exported FBX: {self.filepath}")

                # Export JSON
                if self.export_json and arm_obj:
                    json_path = os.path.join(output_dir, f"{aircraft_name}_telemetry.json")
                    export_telemetry_json(json_path, arm_obj, os.path.basename(self.filepath), aircraft_name)
                    self.report({'INFO'}, f"Exported JSON: {json_path}")

                # Export CSV
                if self.export_csv and arm_obj:
                    csv_path = os.path.join(output_dir, f"{aircraft_name}_datatable.csv")
                    export_telemetry_csv(csv_path, arm_obj)
                    self.report({'INFO'}, f"Exported CSV: {csv_path}")

            except Exception as e:
                self.report({'ERROR'}, f"Export failed: {e}")
                return {'CANCELLED'}

            return {'FINISHED'}
