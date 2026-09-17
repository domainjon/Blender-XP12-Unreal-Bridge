# X-Plane 12 to Blender 4+ & Unreal Engine Aircraft Bridge

A comprehensive, production-grade Blender 4.3+ add-on that imports X-Plane 12 aircraft projects (`.acf` and `.obj`) with complete hierarchy, Skeletal Mesh rigging, and PBR materials, generates Unreal Engine telemetry mapping (JSON/CSV) with DirectX Normal and ORM texture repacking, and enables round-trip export back to X-Plane 12.

---

## Key Features

- **Full Aircraft Project Import (`.acf`):**
  Parses Plane Maker `.acf` files to automatically discover and assemble all attached component objects (`Fuselage.obj`, `Wings.obj`, `Gear.obj`, `Cockpit.obj`, etc.) at their precise relative spatial coordinates.

- **Standalone OBJ8 Import (`.obj`):**
  Full support for X-Plane 12 OBJ8 syntax:
  - Custom split vertex normals (`normals_split_custom_set_from_vertices`) fully compliant with Blender 4.3+ API (eliminating legacy read-only `MeshVertex.normal` crashes).
  - Counter-clockwise face winding conversion.
  - High-performance loop UV assignment.

- **Unreal Engine Armature & Rigging (SkeletalMesh):**
  Parses X-Plane animation directives (`ANIM_begin`, `ANIM_rotate`, `ANIM_trans`, `ANIM_end`) and constructs a unified Blender Armature where moving flight controls (ailerons, flaps, elevators, rudder, landing gear, steerable wheels, propellers) are rigged as bones. Preserves X-Plane DataRef metadata on each bone.

- **Principled BSDF v2 PBR Shaders:**
  Interprets X-Plane 12 `NORMAL_METALNESS` format:
  - Procedural reconstruction of Normal Z: $\sqrt{\max(0, 1 - X^2 - Y^2)}$
  - Metallic routing from Blue channel
  - Roughness routing from Alpha channel
  - Emission routing for night/cockpit lit textures (`TEXTURE_LIT`)

- **Zero-Dependency Unreal Engine Texture Repacker:**
  Converts X-Plane 12 normal/metalness textures into Unreal Engine-standard textures using only NumPy and Blender C-buffers:
  - **DirectX Normal Map (`_Normal_DX.png`):** Inverted green channel (-Y) and embedded reconstructed Normal Z.
  - **ORM Map (`_ORM.png`):** Red = Ambient Occlusion (1.0), Green = Roughness, Blue = Metallic.

- **Real-Time Telemetry Exporter for Unreal Engine:**
  1-click export generating:
  1. `[Aircraft].fbx` — UE5-ready SkeletalMesh with proper bone axes.
  2. `[Aircraft]_telemetry.json` — DataRef-to-Bone mapping schema (axes, min/max limits, units).
  3. `[Aircraft]_datatable.csv` — Unreal Engine `UDataTable` import-ready CSV.
  *Used for real-time pilot synchronization via UDP telemetry.*

- **Round-Trip X-Plane 12 OBJ8 Exporter:**
  Exports modified meshes back to valid X-Plane 12 OBJ8 files with coordinate conversion, clockwise winding, and animation blocks reconstructed from Armature bones.

- **3D Viewport N-Panel:**
  Convenient sidebar tab (**"X-Plane 12"**) with 1-click buttons for Import, Texture Repack, UE Export, and OBJ8 Export.

---

## Installation (Blender 4.3+)

1. Download or clone this repository.
2. In Blender 4.3+, open **Edit > Preferences > Add-ons**.
3. Click the drop-down arrow at the top right, select **Install from Disk...**, and select the `io_scene_xpobj` folder (or a `.zip` containing it).
4. Enable the checkbox for **X-Plane 12 Aircraft & OBJ Importer / Exporter**.

---

## Quick Start Guide

### 1. Import Full Aircraft
- Navigate to **File > Import > X-Plane Aircraft (.acf)**.
- Select your aircraft's `.acf` file.
- Under import settings, select your desired component filter:
  - `Both (Exterior & Cockpit)`
  - `Exterior Only`
  - `Cockpit Only`
- Click **Import X-Plane Aircraft**.

### 2. Repack Textures for Unreal Engine
- Open the 3D Viewport sidebar by pressing `N`.
- Click on the **X-Plane 12** tab.
- Click **Repack Textures for UE**.
- The add-on generates `[Name]_Normal_DX.png` and `[Name]_ORM.png` in the texture directory.

### 3. Export to Unreal Engine
- Select the aircraft Armature or meshes.
- In the sidebar or via **File > Export > Unreal Engine Aircraft (FBX + DataRef)**, choose the export destination.
- The exporter writes the `.fbx`, `_telemetry.json`, and `_datatable.csv` files.

### 4. Export back to X-Plane 12
- Go to **File > Export > X-Plane Object (.obj)**.
- Choose your export destination and click **Export X-Plane OBJ**.

---

## Testing & Verification

Run the automated test suite in headless Blender 4.3:

```powershell
& "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe" --background --factory-startup --python tests/run_tests.py -- --tier all
```

Pass rate: **50/50 Tiered Integration Tests + 92/92 Discovery Unittests Passed (100%)**.

---

## License

MIT License. Based on original work by David C. Prue (2017) and FSWindowSeat (2020), modernized and expanded for Blender 4.3+ and Unreal Engine pipelines.
