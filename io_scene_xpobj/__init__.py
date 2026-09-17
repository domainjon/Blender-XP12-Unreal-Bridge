"""
io_scene_xpobj - X-Plane 12 Aircraft & OBJ8 Importer / Exporter for Blender 4.3+.

Features:
- Imports X-Plane 12 OBJ8 models with custom split normals, UVs, and coordinate transformation.
- Imports full Plane Maker .acf aircraft projects assembling all attached objects from objects/.
- Prepares animation hierarchies for Armature SkeletalMesh rigging.
- Principled BSDF v2 PBR material setup.
- Unreal Engine telemetry and texture repacking pipelines.
"""

bl_info = {
    "name": "X-Plane 12 Aircraft & OBJ Importer / Exporter",
    "author": "Community / FSWindowSeat",
    "version": (2, 0, 0),
    "blender": (4, 3, 0),
    "location": "File > Import > X-Plane (.obj / .acf)",
    "description": "Imports and exports X-Plane 12 .acf and .obj models with rigging, PBR materials, and Unreal Engine telemetry",
    "category": "Import-Export",
    "doc_url": "",
    "tracker_url": "",
}

import os
from typing import Optional, Any

try:
    import bpy
    from bpy_extras.io_utils import ImportHelper
    from bpy.props import (
        StringProperty,
        BoolProperty,
        IntProperty,
        EnumProperty,
        CollectionProperty,
    )
except ImportError:
    bpy = None
    ImportHelper = object

from . import constants
from .constants import (
    ADDON_VERSION,
    BLENDER_MIN_VERSION,
    xp_to_blender_point,
    xp_to_blender_vector,
    blender_to_xp_point,
    blender_to_xp_vector,
    reverse_winding_triangle,
)
from .import_obj8 import (
    ParsedOBJ8,
    TrisCommand,
    parse_obj8,
    build_mesh,
    import_obj8_file,
    load_texture,
    create_material_for_obj8,
)
from .import_acf import (
    ParsedACF,
    ACFAttachedObject,
    parse_acf,
    import_acf_project,
)
from .export_obj8 import (
    export_obj8,
    export_obj8_from_parsed,
    EXPORT_SCENE_OT_xplane_obj,
)
from .dataref_exporter import (
    export_telemetry_json,
    export_telemetry_csv,
    export_fbx_for_unreal,
    export_all_for_unreal,
    EXPORT_SCENE_OT_xplane_unreal,
)
from .texture_repacker import (
    repack_textures,
    repack_xplane_normal_texture,
)
from .ui_panels import (
    XPLANE_OT_repack_textures,
    VIEW3D_PT_xplane_bridge,
)


# ==============================================================================
# Operators
# ==============================================================================

if bpy is not None:
    class IMPORT_SCENE_OT_xplane_obj(bpy.types.Operator, ImportHelper):
        """Import an X-Plane 12 OBJ8 model (.obj) into Blender"""
        bl_idname = "import_scene.xplane_obj"
        bl_label = "Import X-Plane OBJ (.obj)"
        bl_description = "Import an X-Plane 12 OBJ8 3D model (.obj) with custom normals and UVs"
        bl_options = {'REGISTER', 'UNDO'}

        filename_ext = ".obj"
        filter_glob: StringProperty(
            default="*.obj",
            options={'HIDDEN'},
        )

        directory: StringProperty(
            subtype='DIR_PATH',
            options={'HIDDEN', 'SKIP_SAVE'},
        )

        files: CollectionProperty(
            type=bpy.types.OperatorFileListElement,
            options={'HIDDEN', 'SKIP_SAVE'},
        )

        lod_level: IntProperty(
            name="LOD Level",
            description="Specific LOD level to import (0 is highest detail)",
            default=0,
            min=0,
        )

        import_all_lods: BoolProperty(
            name="Import All LODs",
            description="Import geometry from all LOD levels simultaneously",
            default=False,
        )

        def execute(self, context):
            target_lod = None if self.import_all_lods else self.lod_level

            try:
                # Multi-file or single-file handling
                if self.files and len(self.files) > 0 and self.directory:
                    for file_elem in self.files:
                        target_path = os.path.join(self.directory, file_elem.name)
                        if os.path.isfile(target_path):
                            import_obj8_file(target_path, context=context, lod_level=target_lod)
                elif self.filepath and os.path.isfile(self.filepath):
                    import_obj8_file(self.filepath, context=context, lod_level=target_lod)
                else:
                    self.report({'ERROR'}, "No valid .obj file selected.")
                    return {'CANCELLED'}
            except Exception as e:
                self.report({'ERROR'}, f"Failed to import X-Plane OBJ8: {e}")
                return {'CANCELLED'}

            self.report({'INFO'}, "Successfully imported X-Plane OBJ8 model(s).")
            return {'FINISHED'}


    # Legacy operator alias for backward compatibility with older scripts
    class IMPORT_OT_xplane_obj_legacy(bpy.types.Operator, ImportHelper):
        """Legacy alias: import.xplane_obj"""
        bl_idname = "import.xplane_obj"
        bl_label = "Import X-Plane OBJ (.obj)"
        bl_options = {'REGISTER', 'UNDO'}

        filename_ext = ".obj"
        filter_glob: StringProperty(
            default="*.obj",
            options={'HIDDEN'},
        )

        directory: StringProperty(
            subtype='DIR_PATH',
            options={'HIDDEN', 'SKIP_SAVE'},
        )

        files: CollectionProperty(
            type=bpy.types.OperatorFileListElement,
            options={'HIDDEN', 'SKIP_SAVE'},
        )

        def execute(self, context):
            try:
                if self.files and len(self.files) > 0 and self.directory:
                    for file_elem in self.files:
                        target_path = os.path.join(self.directory, file_elem.name)
                        if os.path.isfile(target_path):
                            import_obj8_file(target_path, context=context, lod_level=0)
                elif self.filepath and os.path.isfile(self.filepath):
                    import_obj8_file(self.filepath, context=context, lod_level=0)
                else:
                    self.report({'ERROR'}, "No valid .obj file selected.")
                    return {'CANCELLED'}
            except Exception as e:
                self.report({'ERROR'}, f"Failed to import X-Plane OBJ8: {e}")
                return {'CANCELLED'}
            return {'FINISHED'}


    class IMPORT_SCENE_OT_xplane_acf(bpy.types.Operator, ImportHelper):
        """Import a Plane Maker aircraft project (.acf) into Blender"""
        bl_idname = "import_scene.xplane_acf"
        bl_label = "Import X-Plane Aircraft (.acf)"
        bl_description = "Import an X-Plane 12 aircraft project (.acf) and assemble all attached objects"
        bl_options = {'REGISTER', 'UNDO'}

        filename_ext = ".acf"
        filter_glob: StringProperty(
            default="*.acf",
            options={'HIDDEN'},
        )

        component_filter: EnumProperty(
            name="Components",
            description="Filter components to import",
            items=[
                ('BOTH', "Both (Exterior & Cockpit)", "Import all components into organized collections"),
                ('EXTERIOR', "Exterior Only", "Import exterior airframe and flight surfaces only"),
                ('COCKPIT', "Cockpit Only", "Import cockpit and cabin interior objects only"),
            ],
            default='BOTH',
        )

        lod_level: IntProperty(
            name="LOD Level",
            description="LOD level to import for attached models (0 is highest detail)",
            default=0,
            min=0,
        )

        def execute(self, context):
            if not self.filepath or not os.path.isfile(self.filepath):
                self.report({'ERROR'}, "Invalid .acf file path.")
                return {'CANCELLED'}

            try:
                res = import_acf_project(
                    acf_filepath=self.filepath,
                    context=context,
                    component_filter=self.component_filter,
                    lod_level=self.lod_level,
                )
            except Exception as e:
                self.report({'ERROR'}, f"Failed to import ACF project: {e}")
                return {'CANCELLED'}

            num_imported = len(res.get('imported_objects', []))
            self.report({'INFO'}, f"Successfully assembled aircraft: {num_imported} parts imported.")
            return {'FINISHED'}


    # Legacy operator alias for ACF
    class IMPORT_OT_xplane_acf_legacy(bpy.types.Operator, ImportHelper):
        """Legacy alias: import.xplane_acf"""
        bl_idname = "import.xplane_acf"
        bl_label = "Import X-Plane Aircraft (.acf)"
        bl_options = {'REGISTER', 'UNDO'}

        filename_ext = ".acf"
        filter_glob: StringProperty(
            default="*.acf",
            options={'HIDDEN'},
        )

        def execute(self, context):
            if not self.filepath or not os.path.isfile(self.filepath):
                self.report({'ERROR'}, "Invalid .acf file path.")
                return {'CANCELLED'}
            try:
                import_acf_project(self.filepath, context=context)
            except Exception as e:
                self.report({'ERROR'}, f"Failed to import ACF project: {e}")
                return {'CANCELLED'}
            return {'FINISHED'}


# ==============================================================================
# Menu Integration
# ==============================================================================

def menu_func_import(self, context):
    self.layout.operator(IMPORT_SCENE_OT_xplane_obj.bl_idname, text="X-Plane Object (.obj)")
    self.layout.operator(IMPORT_SCENE_OT_xplane_acf.bl_idname, text="X-Plane Aircraft (.acf)")


def menu_func_export(self, context):
    self.layout.operator(EXPORT_SCENE_OT_xplane_obj.bl_idname, text="X-Plane Object (.obj)")
    self.layout.operator(EXPORT_SCENE_OT_xplane_unreal.bl_idname, text="Unreal Engine Aircraft (FBX + DataRef)")


CLASSES = (
    IMPORT_SCENE_OT_xplane_obj,
    IMPORT_OT_xplane_obj_legacy,
    IMPORT_SCENE_OT_xplane_acf,
    IMPORT_OT_xplane_acf_legacy,
    EXPORT_SCENE_OT_xplane_obj,
    EXPORT_SCENE_OT_xplane_unreal,
    XPLANE_OT_repack_textures,
    VIEW3D_PT_xplane_bridge,
) if bpy is not None else ()


# ==============================================================================
# Registration
# ==============================================================================

def register():
    if bpy is None:
        return
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    if bpy is None:
        return
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
