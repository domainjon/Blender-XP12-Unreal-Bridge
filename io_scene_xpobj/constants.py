"""
constants.py - Constants, coordinate transform matrices, tokens, and schemas for X-Plane 12.

Defines coordinate conversion between X-Plane 12 (+X Right, +Y Up, +Z Aft) and Blender
(+X Right, +Y Back, +Z Up), token definitions for OBJ8 and ACF files, and version metadata.
"""

import math
from typing import Tuple, List, Dict, Any, Optional

# Addon metadata
ADDON_VERSION = (2, 0, 0)
BLENDER_MIN_VERSION = (4, 3, 0)

# ==============================================================================
# Coordinate Space Conversions
# ==============================================================================
# X-Plane 12 Space:
#   +X = Starboard (Right)
#   +Y = Up
#   +Z = Aft / Tail (Nose is -Z)
#
# Blender 4.3+ Space:
#   +X = Starboard (Right)
#   +Y = Forward (Nose is +Y, Tail is -Y)
#   +Z = Up
#
# Transformation Equations:
#   X_blender = X_xp
#   Y_blender = -Z_xp
#   Z_blender = Y_xp
#
# Inverse Equations (Blender -> X-Plane):
#   X_xp = X_blender
#   Y_xp = Z_blender
#   Z_xp = -Y_blender
# ==============================================================================

# 4x4 Homogeneous transformation matrix (Row-major)
# [ 1  0  0  0 ]
# [ 0  0 -1  0 ]
# [ 0  1  0  0 ]
# [ 0  0  0  1 ]
XP_TO_BLENDER_MATRIX = (
    (1.0, 0.0,  0.0, 0.0),
    (0.0, 0.0, -1.0, 0.0),
    (0.0, 1.0,  0.0, 0.0),
    (0.0, 0.0,  0.0, 1.0),
)

# Inverse 4x4 matrix (Blender -> X-Plane)
BLENDER_TO_XP_MATRIX = (
    (1.0,  0.0, 0.0, 0.0),
    (0.0,  0.0, 1.0, 0.0),
    (0.0, -1.0, 0.0, 0.0),
    (0.0,  0.0, 0.0, 1.0),
)


def xp_to_blender_point(x: float, y: float, z: float) -> Tuple[float, float, float]:
    """
    Transforms a 3D position from X-Plane coordinates to Blender coordinates.
    X_blender = X_xp
    Y_blender = -Z_xp
    Z_blender = Y_xp
    """
    return (float(x), -float(z), float(y))


def xp_to_blender_vector(vx: float, vy: float, vz: float) -> Tuple[float, float, float]:
    """
    Transforms a 3D direction/normal vector from X-Plane coordinates to Blender coordinates.
    """
    return (float(vx), -float(vz), float(vy))


def blender_to_xp_point(x: float, y: float, z: float) -> Tuple[float, float, float]:
    """
    Transforms a 3D position from Blender coordinates to X-Plane coordinates.
    X_xp = X_blender
    Y_xp = Z_blender
    Z_xp = -Y_blender
    """
    return (float(x), float(z), -float(y))


def blender_to_xp_vector(vx: float, vy: float, vz: float) -> Tuple[float, float, float]:
    """
    Transforms a 3D direction/normal vector from Blender coordinates to X-Plane coordinates.
    """
    return (float(vx), float(vz), -float(vy))


def reverse_winding_triangle(v0: int, v1: int, v2: int) -> Tuple[int, int, int]:
    """
    Converts clockwise (CW) front-face winding (X-Plane OBJ8 standard)
    to counter-clockwise (CCW) front-face winding (Blender standard).
    (v0, v1, v2) -> (v0, v2, v1)
    """
    return (v0, v2, v1)


# ==============================================================================
# OBJ8 Tokens & Directives
# ==============================================================================
HEADER_LINES = ("I", "800", "OBJ")

# Geometry tokens
TOKEN_VT = "VT"
TOKEN_IDX10 = "IDX10"
TOKEN_IDX = "IDX"
TOKEN_TRIS = "TRIS"
TOKEN_LINES = "LINES"
TOKEN_LIGHTS = "LIGHTS"
TOKEN_POINT_COUNTS = "POINT_COUNTS"
TOKEN_ATTR_LOD = "ATTR_LOD"

# Material tokens
TOKEN_TEXTURE = "TEXTURE"
TOKEN_TEXTURE_LIT = "TEXTURE_LIT"
TOKEN_TEXTURE_NORMAL = "TEXTURE_NORMAL"
TOKEN_TEXTURE_DRAPED = "TEXTURE_DRAPED"
TOKEN_NORMAL_METALNESS = "NORMAL_METALNESS"
TOKEN_GLOBAL_SPECULAR = "GLOBAL_specular"
TOKEN_BLEND_GLASS = "BLEND_GLASS"
TOKEN_GLOBAL_NO_SHADOW = "GLOBAL_no_shadow"
TOKEN_GLOBAL_LUMINANCE = "GLOBAL_luminance"

# Animation tokens
TOKEN_ANIM_BEGIN = "ANIM_begin"
TOKEN_ANIM_END = "ANIM_end"
TOKEN_ANIM_ROTATE = "ANIM_rotate"
TOKEN_ANIM_ROTATE_BEGIN = "ANIM_rotate_begin"
TOKEN_ANIM_ROTATE_KEY = "ANIM_rotate_key"
TOKEN_ANIM_ROTATE_END = "ANIM_rotate_end"
TOKEN_ANIM_TRANS = "ANIM_trans"
TOKEN_ANIM_TRANS_BEGIN = "ANIM_trans_begin"
TOKEN_ANIM_TRANS_KEY = "ANIM_trans_key"
TOKEN_ANIM_TRANS_END = "ANIM_trans_end"
TOKEN_ANIM_HIDE = "ANIM_hide"
TOKEN_ANIM_SHOW = "ANIM_show"
TOKEN_ANIM_KEYFRAME_LOOP = "ANIM_keyframe_loop"

# Lighting & Attribute tokens
TOKEN_LIGHT_NAMED = "LIGHT_NAMED"
TOKEN_LIGHT_CUSTOM = "LIGHT_CUSTOM"
TOKEN_ATTR_SHINY_RAT = "ATTR_shiny_rat"
TOKEN_ATTR_RESET = "ATTR_reset"
TOKEN_ATTR_NO_BLEND = "ATTR_no_blend"
TOKEN_ATTR_BLEND = "ATTR_blend"

# ==============================================================================
# Plane Maker ACF Tokens & Keywords
# ==============================================================================
ACF_HEADER_IDENTIFIER = "ACF"

ACF_PROP_TAILNUM = "acf/_tailnum"
ACF_PROP_NAME = "acf/_name"
ACF_PROP_ICAO = "acf/_ICAO"
ACF_PROP_PE_XYZ = "acf/_pe_xyz"

ACF_MISC_OBJ_NAME = "acf/_misc_obj_name"
ACF_MISC_OBJ_XYZ = "acf/_misc_obj_xyz"
ACF_MISC_OBJ_IS_COCKPIT = "acf/_misc_obj_is_cockpit"
ACF_MISC_OBJ_LIGHTING = "acf/_misc_obj_lighting"

# Substrings identifying cockpit components
COCKPIT_KEYWORDS = (
    "cockpit",
    "cockpit_inn",
    "cockpit_out",
    "panel",
    "interior",
    "cabin",
    "instruments",
    "yoke",
    "pedestal",
    "overhead",
    "avionic",
    "seat",
)

# ==============================================================================
# Rigging & Custom Property Schemas
# ==============================================================================
PROP_DATAREF = "xp_dataref"
PROP_MOTION_TYPE = "xp_motion_type"
PROP_AXIS = "xp_axis"
PROP_KEYFRAMES = "xp_keyframes"
PROP_INPUT_MIN = "xp_input_min"
PROP_INPUT_MAX = "xp_input_max"
PROP_OUTPUT_MIN = "xp_output_min"
PROP_OUTPUT_MAX = "xp_output_max"
PROP_UNIT = "xp_unit"
