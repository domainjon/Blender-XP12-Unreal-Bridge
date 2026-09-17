# Test Infrastructure Architecture & Specification

## 1. Executive Summary

This document establishes the test infrastructure architecture, synthetic asset generator, test runner, execution methodologies, and verification matrix for the **Blender 4.3+ X-Plane 12 Aircraft Importer, Rigging, PBR & Unreal Engine Exporter** (`io_scene_xpobj`).

The test suite operates entirely in headless Blender 4.3 CLI (`--background --factory-startup`) using bundled Python 3.11 and NumPy 1.24, requiring **zero external dependencies** (no PIL/Pillow or third-party test runners).

---

## 2. Test Architecture & File Layout

```
tests/
├── run_tests.py               # Master CLI test runner and result aggregator
├── synthetic_assets.py        # Autonomous synthetic X-Plane 12 test asset generator
├── test_synthetic_assets.py   # Unit tests verifying the synthetic asset generator (F24)
├── test_tier1_features.py     # Tier 1: Isolated unit tests for Features 1 - 23
├── test_tier2_boundary.py     # Tier 2: Boundary, corner case, and stress tests
├── test_tier3_combinations.py # Tier 3: Cross-feature integration tests
├── test_tier4_scenarios.py    # Tier 4: Real-world E2E production scenarios
├── test_addon_lifecycle.py    # Modular Suite: Addon registration & unregistration (F1)
├── test_obj8_importer.py      # Modular Suite: OBJ8 geometry, normals, UVs (F2, F3, F4, F5)
├── test_acf_importer.py       # Modular Suite: ACF parsing & attached objects (F6)
├── test_rigging.py            # Modular Suite: Armature, bone hierarchy, DataRefs (F7-F11)
├── test_materials.py          # Modular Suite: Principled BSDF v2 shader networks (F12, F13)
├── test_repacker.py           # Modular Suite: DirectX Normal & ORM repacker (F14, F15, F16)
├── test_filtering.py          # Modular Suite: Exterior/Cockpit & LOD filters (F17, F18, F19)
├── test_telemetry.py          # Modular Suite: JSON & Unreal DataTable CSV export (F20, F21)
├── test_fbx_export.py         # Modular Suite: Unreal SkeletalMesh FBX export (F22)
└── test_roundtrip_obj8.py     # Modular Suite: Round-trip OBJ8 serializer parity (F23)
```

---

## 3. Synthetic Asset Generation (`tests/synthetic_assets.py`)

To guarantee reproducible, self-contained automated tests without storing large binary models in source control, `tests/synthetic_assets.py` provides on-the-fly generation of minimal, 100% specification-compliant fixtures:

### 3.1 Pure Python PNG Generator
- Standard 32-bit RGBA PNG image generator written entirely in Python standard library (`zlib`, `struct`).
- Generates valid `IHDR`, `IDAT`, and `IEND` chunks without PIL/Pillow.
- Functions: `write_rgba_png`, `create_synthetic_albedo_texture`, `create_synthetic_normal_metalness_texture`.

### 3.2 X-Plane 12 `NORMAL_METALNESS` Fixture
- 4-channel encoding:
  - **Red**: Tangent Normal X ($N_x \in [-1.0, 1.0]$ mapped to $[0, 255]$).
  - **Green**: Tangent Normal Y ($N_y \in [-1.0, 1.0]$ mapped to $[0, 255]$).
  - **Blue**: Metallic factor ($M \in [0.0, 1.0]$ mapped to $[0, 255]$).
  - **Alpha**: Roughness factor ($R \in [0.0, 1.0]$ mapped to $[0, 255]$).
- Supports uniform test textures and quadrant test patterns for spatial UV verification.

### 3.3 Synthetic OBJ8 Models
- `create_minimal_obj8`: Minimal valid textured unit cube with header (`I`, `800`, `OBJ`), `POINT_COUNTS`, 24 `VT` vertices with unit normals and UVs, `IDX10` indices, and `TRIS` commands with clockwise winding.
- `create_animated_aircraft_obj8`: Fuselage root geometry with animated aileron, elevator, rudder, landing gear deploy (`ANIM_trans`), and steerable wheel (`ANIM_rotate` nested under `ANIM_trans`).
- `create_lod_obj8`: Multi-LOD model containing `ATTR_LOD 0.0 500.0` (high poly) and `ATTR_LOD 500.0 2500.0` (low poly).
- `create_corner_case_obj8`: Specialized fixtures covering blank lines/comments, zero-length bone axes, degenerate triangles, extreme DataRef bounds ($-10^6$ to $+10^6$), deep animation nesting (6+ levels), and missing texture references.

### 3.4 Synthetic Plane Maker ACF Projects
- `create_synthetic_acf`: Plane Maker 1200 `.acf` file declaring tail number, aircraft name, ICAO, pilot eye position, and attached object array properties (`_misc_obj_name`, `_misc_obj_xyz`, `_misc_obj_is_cockpit`, `_misc_obj_lighting`).
- `create_full_synthetic_aircraft_project`: Complete multi-part project directory layout:
  ```
  <project_dir>/
  ├── aircraft.acf
  └── objects/
      ├── fuselage.obj
      ├── wings.obj
      ├── cockpit_inn.obj
      ├── landing_gear.obj
      ├── exterior_paint.png
      ├── exterior_NML.png
      ├── cockpit_paint.png
      └── cockpit_NML.png
  ```

---

## 4. Test Runner Architecture (`tests/run_tests.py`)

### 4.1 CLI Execution Command
```powershell
& "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe" `
    --background `
    --factory-startup `
    --python "tests/run_tests.py"
```

### 4.2 CLI Argument Support (Passed after `--`)
- `--tier <1|2|3|4|all>`: Run a specific tier (default: `all`).
- `--module <module_name>`: Run a single modular test suite (e.g. `--module test_obj8_importer`).
- `--verbose` / `-v`: Enable detailed test case output.
- `--list`: List all registered tiers and modules.

### 4.3 Exit Code Semantics
- **Exit Code 0**: All executed tests passed cleanly (or were safely skipped pending planned future milestones).
- **Exit Code 1**: One or more test failures or unhandled errors occurred.

### 4.4 Non-Destructive Scene Isolation
The test suite implements `safe_clean_scene()` between tests to clear objects, meshes, armatures, materials, and images from memory without calling `bpy.ops.wm.read_factory_settings(use_empty=True)` (which unloads registered add-ons and background server processes).

---

## 5. Four Systematic Verification Tiers

### Tier 1: Feature Coverage (Isolation)
Tests each of the 23 core functional features in strict isolation against authoritative specifications:
- **Features 1-6 (M1)**: Add-on registration, OBJ8 geometry/normal/UV parsing, coordinate transforms ($X_{bl} = X_{xp}, Y_{bl} = -Z_{xp}, Z_{bl} = Y_{xp}$), face winding reversal, ACF parsing.
- **Features 7-11 (M2)**: Animation directive tokens, Armature construction in EDIT mode, EditBone minimum length clamping ($> 10^{-4}$m), disconnected child bones (`use_connect=False`), vertex groups, DataRef custom properties.
- **Features 12-16 (M3)**: Principled BSDF v2 socket mapping, Normal Z derivation ($N_z = \sqrt{\max(0, 1 - X^2 - Y^2)}$), DirectX Normal (-Y Green), ORM channel packing, NumPy vectorized processing.
- **Features 17-19 (M4)**: Exterior vs Cockpit filtering, LOD 0 vs All LODs collections, Sidebar panel metadata.
- **Features 20-23 (M5)**: JSON Draft 2020-12 telemetry schema, Unreal Engine `UDataTable` CSV formatting with `---` prefix, SkeletalMesh FBX exporter parameters, OBJ8 round-trip coordinate inversion.

### Tier 2: Boundary & Corner Cases
Adversarial and stress tests verifying parser robustness:
- Empty lines, extraneous whitespace, tabs, and `#` comments in OBJ8 and ACF files.
- Zero-length bone axes (preventing Blender's silent EditBone auto-deletion).
- Degenerate triangles (coincident vertices, duplicate indices).
- Boundary and extreme DataRef values ($-10^6$ to $+10^6$, zero range, inverted range).
- Missing texture files on disk (graceful fallback without unhandled exceptions).
- Out-of-bounds UV coordinates (negative and $> 1.0$ for texture tiling).
- Normal Z clamping protection when $N_x^2 + N_y^2 \ge 1.0$ (preventing `math.sqrt` domain errors).
- Deeply nested animation hierarchies (6+ levels of `ANIM_begin` / `ANIM_end`).
- Empty ACF projects with zero attached objects.
- Non-ASCII and Unicode characters in file paths and object names.

### Tier 3: Cross-Feature Combinations
Verifies interoperability between multiple subsystem modules:
- **Combination 1**: ACF Parser + OBJ8 Parser $\rightarrow$ Multi-object spatial assembly with relative offsets in Blender scene hierarchy.
- **Combination 2**: OBJ8 Animation blocks + Rigging Engine $\rightarrow$ Armature with parent-child bone hierarchy and skinned meshes.
- **Combination 3**: OBJ8 Materials + Principled BSDF v2 Builder $\rightarrow$ PBR shader networks with reconstructed Normal Z.
- **Combination 4**: NORMAL_METALNESS texture + Repacker Engine $\rightarrow$ DirectX Normal + ORM images verified via NumPy.
- **Combination 5**: Armature + Telemetry Exporter $\rightarrow$ SkeletalMesh FBX + JSON mapping + Unreal DataTable CSV.

### Tier 4: Real-World Application Scenarios
Simulates production aircraft workflows:
- **Scenario 1 (Full Aircraft Assembly)**: Assembles multi-part aircraft project (`aircraft.acf` + `objects/` + textures), verifying collection hierarchy, custom normals, and UVs.
- **Scenario 2 (Live Telemetry Synchronization)**: Generates complete telemetry JSON and Unreal Engine `UDataTable` CSV from rigged flight control surfaces.
- **Scenario 3 (Round-Trip OBJ8 Workflow)**: Imports synthetic OBJ8 model, serializes back out to OBJ8 format, re-imports, and verifies complete topological and geometric parity.

---

## 6. Complete 26-Feature Verification Matrix

| # | Feature Name | Milestone | Primary Test Module | Method / Verification |
|---|--------------|-----------|---------------------|-----------------------|
| 1 | Add-on Registration | M1 | `test_tier1_features.py`<br>`test_addon_lifecycle.py` | `test_f01_addon_registration_metadata`<br>`test_addon_bl_info` |
| 2 | OBJ8 Geometry Parsing | M1 | `test_tier1_features.py`<br>`test_obj8_importer.py` | `test_f02_obj8_geometry_parsing`<br>`test_obj8_import_geometry_and_normals` |
| 3 | Modern Custom Normals | M1 | `test_tier1_features.py`<br>`test_obj8_importer.py` | `test_f03_custom_split_normals`<br>`normals_split_custom_set_from_vertices` |
| 4 | Coordinate Frame Mapping | M1 | `test_tier1_features.py`<br>`test_obj8_importer.py` | `test_f04_coordinate_frame_mapping`<br>`test_winding_reversal_guarantees_outward_normals` |
| 5 | UV Map Assignment | M1 | `test_tier1_features.py`<br>`test_obj8_importer.py` | `test_f05_uv_map_assignment`<br>`uv_layer.data.foreach_set` |
| 6 | ACF Project Parsing | M1 | `test_tier1_features.py`<br>`test_acf_importer.py` | `test_f06_acf_project_parsing`<br>`test_acf_parsing_and_attached_objects` |
| 7 | Animation Directives Parsing | M2 | `test_tier1_features.py`<br>`test_rigging.py` | `test_f07_anim_directives_parsing` |
| 8 | Unified Armature Generation | M2 | `test_tier1_features.py`<br>`test_rigging.py` | `test_f08_unified_armature_generation`<br>`test_armature_bone_creation_and_hierarchy` |
| 9 | Bone Creation & Sizing | M2 | `test_tier1_features.py`<br>`test_rigging.py` | `test_f09_bone_creation_sizing`<br>`test_zero_bone_length_fallback` |
| 10 | Mesh Skinning & Vertex Groups | M2 | `test_tier1_features.py`<br>`test_rigging.py` | `test_f10_mesh_skinning_vertex_groups` |
| 11 | DataRef Preservation | M2 | `test_tier1_features.py`<br>`test_rigging.py` | `test_f11_dataref_preservation` |
| 12 | Principled BSDF v2 Shaders | M3 | `test_tier1_features.py`<br>`test_materials.py` | `test_f12_principled_bsdf_v2`<br>`test_principled_bsdf_v2_sockets` |
| 13 | Normal Z Derivation | M3 | `test_tier1_features.py`<br>`test_materials.py` | `test_f13_normal_z_derivation`<br>`test_normal_z_derivation_numerical` |
| 14 | DirectX Normal Repacker | M3 | `test_tier1_features.py`<br>`test_repacker.py` | `test_f14_directx_normal_repacker`<br>`test_vectorized_repacker_logic` |
| 15 | ORM Texture Repacker | M3 | `test_tier1_features.py`<br>`test_repacker.py` | `test_f15_orm_texture_repacker` |
| 16 | Zero-Dependency Processing | M3 | `test_tier1_features.py`<br>`test_repacker.py` | `test_f16_zero_dependency_image_processing` |
| 17 | Component Filtering UI | M4 | `test_tier1_features.py`<br>`test_filtering.py` | `test_f17_component_filtering`<br>`test_component_filtering_classification` |
| 18 | LOD Filtering UI | M4 | `test_tier1_features.py`<br>`test_filtering.py` | `test_f18_lod_filtering`<br>`test_lod_level_filtering_logic` |
| 19 | Sidebar Panel & Tools UI | M4 | `test_tier1_features.py` | `test_f19_sidebar_panel_ui` |
| 20 | Telemetry JSON Exporter | M5 | `test_tier1_features.py`<br>`test_telemetry.py` | `test_f20_telemetry_json_exporter`<br>`test_json_telemetry_structure` |
| 21 | Unreal DataTable CSV Exporter| M5 | `test_tier1_features.py`<br>`test_telemetry.py` | `test_f21_unreal_datatable_csv_exporter`<br>`test_csv_telemetry_format` |
| 22 | Unreal SkeletalMesh FBX | M5 | `test_tier1_features.py`<br>`test_fbx_export.py` | `test_f22_unreal_fbx_exporter`<br>`test_fbx_exporter_flags` |
| 23 | Round-Trip OBJ8 Exporter | M5 | `test_tier1_features.py`<br>`test_roundtrip_obj8.py` | `test_f23_roundtrip_obj8_exporter`<br>`test_roundtrip_coordinate_inversion` |
| 24 | Synthetic Test Asset Generator| Test Track | `test_synthetic_assets.py` | 9 Unit tests verifying PNG, OBJ8, ACF, LOD, and animation generation |
| 25 | Headless CLI Test Suite | Test Track | `tests/run_tests.py` | Multi-tier runner, exit-code propagation, summary reporting |
| 26 | Adversarial Hardening | M6 | `test_tier2_boundary.py` | Stress tests, degenerate geometry, domain clamping, deep nesting |

---

## 7. Current Baseline Verification Results

Executing the complete master suite in Blender 4.3.2:
```
================================================================================
 BLENDER 4.3+ / X-PLANE 12 AUTOMATED TEST SUITE RUNNER
 Workspace Root: c:\Developer Files\Projects\blender\Blender Import XPObj new
 Blender Runtime: 4.3.2 (Headless: True)
================================================================================

 TEST EXECUTION SUMMARY
--------------------------------------------------------------------------------
 Tier / Suite                             | Run    | Pass   | Skip   | Fail   | Error 
--------------------------------------------------------------------------------
 Tier 1: Feature Coverage (Isolation)     | 32     | 32     | 0      | 0      | 0     
 Tier 2: Boundary & Corner Cases          | 10     | 10     | 0      | 0      | 0     
 Tier 3: Cross-Feature Combinations       | 5      | 5      | 0      | 0      | 0     
 Tier 4: Real-World Application Scenarios | 3      | 3      | 0      | 0      | 0     
--------------------------------------------------------------------------------
 TOTAL                                    | 50     | 50     | 0      | 0      | 0     
 Total Execution Time: 1.10 seconds
================================================================================
 >>> OVERALL STATUS: ALL TESTS PASSED (Exit Code: 0)
```
