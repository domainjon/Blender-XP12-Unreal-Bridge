"""
import_acf.py - Plane Maker .acf aircraft project parser and multi-part assembler.

Parses Plane Maker .acf definition files (XP10, XP11, XP12):
- Extracts aircraft metadata (tailnum, name, ICAO, pilot eye position).
- Resolves attached 3D OBJ8 models from objects/ directory with relative coordinate frames.
- Classifies objects into Exterior vs. Cockpit collections based on flags and naming.
- Applies relative coordinate offsets: X_bl = X_xp, Y_bl = -Z_xp, Z_bl = Y_xp.
- Supports component filtering (Both, Exterior Only, Cockpit Only).
"""

import os
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional

try:
    import bpy
    from mathutils import Vector
except ImportError:
    bpy = None
    Vector = None

from .constants import (
    xp_to_blender_point,
    ACF_HEADER_IDENTIFIER,
    COCKPIT_KEYWORDS,
)
from .import_obj8 import import_obj8_file, parse_obj8, build_mesh
from .anim_rigging import build_unified_armature


@dataclass
class ACFAttachedObject:
    """Represents an external 3D object attached to an aircraft project in .acf."""
    index: int
    rel_path: str
    abs_path: str
    offset_xp: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    offset_blender: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    is_cockpit: bool = False
    lighting: int = 0
    exists: bool = False


@dataclass
class ParsedACF:
    """Parsed representation of a Plane Maker .acf aircraft project."""
    filepath: str
    aircraft_name: str = "X-Plane Aircraft"
    tailnum: str = ""
    icao: str = ""
    version_string: str = ""
    pe_xyz: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    attached_objects: List[ACFAttachedObject] = field(default_factory=list)
    unreferenced_objects: List[str] = field(default_factory=list)
    properties: Dict[str, str] = field(default_factory=dict)


def parse_acf(filepath: str) -> ParsedACF:
    """
    Parses a Plane Maker .acf file into a ParsedACF structure.

    :param filepath: Path to the .acf file
    :return: ParsedACF with all attached objects and relative coordinates
    :raises ValueError: If header is not a valid ACF file
    :raises FileNotFoundError: If the file does not exist
    """
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"ACF file not found: {filepath}")

    base_dir = os.path.dirname(os.path.abspath(filepath))
    parsed = ParsedACF(filepath=os.path.abspath(filepath))

    # Read lines with utf-8, fallback to latin-1
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        with open(filepath, 'r', encoding='latin-1') as f:
            lines = f.readlines()

    # Validate header
    header_tokens = []
    line_idx = 0
    while line_idx < len(lines) and len(header_tokens) < 3:
        raw = lines[line_idx].strip()
        line_idx += 1
        if not raw or raw.startswith('#'):
            continue
        header_tokens.append(raw)

    if (
        len(header_tokens) < 3
        or header_tokens[0] not in ('I', 'A')
        or header_tokens[2].split()[0] != ACF_HEADER_IDENTIFIER
    ):
        raise ValueError(
            f"Invalid ACF header in '{filepath}'. Expected ['I'|'A', '<version> Version', 'ACF'], got {header_tokens}"
        )

    parsed.version_string = header_tokens[1]

    # Temporary maps for attached object array properties
    obj_paths: Dict[int, str] = {}
    obj_xyz: Dict[int, List[float]] = {}
    obj_is_cockpit: Dict[int, bool] = {}
    obj_lighting: Dict[int, int] = {}
    pe_xyz_coords = [0.0, 0.0, 0.0]

    for line_str in lines[line_idx:]:
        line_str = line_str.strip()
        if not line_str or line_str.startswith('#'):
            continue

        tokens = line_str.split(None, 2)
        if len(tokens) < 2:
            continue

        # Check for 'P' property prefix
        if tokens[0] == 'P' and len(tokens) >= 3:
            prop_key = tokens[1]
            prop_val = tokens[2].strip()
            parsed.properties[prop_key] = prop_val

            # Basic metadata
            if prop_key in ('acf/_name', '_acf_name'):
                parsed.aircraft_name = prop_val
            elif prop_key in ('acf/_tailnum', '_acf_tailnum'):
                parsed.tailnum = prop_val
            elif prop_key in ('acf/_ICAO', '_acf_ICAO'):
                parsed.icao = prop_val

            # Pilot Eye position
            elif prop_key.startswith('acf/_pe_xyz/'):
                idx_part = prop_key.split('/')[-1]
                try:
                    c_idx = int(idx_part)
                    if 0 <= c_idx < 3:
                        pe_xyz_coords[c_idx] = float(prop_val)
                except ValueError:
                    pass

            # Modern X-Plane 11/12 attached objects: _obja/<idx>/<field>
            elif prop_key.startswith('_obja/') or prop_key.startswith('acf/_obja/'):
                parts = prop_key.split('/')
                idx_part = parts[1] if parts[0] == '_obja' else (parts[2] if len(parts) > 2 else "")
                field_part = parts[2] if parts[0] == '_obja' and len(parts) > 2 else (parts[3] if len(parts) > 3 else "")
                if idx_part.isdigit() and field_part:
                    try:
                        o_idx = int(idx_part)
                        if field_part in ('_v10_att_file_stl', '_att_file_stl', '_att_file'):
                            clean_val = prop_val.strip('"\'').replace('\\', '/')
                            obj_paths[o_idx] = clean_val
                        elif field_part == '_v10_att_x_acf_prt_ref':
                            if o_idx not in obj_xyz:
                                obj_xyz[o_idx] = [0.0, 0.0, 0.0]
                            obj_xyz[o_idx][0] = float(prop_val)
                        elif field_part == '_v10_att_y_acf_prt_ref':
                            if o_idx not in obj_xyz:
                                obj_xyz[o_idx] = [0.0, 0.0, 0.0]
                            obj_xyz[o_idx][1] = float(prop_val)
                        elif field_part == '_v10_att_z_acf_prt_ref':
                            if o_idx not in obj_xyz:
                                obj_xyz[o_idx] = [0.0, 0.0, 0.0]
                            obj_xyz[o_idx][2] = float(prop_val)
                        elif field_part == '_v10_is_internal':
                            try:
                                v = int(prop_val)
                                obj_is_cockpit[o_idx] = (v in (1, 2))
                            except ValueError:
                                pass
                        elif field_part in ('_v10_lighting', '_obj_lighting'):
                            try:
                                obj_lighting[o_idx] = int(prop_val)
                            except ValueError:
                                pass
                    except (ValueError, IndexError):
                        pass

            # Legacy X-Plane attached object path
            elif prop_key.startswith('acf/_misc_obj_name/') or prop_key.startswith('acf/_obj_path/') or prop_key.startswith('_misc_obj_name/'):
                idx_part = prop_key.split('/')[-1]
                try:
                    o_idx = int(idx_part)
                    clean_val = prop_val.strip('"\'').replace('\\', '/')
                    obj_paths[o_idx] = clean_val
                except ValueError:
                    pass

            # Attached object XYZ offset (indexed /0, /1, /2 or triplet)
            elif 'acf/_misc_obj_xyz/' in prop_key:
                parts = prop_key.split('/')
                # Form: acf/_misc_obj_xyz/<i>/<axis>
                if len(parts) >= 4:
                    try:
                        o_idx = int(parts[2])
                        axis_idx = int(parts[3])
                        if o_idx not in obj_xyz:
                            obj_xyz[o_idx] = [0.0, 0.0, 0.0]
                        if 0 <= axis_idx < 3:
                            obj_xyz[o_idx][axis_idx] = float(prop_val)
                    except ValueError:
                        pass
                # Form: acf/_misc_obj_xyz/<i> <x> <y> <z>
                elif len(parts) == 3:
                    try:
                        o_idx = int(parts[2])
                        coords = [float(v) for v in prop_val.split()]
                        if len(coords) >= 3:
                            obj_xyz[o_idx] = coords[:3]
                    except ValueError:
                        pass

            # Attached object cockpit flag
            elif prop_key.startswith('acf/_misc_obj_is_cockpit/'):
                idx_part = prop_key.split('/')[-1]
                try:
                    o_idx = int(idx_part)
                    obj_is_cockpit[o_idx] = (int(prop_val) != 0)
                except ValueError:
                    pass

            # Attached object lighting
            elif prop_key.startswith('acf/_misc_obj_lighting/'):
                idx_part = prop_key.split('/')[-1]
                try:
                    o_idx = int(idx_part)
                    obj_lighting[o_idx] = int(prop_val)
                except ValueError:
                    pass

    parsed.pe_xyz = (pe_xyz_coords[0], pe_xyz_coords[1], pe_xyz_coords[2])

    # Assemble ACFAttachedObject records
    all_indices = sorted(set(list(obj_paths.keys()) + list(obj_xyz.keys())))
    referenced_rel_paths = set()

    for idx in all_indices:
        rel_path = obj_paths.get(idx, f"objects/part_{idx}.obj")
        norm_rel = rel_path.lstrip('/\\')

        # Only process 3D mesh .obj files (skip .wpn, .afl, etc.)
        if not norm_rel.lower().endswith(".obj"):
            continue

        referenced_rel_paths.add(os.path.normpath(norm_rel).lower())

        # Resolve candidate paths across nested objects/ subdirectories
        abs_candidates = [
            os.path.normpath(os.path.join(base_dir, norm_rel)),
            os.path.normpath(os.path.join(base_dir, "objects", norm_rel)),
            os.path.normpath(os.path.join(base_dir, "objects", os.path.basename(norm_rel))),
            os.path.normpath(os.path.join(base_dir, os.path.basename(norm_rel))),
        ]

        resolved_abs = abs_candidates[0]
        file_exists = False
        for c in abs_candidates:
            if os.path.isfile(c):
                resolved_abs = c
                file_exists = True
                break

        # If not yet found, search recursively inside objects/ directory
        if not file_exists:
            base_fname = os.path.basename(norm_rel).lower()
            objects_dir = os.path.join(base_dir, "objects")
            if os.path.isdir(objects_dir):
                for r_dir, _, f_names in os.walk(objects_dir):
                    for fn in f_names:
                        if fn.lower() == base_fname:
                            resolved_abs = os.path.join(r_dir, fn)
                            file_exists = True
                            break
                    if file_exists:
                        break

        coords = obj_xyz.get(idx, [0.0, 0.0, 0.0])
        xp_offset = (coords[0], coords[1], coords[2])
        bl_offset = xp_to_blender_point(coords[0], coords[1], coords[2])

        # Determine cockpit status: check path keywords and explicit flag
        lower_rel = norm_rel.lower()
        is_cockpit = any(kw in lower_rel for kw in COCKPIT_KEYWORDS) or obj_is_cockpit.get(idx, False)

        lighting = obj_lighting.get(idx, 0)

        entry = ACFAttachedObject(
            index=idx,
            rel_path=rel_path,
            abs_path=resolved_abs,
            offset_xp=xp_offset,
            offset_blender=bl_offset,
            is_cockpit=is_cockpit,
            lighting=lighting,
            exists=file_exists
        )
        parsed.attached_objects.append(entry)

    # Scan objects/ directory for unreferenced .obj files (fallback discovery)
    objects_dir = os.path.join(base_dir, "objects")
    if os.path.isdir(objects_dir):
        for fname in os.listdir(objects_dir):
            if fname.lower().endswith(".obj"):
                rel_candidate = os.path.normpath(os.path.join("objects", fname)).lower()
                if rel_candidate not in referenced_rel_paths:
                    parsed.unreferenced_objects.append(os.path.join(objects_dir, fname))

    return parsed


def import_acf_project(
    acf_filepath: str,
    context: Optional[Any] = None,
    component_filter: str = 'BOTH',
    lod_level: Optional[int] = 0,
) -> Dict[str, Any]:
    """
    Imports and assembles a full X-Plane 12 aircraft project (.acf) into Blender 4.3+.

    - Creates hierarchical collections: <Aircraft>, <Aircraft>_Exterior, <Aircraft>_Cockpit.
    - Imports all attached .obj models from objects/ with relative coordinate transforms.
    - Filters components according to component_filter ('BOTH', 'EXTERIOR', 'COCKPIT').
    - Applies relative coordinate offsets: X_bl = X_xp, Y_bl = -Z_xp, Z_bl = Y_xp.
    - Assembles all imported components under a single unified Armature.
    - Tags custom properties on imported objects.

    :param acf_filepath: Path to the .acf file
    :param context: Blender bpy.context
    :param component_filter: 'BOTH', 'EXTERIOR', or 'COCKPIT'
    :param lod_level: Specific LOD level to import (default 0)
    :return: Dict containing 'parsed_acf', 'root_collection', 'imported_objects', 'armature_obj'
    """
    if bpy is None:
        raise RuntimeError("Blender 'bpy' module is required to import ACF projects.")

    parsed_acf = parse_acf(acf_filepath)

    # Base name for collection
    sanitized_name = parsed_acf.aircraft_name.strip() or os.path.splitext(os.path.basename(acf_filepath))[0]

    # Create root aircraft collection
    root_col = bpy.data.collections.new(sanitized_name)
    if bpy.context and bpy.context.scene:
        bpy.context.scene.collection.children.link(root_col)

    # Create sub-collections
    ext_col = bpy.data.collections.new(f"{sanitized_name}_Exterior")
    cockpit_col = bpy.data.collections.new(f"{sanitized_name}_Cockpit")
    root_col.children.link(ext_col)
    root_col.children.link(cockpit_col)

    imported_objects: List[Any] = []
    skipped_objects: List[str] = []
    items_to_rig: List[Tuple[Any, Any]] = []

    # Import each attached object
    for entry in parsed_acf.attached_objects:
        # Check component filter
        if component_filter == 'EXTERIOR' and entry.is_cockpit:
            skipped_objects.append(entry.rel_path)
            continue
        if component_filter == 'COCKPIT' and not entry.is_cockpit:
            skipped_objects.append(entry.rel_path)
            continue

        if not entry.exists or not os.path.isfile(entry.abs_path):
            skipped_objects.append(entry.rel_path)
            continue

        target_col = cockpit_col if entry.is_cockpit else ext_col

        try:
            # Parse OBJ8 and build mesh
            parsed_obj = parse_obj8(entry.abs_path)
            part_name = os.path.splitext(os.path.basename(entry.abs_path))[0]
            part_obj = build_mesh(
                parsed_data=parsed_obj,
                context=context,
                name=f"{part_name}_{entry.index}",
                lod_level=lod_level
            )

            # Apply relative coordinate offset in Blender coordinates
            part_obj.location = Vector(entry.offset_blender)

            # Assign custom metadata properties
            part_obj["acf_is_cockpit"] = 1 if entry.is_cockpit else 0
            part_obj["acf_lighting"] = entry.lighting
            part_obj["acf_rel_path"] = entry.rel_path
            part_obj["acf_offset_xp"] = list(entry.offset_xp)
            part_obj["acf_offset_blender"] = list(entry.offset_blender)
            part_obj["acf_index"] = entry.index

            # Ensure linked to target collection and unlinked from all other collections
            if part_obj.name not in target_col.objects:
                target_col.objects.link(part_obj)
            for col in list(part_obj.users_collection):
                if col != target_col:
                    col.objects.unlink(part_obj)

            imported_objects.append(part_obj)
            items_to_rig.append((parsed_obj, part_obj))

        except Exception as e:
            print(f"[io_scene_xpobj] Warning: Failed importing attached part '{entry.rel_path}': {e}")
            skipped_objects.append(entry.rel_path)

    # Build a unified Armature for the entire aircraft
    armature_obj = None
    if items_to_rig:
        try:
            arm_name = f"{sanitized_name}_Armature"
            armature_obj = build_unified_armature(
                items=items_to_rig,
                context=context,
                armature_name=arm_name
            )
            if armature_obj is not None:
                if armature_obj.name not in root_col.objects:
                    root_col.objects.link(armature_obj)
                for col in list(armature_obj.users_collection):
                    if col != root_col:
                        col.objects.unlink(armature_obj)
        except Exception as e:
            print(f"[io_scene_xpobj] Warning: Failed building unified armature: {e}")

    return {
        'parsed_acf': parsed_acf,
        'root_collection': root_col,
        'exterior_collection': ext_col,
        'cockpit_collection': cockpit_col,
        'imported_objects': imported_objects,
        'skipped_objects': skipped_objects,
        'armature_obj': armature_obj,
    }

