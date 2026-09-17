# ---------------------------------------------------------------------------
#
# X-Plane 12 Aircraft & OBJ8 Importer / Exporter for Blender 4.3+.
#
# Complete pipeline:
# - Full Aircraft project (.acf) & OBJ8 (.obj) import
# - Skeletal Mesh Armature rigging with DataRef preservation
# - Principled BSDF v2 PBR shader networks
# - Zero-dependency texture repacking (DirectX Normal + ORM) for Unreal Engine
# - Telemetry export (FBX + JSON/CSV Data Table) for live pilot sync
# - Round-trip OBJ8 export with animation hierarchy
#
# Based on BlenderImportXPObj (FSWindowSeat) and modernized for Blender 4.3+
#
# MIT License
# ---------------------------------------------------------------------------

bl_info = {
    "name": "X-Plane 12 Aircraft & OBJ Importer / Exporter",
    "author": "FSWindowSeat / Modernized by Antigravity",
    "version": (2, 0, 0),
    "blender": (4, 3, 0),
    "location": "File > Import/Export > X-Plane, 3D View > Sidebar > X-Plane 12",
    "description": "Imports and exports X-Plane 12 .acf and .obj models with rigging, PBR materials, and Unreal Engine telemetry",
    "warning": "",
    "doc_url": "https://github.com/FSWindowSeat/BlenderImportXPObj",
    "tracker_url": "",
    "support": "COMMUNITY",
    "category": "Import-Export",
}

from .io_scene_xpobj import register, unregister

if __name__ == "__main__":
    register()