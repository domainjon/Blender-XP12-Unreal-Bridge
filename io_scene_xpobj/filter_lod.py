"""
filter_lod.py - Component and LOD filtering engine for X-Plane 12 models.

Implements Features 17 & 18 (Milestone 4):
- Component filtering:
    - 'BOTH': import all components (exterior + cockpit) into organized collections.
    - 'EXTERIOR': import exterior airframe only, skipping cockpit/interior parts.
    - 'COCKPIT': import cockpit/cabin interior parts only, skipping exterior airframe.
- LOD filtering:
    - 'LOD0': import highest detail level (distance starting at 0) and drop lower LODs.
    - 'ALL': import all LOD levels into distinct hierarchy collections (<Model>_LOD0, <Model>_LOD1, ...).
- Blender 4.3 collection hierarchy management:
    - Guarantees collections are properly structured.
    - Prevents double-linking objects or collections to both parent and default scene collections.
"""

import os
from typing import List, Tuple, Dict, Any, Optional, Union

try:
    import bpy
except ImportError:
    bpy = None

from .constants import COCKPIT_KEYWORDS


# ==============================================================================
# Filter Mode Constants
# ==============================================================================

COMPONENT_BOTH = 'BOTH'
COMPONENT_EXTERIOR = 'EXTERIOR'
COMPONENT_COCKPIT = 'COCKPIT'

LOD_MODE_LOD0 = 'LOD0'
LOD_MODE_ALL = 'ALL'

COMPONENT_FILTER_ITEMS = [
    (COMPONENT_BOTH, "Both (Exterior & Cockpit)", "Import all components into organized collections"),
    (COMPONENT_EXTERIOR, "Exterior Only", "Import exterior airframe and flight surfaces only"),
    (COMPONENT_COCKPIT, "Cockpit Only", "Import cockpit and cabin interior objects only"),
]

LOD_FILTER_ITEMS = [
    (LOD_MODE_LOD0, "LOD 0 Only (Highest Detail)", "Import highest detail LOD 0 only and drop lower detail LODs"),
    (LOD_MODE_ALL, "All LODs (Separate Collections)", "Import and organize all LOD levels into distinct hierarchy collections"),
]


# ==============================================================================
# Component Filtering Logic
# ==============================================================================

def classify_component(filename_or_path: str, is_cockpit_flag: Optional[bool] = None) -> bool:
    """
    Classifies a component as cockpit (True) or exterior (False).

    :param filename_or_path: File name or relative path of the component
    :param is_cockpit_flag: Explicit boolean flag from Plane Maker .acf (takes precedence)
    :return: True if cockpit/interior, False if exterior airframe
    """
    if is_cockpit_flag is not None:
        return bool(is_cockpit_flag)

    clean_name = os.path.basename(filename_or_path).lower()
    return any(kw in clean_name for kw in COCKPIT_KEYWORDS)


def should_import_component(is_cockpit: bool, filter_mode: str = COMPONENT_BOTH) -> bool:
    """
    Determines whether a component should be imported given its classification
    and the selected filter mode.

    :param is_cockpit: True if component is cockpit, False if exterior
    :param filter_mode: 'BOTH', 'EXTERIOR', or 'COCKPIT'
    :return: True if component should be imported, False to skip
    """
    mode = str(filter_mode).upper()
    if mode == COMPONENT_EXTERIOR and is_cockpit:
        return False
    if mode == COMPONENT_COCKPIT and not is_cockpit:
        return False
    return True


def filter_component_list(
    items: List[Any],
    filter_mode: str = COMPONENT_BOTH,
    is_cockpit_getter: Optional[Any] = None,
) -> List[Any]:
    """
    Filters a sequence of items (e.g. ACFAttachedObject or tuples) by component filter mode.

    :param items: List of items to filter
    :param filter_mode: 'BOTH', 'EXTERIOR', or 'COCKPIT'
    :param is_cockpit_getter: Optional callable `fn(item) -> bool` or attribute name
    :return: Filtered list of items
    """
    result = []
    for it in items:
        if is_cockpit_getter is not None:
            if callable(is_cockpit_getter):
                cockpit = is_cockpit_getter(it)
            elif isinstance(is_cockpit_getter, str):
                cockpit = getattr(it, is_cockpit_getter, False)
            else:
                cockpit = False
        elif hasattr(it, "is_cockpit"):
            cockpit = getattr(it, "is_cockpit")
        elif isinstance(it, dict) and "is_cockpit" in it:
            cockpit = bool(it["is_cockpit"])
        elif isinstance(it, (tuple, list)) and len(it) > 1 and isinstance(it[1], bool):
            cockpit = it[1]
        else:
            cockpit = classify_component(str(it))

        if should_import_component(cockpit, filter_mode):
            result.append(it)
    return result


# ==============================================================================
# LOD Filtering Logic
# ==============================================================================

def get_lod_collection_name(base_name: str, lod_index: int) -> str:
    """
    Returns standard collection name for a given LOD level, e.g. 'Cessna_LOD0'.
    """
    return f"{base_name}_LOD{lod_index}"


def resolve_target_lods(
    lod_ranges: List[Tuple[float, float]],
    lod_mode: str = LOD_MODE_LOD0,
    lod_level: Optional[int] = 0,
) -> List[int]:
    """
    Resolves which LOD indices should be extracted from parsed OBJ8 data.

    :param lod_ranges: List of (near, far) float tuples from parsed ATTR_LOD directives
    :param lod_mode: 'LOD0' or 'ALL'
    :param lod_level: Specific single LOD index (used when lod_mode is not 'ALL')
    :return: List of 0-based integer LOD indices to build
    """
    total_lods = max(1, len(lod_ranges))
    mode = str(lod_mode).upper() if lod_mode else LOD_MODE_LOD0

    if mode == LOD_MODE_ALL:
        return list(range(total_lods))

    if lod_level is not None and 0 <= lod_level < total_lods:
        return [lod_level]

    return [0]


def group_tris_by_lod(commands: List[Any]) -> Dict[int, List[Any]]:
    """
    Groups TrisCommand instances by their `lod_index`.

    :param commands: List of parsed OBJ8 command objects
    :return: Dict mapping lod_index (int) -> list of TrisCommand objects
    """
    grouped: Dict[int, List[Any]] = {}
    for cmd in commands:
        if getattr(cmd, "cmd_type", None) == "TRIS" or cmd.__class__.__name__ == "TrisCommand":
            idx = getattr(cmd, "lod_index", 0)
            grouped.setdefault(idx, []).append(cmd)
    return grouped


def filter_lod_faces(
    parsed_data: Any,
    lod_mode: str = LOD_MODE_LOD0,
    target_lod: Optional[int] = 0,
) -> Dict[int, List[Tuple[int, int, int]]]:
    """
    Extracts face indices grouped by LOD index according to the requested LOD filter mode.

    :param parsed_data: ParsedOBJ8 instance
    :param lod_mode: 'LOD0' or 'ALL'
    :param target_lod: Specific LOD index if lod_mode is single-LOD
    :return: Dict mapping lod_index -> list of (v0, v1, v2) triangle faces
    """
    lod_ranges = getattr(parsed_data, "lod_ranges", [])
    commands = getattr(parsed_data, "commands", [])
    grouped = group_tris_by_lod(commands)

    active_indices = resolve_target_lods(lod_ranges, lod_mode=lod_mode, lod_level=target_lod)

    result: Dict[int, List[Tuple[int, int, int]]] = {}
    for idx in active_indices:
        faces: List[Tuple[int, int, int]] = []
        for cmd in grouped.get(idx, []):
            cmd_faces = getattr(cmd, "faces", [])
            faces.extend(cmd_faces)
        result[idx] = faces

    # Fallback: if active requested LOD had 0 faces but others exist, fallback to all available
    if not any(result.values()) and grouped:
        all_faces: List[Tuple[int, int, int]] = []
        for cmd_list in grouped.values():
            for cmd in cmd_list:
                all_faces.extend(getattr(cmd, "faces", []))
        result[0] = all_faces

    return result


# ==============================================================================
# Blender 4.3 Collection Hierarchy Management
# ==============================================================================

def get_or_create_collection(
    name: str,
    parent: Optional[Any] = None,
    context: Optional[Any] = None,
) -> Any:
    """
    Retrieves an existing Blender collection or creates a new one, ensuring it is
    safely linked into `parent` (or the active scene collection) without duplicates.

    :param name: Name of the collection
    :param parent: Target parent bpy.types.Collection
    :param context: Blender context (optional)
    :return: bpy.types.Collection instance
    """
    if bpy is None:
        return None

    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)

    target_parent = parent
    if target_parent is None:
        if context and hasattr(context, "scene") and context.scene:
            target_parent = context.scene.collection
        elif bpy.context and hasattr(bpy.context, "scene") and bpy.context.scene:
            target_parent = bpy.context.scene.collection

    if target_parent is not None:
        if coll.name not in target_parent.children:
            target_parent.children.link(coll)

    return coll


def link_collection_safely(parent: Any, child: Any) -> None:
    """
    Safely links a child collection into a parent collection, checking for existing linkage.
    """
    if bpy is None or parent is None or child is None:
        return
    if child.name not in parent.children:
        parent.children.link(child)


def link_object_to_collection(
    obj: Any,
    target_collection: Any,
    unlink_from_others: bool = True,
) -> None:
    """
    Safely links an object to a target collection and optionally unlinks it from
    all other collections (e.g. scene root) to prevent double-linking.

    :param obj: bpy.types.Object
    :param target_collection: bpy.types.Collection to place object in
    :param unlink_from_others: If True, unlinks obj from any other collection it belongs to
    """
    if bpy is None or obj is None or target_collection is None:
        return

    if obj.name not in target_collection.objects:
        target_collection.objects.link(obj)

    if unlink_from_others:
        for col in list(obj.users_collection):
            if col != target_collection:
                try:
                    col.objects.unlink(obj)
                except RuntimeError:
                    pass


def setup_acf_collections(
    aircraft_name: str,
    component_filter: str = COMPONENT_BOTH,
    parent_collection: Optional[Any] = None,
    context: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Creates and links hierarchical collections for an ACF aircraft project in Blender 4.3:
    - Root collection: <AircraftName>
    - Sub-collections based on component_filter:
      - <AircraftName>_Exterior (if BOTH or EXTERIOR)
      - <AircraftName>_Cockpit (if BOTH or COCKPIT)

    :param aircraft_name: Name of the aircraft (from ACF metadata)
    :param component_filter: 'BOTH', 'EXTERIOR', or 'COCKPIT'
    :param parent_collection: Parent collection to link root collection into
    :param context: Blender context
    :return: Dict containing 'root', 'exterior', 'cockpit' collection references
    """
    sanitized = aircraft_name.strip() or "X-Plane_Aircraft"
    root_col = get_or_create_collection(sanitized, parent=parent_collection, context=context)

    result = {
        'root': root_col,
        'exterior': None,
        'cockpit': None,
    }

    mode = str(component_filter).upper()
    if mode in (COMPONENT_BOTH, COMPONENT_EXTERIOR):
        ext_col = get_or_create_collection(f"{sanitized}_Exterior", parent=root_col, context=context)
        result['exterior'] = ext_col

    if mode in (COMPONENT_BOTH, COMPONENT_COCKPIT):
        cockpit_col = get_or_create_collection(f"{sanitized}_Cockpit", parent=root_col, context=context)
        result['cockpit'] = cockpit_col

    return result


def setup_lod_collections(
    model_name: str,
    lod_indices: List[int],
    parent_collection: Optional[Any] = None,
    context: Optional[Any] = None,
) -> Dict[int, Any]:
    """
    Creates distinct hierarchy collections for all specified LOD levels:
    e.g. <Model>_LOD0, <Model>_LOD1, ... linked under parent_collection.

    :param model_name: Name of the model
    :param lod_indices: List of LOD indices, e.g. [0, 1]
    :param parent_collection: Parent collection to contain the LOD collections
    :param context: Blender context
    :return: Dict mapping lod_index -> bpy.types.Collection
    """
    lod_collections: Dict[int, Any] = {}
    for idx in lod_indices:
        col_name = get_lod_collection_name(model_name, idx)
        coll = get_or_create_collection(col_name, parent=parent_collection, context=context)
        lod_collections[idx] = coll
    return lod_collections
