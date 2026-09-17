# Original User Request

## Initial Request — 2026-09-17T04:45:07Z

Build a production-quality Blender 4+ add-on that completely imports X-Plane 12 aircraft (.acf and .obj) with full hierarchy, Armature (SkeletalMesh) rigging, and Principled BSDF v2 PBR materials, generates Unreal Engine telemetry mapping (JSON/CSV) and texture repacks (DirectX Normal + ORM), and enables round-trip export back to X-Plane 12.

Working directory: c:\Developer Files\Projects\blender\Blender Import XPObj new
Integrity mode: development

## Requirements

### R1. Aircraft Project & OBJ8 Importer for Blender 4+
Import full X-Plane 12 aircraft projects by parsing .acf definition files to automatically assemble all attached .obj parts from the objects/ directory in relative coordinates, as well as importing standalone .obj files. Must be fully compatible with Blender 4.3+ API (fixing read-only MeshVertex.normal by utilizing modern normals APIs like normals_split_custom_set_from_vertices).

### R2. Skeletal Mesh Rigging & Animation Hierarchy
Parse X-Plane OBJ8 animation blocks (ANIM_rotate, ANIM_rotate_key, ANIM_trans, ANIM_trans_key, ANIM_begin, ANIM_end, and attached DataRefs) to build a unified Blender Armature where moving parts (ailerons, flaps, elevators, rudder, landing gear, steerable wheels, propellers, thrust reversers) are rigged as bones with DataRef metadata preserved on the bones.

### R3. PBR Materials & Unreal Engine Texture Repacker
Set up Blender 4+ Principled BSDF v2 shader networks correctly interpreting X-Plane 12 NORMAL_METALNESS format (Tangent Normal X/Y, Metalness from Blue channel, Roughness from Alpha channel, and Normal Z calculated as sqrt(max(0, 1 - X^2 - Y^2))). Include an automated texture repacker tool that converts X-Plane normal textures into standard Unreal Engine-ready DirectX Tangent Normal (-Y green) and ORM (Ambient Occlusion, Roughness, Metallic) maps.

### R4. Component & LOD Filtering
Provide intuitive UI filter options in the import dialog and sidebar to filter by component type (Exterior only, Cockpit only, or Both) and LOD level (importing only highest-detail LOD 0 or organizing all LOD levels into distinct hierarchy groups).

### R5. Unreal Engine Telemetry Exporter & X-Plane 12 OBJ8 Exporter
Provide a 1-click exporter generating Unreal Engine-compatible FBX (SkeletalMesh) alongside a DataRef-to-Bone mapping file (.json and Unreal Engine Data Table .csv) containing bone names, datarefs, motion axes, and value ranges for live pilot telemetry synchronization. Also provide a direct exporter generating valid X-Plane 12 OBJ8 syntax to allow round-trip edits.

### R6. Automated Verification Suite
Create an automated test suite with synthetic X-Plane 12 ACF and OBJ8 models (with animations, textures, and geometry) and run programmatic tests via Blender 4.3 CLI (`C:\Program Files\Blender Foundation\Blender 4.3\blender.exe --background --python ...`) to verify addon registration, geometry import, armature creation, texture repacking, and file exports.

## Acceptance Criteria

### Blender 4.3 Compatibility & Import
- [ ] Add-on successfully registers and unregisters in Blender 4.3+ without any Python exceptions or deprecated API warnings.
- [ ] Imports sample X-Plane 12 OBJ8 and .acf files with correct geometry, UV mapping, and vertex normals.
- [ ] Generates an Armature with correctly positioned and oriented bones mapped to X-Plane animation directives.

### Materials & Unreal Pipeline
- [ ] Principled BSDF v2 nodes accurately render PBR properties without manual shader editing.
- [ ] Texture repacker tool produces valid DirectX Normal and ORM textures ready for Unreal Engine.
- [ ] Telemetry exporter outputs valid FBX, JSON, and CSV files matching the DataRef specifications.

### Round-Trip Export & Tests
- [ ] Exported OBJ8 files conform to the official X-Plane OBJ8 format specification and preserve animation hierarchy.
- [ ] All automated tests pass successfully in headless Blender 4.3 CLI mode.
