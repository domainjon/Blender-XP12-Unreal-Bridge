# Project: Blender 4.3+ X-Plane 12 Aircraft Importer, Rigging, PBR & Unreal Engine Exporter

## Architecture
A modular Blender 4.3+ add-on (`io_scene_xpobj`) organized into discrete components:
- `__init__.py`: Add-on metadata (`bl_info`), registration/unregistration of all classes, menu integration (`TOPBAR_MT_file_import`, `TOPBAR_MT_file_export`).
- `constants.py`: Coordinate transform matrices, X-Plane 12 tokens, default settings.
- `import_obj8.py`: Parser for X-Plane 12 OBJ8 geometry, vertices, custom split normals, UVs, material assignments, and animation commands.
- `import_acf.py`: Parser for Plane Maker `.acf` files, detecting attached objects from `objects/`, relative coordinate frames, and component tagging.
- `anim_rigging.py`: Engine converting OBJ8 hierarchical `ANIM_begin` / `ANIM_rotate` / `ANIM_trans` blocks into a unified Blender Armature with bones, constraints, vertex groups, and DataRef custom properties.
- `materials.py`: Principled BSDF v2 shader graph builder for X-Plane 12 `NORMAL_METALNESS` textures (deriving Normal Z from X/Y, routing Metallic and Roughness).
- `texture_repacker.py`: Vectorized NumPy-based image repacker converting X-Plane normal textures to DirectX Normal (-Y green) and ORM maps (AO, Roughness, Metallic).
- `filter_lod.py`: Logic and collection management for Exterior vs Cockpit filtering and LOD level separation (LOD 0 or distinct hierarchy collections).
- `ui.py`: Import/Export file dialog operators and 3D View sidebar panel (`VIEW3D_PT_xplane_tools`) for texture repacking and batch tools.
- `export_telemetry.py`: Exporter generating telemetry JSON (Draft 2020-12) and Unreal Engine `UDataTable` CSV mapping bone names to DataRefs, axes, and limits.
- `export_fbx.py`: Exporter generating Unreal Engine-ready SkeletalMesh FBX with verified parameters (`axis_forward='-Z'`, `axis_up='Y'`, `add_leaf_bones=False`, `armature_nodetype='NULL'`).
- `export_obj8.py`: Exporter generating valid X-Plane 12 OBJ8 files preserving geometry, split normals, UVs, materials, and animation hierarchy for round-trip workflows.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Add-on Registration | Clean registration and unregistration in Blender 4.3+ without warnings or exceptions | M1 | ORIGINAL_REQUEST §R1 |
| 2 | OBJ8 Geometry Parsing | Parse OBJ8 headers, POINT_COUNTS, VT, IDX, TRIS, and command tokens | M1 | ORIGINAL_REQUEST §R1 |
| 3 | Modern Custom Normals | Set custom split vertex normals via `normals_split_custom_set_from_vertices` without deprecated APIs | M1 | ORIGINAL_REQUEST §R1 |
| 4 | Coordinate Frame Mapping | Transform X-Plane (+X Right, +Y Up, +Z Aft) to Blender (+X Right, +Y Back, +Z Up) and fix face winding | M1 | ORIGINAL_REQUEST §R1 |
| 5 | UV Map Assignment | Fast assignment of texture coordinates to mesh UV layers via `foreach_set` | M1 | ORIGINAL_REQUEST §R1 |
| 6 | ACF Project Parsing | Parse Plane Maker `.acf` files to locate attached `.obj` files in `objects/` with relative offsets | M1 | ORIGINAL_REQUEST §R1 |
| 7 | Animation Directives Parsing | Parse `ANIM_begin`, `ANIM_end`, `ANIM_rotate`, `ANIM_rotate_key`, `ANIM_trans`, `ANIM_trans_key`, and DataRefs | M2 | ORIGINAL_REQUEST §R2 |
| 8 | Unified Armature Generation | Construct a unified Blender Armature representing the full hierarchical kinematic chain | M2 | ORIGINAL_REQUEST §R2 |
| 9 | Bone Creation & Sizing | Generate `EditBone` elements with valid non-zero length and correct orientations matching rotation/translation axes | M2 | ORIGINAL_REQUEST §R2 |
| 10 | Mesh Skinning & Vertex Groups | Bind mesh objects to bones with vertex groups and Armature modifiers | M2 | ORIGINAL_REQUEST §R2 |
| 11 | DataRef Preservation | Store DataRef path, motion type, axis, and keyframe value/angle ranges as custom properties on bones | M2 | ORIGINAL_REQUEST §R2 |
| 12 | Principled BSDF v2 PBR Shaders | Build Blender 4.3 Principled BSDF v2 shader networks for X-Plane 12 `NORMAL_METALNESS` textures | M3 | ORIGINAL_REQUEST §R3 |
| 13 | Normal Z Derivation | Compute reconstructed Normal Z = `sqrt(max(0, 1 - X^2 - Y^2))` in shader graph and repacker | M3 | ORIGINAL_REQUEST §R3 |
| 14 | DirectX Normal Repacker | Convert X-Plane normal textures to DirectX Normal maps with inverted green channel (-Y) | M3 | ORIGINAL_REQUEST §R3 |
| 15 | ORM Texture Repacker | Pack Red=AO (1.0 default), Green=Roughness (from Alpha), Blue=Metallic (from Blue) using NumPy | M3 | ORIGINAL_REQUEST §R3 |
| 16 | Zero-Dependency Image Processing | Execute texture repacking using bundled NumPy and Blender C-buffers without external pip packages | M3 | ORIGINAL_REQUEST §R3 |
| 17 | Component Filtering UI | Import dialog and sidebar options to filter by component type: Exterior only, Cockpit only, or Both | M4 | ORIGINAL_REQUEST §R4 |
| 18 | LOD Filtering UI | Import options to import only highest-detail LOD 0 or organize all LOD levels into distinct collections | M4 | ORIGINAL_REQUEST §R4 |
| 19 | Sidebar Panel & Tools UI | 3D View sidebar panel with texture repacker utility, telemetry exporter triggers, and batch tools | M4 | ORIGINAL_REQUEST §R4 |
| 20 | Telemetry JSON Exporter | Export hierarchical JSON mapping bone names to DataRefs, axes, and telemetry ranges | M5 | ORIGINAL_REQUEST §R5 |
| 21 | Unreal Engine DataTable CSV Exporter | Export Unreal Engine `UDataTable` CSV matching `FXPlaneBoneTelemetryRow` struct format | M5 | ORIGINAL_REQUEST §R5 |
| 22 | Unreal SkeletalMesh FBX Exporter | 1-click export of Armature + Meshes to Unreal Engine FBX with verified settings (no leaf bones, null root) | M5 | ORIGINAL_REQUEST §R5 |
| 23 | Round-Trip X-Plane 12 OBJ8 Exporter | Export Blender meshes and Armature animations back to valid X-Plane 12 OBJ8 syntax | M5 | ORIGINAL_REQUEST §R5 |
| 24 | Synthetic Test Asset Generator | Generate synthetic ACF, OBJ8 (with animation, materials, LODs), and normal textures for automated tests | Test Track | ORIGINAL_REQUEST §R6 |
| 25 | Headless CLI Test Suite (Tiers 1-4) | Comprehensive test suite running via headless Blender 4.3 CLI verifying all features | Test Track | ORIGINAL_REQUEST §R6 |
| 26 | Adversarial Hardening (Tier 5) | White-box stress-testing, boundary tests, malformed inputs, and robustness verification | M6 | ORIGINAL_REQUEST §R6 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| Test Track | E2E Testing Track | Test harness, synthetic asset generators, and Tiers 1-4 test suites; publishes TEST_READY.md | None | IN_PROGRESS |
| M1 | Core Add-on & Geometry Importer | Add-on package structure, registration, OBJ8/ACF parser, coordinate mapping, custom split normals, UVs | None | IN_PROGRESS |
| M2 | Skeletal Mesh Rigging & Animations | Hierarchy tree, unified Armature, EditBone generation, vertex groups, DataRef bone custom properties | M1 | PLANNED |
| M3 | PBR Materials & Texture Repacker | Principled BSDF v2 shader node trees, X-Plane NORMAL_METALNESS, vectorized DirectX Normal & ORM repacker | M1 | PLANNED |
| M4 | UI, Preferences & LOD/Component Filters | File import/export operator dialogs, 3D View sidebar panel, Exterior/Cockpit filters, LOD collections | M1, M2, M3 | PLANNED |
| M5 | Unreal Telemetry & OBJ8 Exporters | SkeletalMesh FBX export, JSON/CSV telemetry data table exports, round-trip OBJ8 serializer | M1, M2 | PLANNED |
| M6 | Final Verification & Adversarial Hardening | Phase 1: Pass 100% E2E test suite (Tiers 1-4). Phase 2: Adversarial coverage hardening (Tier 5) | Test Track, M1-M5 | PLANNED |

## Interface Contracts

### M1 Core Importer ↔ M2 Rigging Engine
- `ParsedOBJ8`: Data container with:
  - `vertices`: List of `(x, y, z)`
  - `normals`: List of `(nx, ny, nz)`
  - `uvs`: List of `(u, v)`
  - `materials`: Dict of material names and texture references
  - `commands`: List of geometry draws (`TRIS`, etc.) and animation blocks (`ANIM_begin`, `ANIM_rotate`, `ANIM_trans`, `ANIM_end`)
  - `lod_ranges`: List of `(near, far)`
- `build_mesh(parsed_data, context) -> bpy.types.Object`: Creates Blender mesh object with custom split normals and UVs.
- `build_armature(parsed_data, context) -> bpy.types.Object`: Ingests animation tree from `parsed_data.commands` and constructs `bpy.types.Armature`.

### M1/M2 Importer ↔ M3 Materials & Repacker
- `create_xplane_pbr_material(mat_name, texture_path, normal_texture_path) -> bpy.types.Material`:
  Builds Principled BSDF v2 node tree interpreting X-Plane 12 `NORMAL_METALNESS`.
- `repack_textures(source_normal_path, output_dir) -> Dict[str, str]`:
  Generates `{ 'directx_normal': path, 'orm': path }` using vectorized NumPy routines.

### M2 Rigging Engine ↔ M5 Exporters
- Bone Custom Properties schema on `armature_obj.data.bones[bone_name]`:
  - `xp_dataref`: String (e.g. `'sim/flightmodel2/controls/left_aileron'`)
  - `xp_motion_type`: String (`'ROTATE'` or `'TRANSLATE'`)
  - `xp_axis`: Tuple of 3 floats `(x, y, z)`
  - `xp_keyframes`: List of `(value, angle_or_distance)` pairs
  - `xp_input_min`: Float
  - `xp_input_max`: Float
  - `xp_output_min`: Float
  - `xp_output_max`: Float
  - `xp_unit`: String (`'deg'`, `'m'`, `'ratio'`, etc.)
- `export_telemetry_json(armature_obj, filepath)`: Exports JSON schema.
- `export_telemetry_csv(armature_obj, filepath)`: Exports Unreal Engine `UDataTable` CSV.
- `export_skeletal_mesh_fbx(armature_obj, mesh_objs, filepath)`: Invokes `bpy.ops.export_scene.fbx` with verified settings.
- `export_xplane_obj8(armature_obj, mesh_objs, filepath)`: Serializes mesh geometry and armature animation hierarchy back to OBJ8 format.

## Code Layout
```
io_scene_xpobj/
├── __init__.py            # bl_info, register/unregister, menu operators
├── constants.py           # Coordinate conversions, token constants, schemas
├── import_obj8.py         # OBJ8 lexer, parser, geometry & normal builder
├── import_acf.py          # ACF aircraft parser & multi-part assembler
├── anim_rigging.py        # Animation block parser, Armature & bone builder, skinning
├── materials.py           # Principled BSDF v2 shader graphs (NORMAL_METALNESS)
├── texture_repacker.py    # Vectorized NumPy DirectX Normal & ORM repacker
├── filter_lod.py          # Cockpit/Exterior & LOD collection organizer
├── ui.py                  # Operator dialogs & 3D View sidebar tools panel
├── export_telemetry.py    # JSON & Unreal Engine DataTable CSV exporters
├── export_fbx.py          # Unreal Engine SkeletalMesh FBX exporter
└── export_obj8.py         # Round-trip X-Plane 12 OBJ8 exporter

tests/
├── run_tests.py           # Headless test runner orchestrating all test suites
├── synthetic_assets.py    # Generator for synthetic ACF, OBJ8, and textures
├── test_addon_lifecycle.py# Test registration, unregistration, menu presence
├── test_obj8_importer.py  # Test geometry, split normals, UVs, coordinates
├── test_acf_importer.py   # Test multi-part aircraft assembly & relative coords
├── test_rigging.py        # Test armature, bones, hierarchy, DataRef properties
├── test_materials.py      # Test Principled BSDF v2 shader networks
├── test_repacker.py       # Test DirectX Normal & ORM texture repacking
├── test_filtering.py      # Test Exterior/Cockpit & LOD 0 filtering
├── test_telemetry.py      # Test JSON and Unreal DataTable CSV telemetry export
├── test_fbx_export.py     # Test Unreal Engine SkeletalMesh FBX export
└── test_roundtrip_obj8.py # Test round-trip export to valid OBJ8
```
