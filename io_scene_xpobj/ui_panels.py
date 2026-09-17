"""
ui_panels.py - 3D Viewport Sidebar UI Panel & Interactive Operators for Blender 4.3+.

Implements 3D Viewport sidebar integration (N-panel, category 'X-Plane 12'):
- Import Section: Quick access to OBJ8 and ACF project importers.
- Texture Tools Section: 1-click repacking of X-Plane 12 normal/metalness maps to Unreal Engine DirectX Normal & ORM.
- Unreal Engine Pipeline Section: 1-click SkeletalMesh FBX + DataRef telemetry (JSON/CSV) export.
- X-Plane 12 Export Section: Round-trip OBJ8 export with animation hierarchy.
"""

import os
from typing import Optional, Any

try:
    import bpy
    from bpy_extras.io_utils import ImportHelper
    from bpy.props import StringProperty, BoolProperty
except ImportError:
    bpy = None
    ImportHelper = object

from .texture_repacker import repack_textures


# ==============================================================================
# Texture Repacker Operator
# ==============================================================================

if bpy is not None:
    class XPLANE_OT_repack_textures(bpy.types.Operator, ImportHelper):
        """Repack X-Plane 12 normal texture into Unreal Engine DirectX Normal and ORM maps"""
        bl_idname = "xplane.repack_textures"
        bl_label = "Repack Textures for Unreal Engine"
        bl_description = "Converts X-Plane 12 NORMAL_METALNESS texture to DirectX Normal (-Y Green) and ORM (AO, Roughness, Metallic)"
        bl_options = {'REGISTER', 'UNDO'}

        filename_ext = ".png"
        filter_glob: StringProperty(
            default="*.png;*.dds;*.tga",
            options={'HIDDEN'},
        )

        output_dir: StringProperty(
            name="Output Directory",
            description="Directory to save repacked textures (leave empty to use source directory)",
            subtype='DIR_PATH',
            default="",
        )

        def invoke(self, context, event):
            # Check if active object has a normal texture image
            obj = context.active_object
            if obj and obj.type == 'MESH' and obj.data.materials:
                mat = obj.data.materials[0]
                if mat and mat.use_nodes:
                    for node in mat.node_tree.nodes:
                        if node.type == 'TEX_IMAGE' and node.image:
                            label = (node.label or "").upper()
                            if 'NORMAL' in label or 'NORM' in label:
                                if node.image.filepath:
                                    abs_fp = bpy.path.abspath(node.image.filepath)
                                    if os.path.isfile(abs_fp):
                                        self.filepath = abs_fp
                                        return self.execute(context)

            # Otherwise show file selector
            context.window_manager.fileselect_add(self)
            return {'RUNNING_MODAL'}

        def execute(self, context):
            if not self.filepath or not os.path.isfile(self.filepath):
                self.report({'ERROR'}, "No valid source normal texture selected.")
                return {'CANCELLED'}

            out_dir = self.output_dir if self.output_dir and os.path.isdir(self.output_dir) else None

            try:
                result = repack_textures(self.filepath, output_dir=out_dir)
                dx_norm = result.get('directx_normal', '')
                orm = result.get('orm', '')
                self.report(
                    {'INFO'},
                    f"Repacked successfully!\nNormal: {os.path.basename(dx_norm)}\nORM: {os.path.basename(orm)}"
                )
            except Exception as e:
                self.report({'ERROR'}, f"Texture repacking failed: {e}")
                return {'CANCELLED'}

            return {'FINISHED'}


    # ==============================================================================
    # 3D Viewport Sidebar Panel (N-Panel)
    # ==============================================================================

    class VIEW3D_PT_xplane_bridge(bpy.types.Panel):
        """Main sidebar panel for X-Plane 12 to Blender 4+ and Unreal Engine Bridge"""
        bl_space_type = 'VIEW_3D'
        bl_region_type = 'UI'
        bl_category = 'X-Plane 12'
        bl_label = "X-Plane 12 Bridge"

        def draw(self, context):
            layout = self.layout

            # ------------------------------------------------------------------
            # Section: Import
            # ------------------------------------------------------------------
            box_import = layout.box()
            box_import.label(text="Import Aircraft / Models", icon='IMPORT')
            col = box_import.column(align=True)
            col.operator("import_scene.xplane_acf", text="Import Aircraft (.acf)", icon='COMMUNITY')
            col.operator("import_scene.xplane_obj", text="Import OBJ8 (.obj)", icon='OBJECT_DATA')

            # ------------------------------------------------------------------
            # Section: Textures (Unreal Engine Repacker)
            # ------------------------------------------------------------------
            box_tex = layout.box()
            box_tex.label(text="PBR & Texture Tools", icon='TEXTURE')
            box_tex.operator("xplane.repack_textures", text="Repack Textures for UE", icon='FILE_IMAGE')

            # ------------------------------------------------------------------
            # Section: Unreal Engine Pipeline
            # ------------------------------------------------------------------
            box_ue = layout.box()
            box_ue.label(text="Unreal Engine Pipeline", icon='EXPORT')
            box_ue.operator("export_scene.xplane_unreal", text="Export to UE (FBX + DataRef)", icon='ARMATURE_DATA')

            # ------------------------------------------------------------------
            # Section: X-Plane 12 Export
            # ------------------------------------------------------------------
            box_xp = layout.box()
            box_xp.label(text="X-Plane 12 Export", icon='FILE_REFRESH')
            box_xp.operator("export_scene.xplane_obj", text="Export to OBJ8 (.obj)", icon='EXPORT')


    CLASSES = (
        XPLANE_OT_repack_textures,
        VIEW3D_PT_xplane_bridge,
    )

else:
    CLASSES = ()


def register():
    if bpy is None:
        return
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    if bpy is None:
        return
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
