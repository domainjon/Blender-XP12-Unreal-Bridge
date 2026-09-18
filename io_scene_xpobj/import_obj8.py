"""
import_obj8.py - Robust X-Plane 12 OBJ8 geometry, normals, UVs, and animation parser.

Compliant with Blender 4.3+ Python API:
- Replaces read-only MeshVertex.normal with me.normals_split_custom_set_from_vertices.
- Eliminates removed mesh.use_auto_smooth and deprecated normal calculations.
- Reverses clockwise triangle face winding to counter-clockwise: (v0, v2, v1).
- Converts coordinates: X_blender = X_xp, Y_blender = -Z_xp, Z_blender = Y_xp.
- High-performance loop UV assignment via foreach_set('uv', flat_uvs).
- Structures ParsedOBJ8 with full command stream for downstream skeletal rigging.
"""

import os
import math
import pathlib
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
    xp_to_blender_vector,
    reverse_winding_triangle,
    TOKEN_VT,
    TOKEN_IDX10,
    TOKEN_IDX,
    TOKEN_TRIS,
    TOKEN_POINT_COUNTS,
    TOKEN_ATTR_LOD,
    TOKEN_TEXTURE,
    TOKEN_TEXTURE_LIT,
    TOKEN_TEXTURE_NORMAL,
    TOKEN_TEXTURE_DRAPED,
    TOKEN_NORMAL_METALNESS,
    TOKEN_GLOBAL_SPECULAR,
    TOKEN_BLEND_GLASS,
    TOKEN_GLOBAL_NO_SHADOW,
    TOKEN_GLOBAL_LUMINANCE,
    TOKEN_ANIM_BEGIN,
    TOKEN_ANIM_END,
    TOKEN_ANIM_ROTATE,
    TOKEN_ANIM_ROTATE_BEGIN,
    TOKEN_ANIM_ROTATE_KEY,
    TOKEN_ANIM_ROTATE_END,
    TOKEN_ANIM_TRANS,
    TOKEN_ANIM_TRANS_BEGIN,
    TOKEN_ANIM_TRANS_KEY,
    TOKEN_ANIM_TRANS_END,
    TOKEN_ANIM_HIDE,
    TOKEN_ANIM_SHOW,
    TOKEN_ANIM_KEYFRAME_LOOP,
)
from .materials import create_xplane_pbr_material


# ==============================================================================
# Matrix 4x4 Math Helpers (OpenGL / OBJ8 Transformation Stack)
# ==============================================================================

def mat4_identity() -> List[List[float]]:
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def mat4_mul(a: List[List[float]], b: List[List[float]]) -> List[List[float]]:
    c = [[0.0] * 4 for _ in range(4)]
    for i in range(4):
        for j in range(4):
            c[i][j] = a[i][0] * b[0][j] + a[i][1] * b[1][j] + a[i][2] * b[2][j] + a[i][3] * b[3][j]
    return c


def mat4_translate(tx: float, ty: float, tz: float) -> List[List[float]]:
    m = mat4_identity()
    m[0][3] = float(tx)
    m[1][3] = float(ty)
    m[2][3] = float(tz)
    return m


def mat4_rotate(angle_deg: float, ax: float, ay: float, az: float) -> List[List[float]]:
    rad = math.radians(float(angle_deg))
    c = math.cos(rad)
    s = math.sin(rad)
    l = math.sqrt(ax * ax + ay * ay + az * az)
    if l < 1e-9:
        return mat4_identity()
    x, y, z = ax / l, ay / l, az / l
    omc = 1.0 - c
    return [
        [x * x * omc + c,     x * y * omc - z * s, x * z * omc + y * s, 0.0],
        [y * x * omc + z * s, y * y * omc + c,     y * z * omc - x * s, 0.0],
        [z * x * omc - y * s, z * y * omc + x * s, z * z * omc + c,     0.0],
        [0.0,                 0.0,                 0.0,                 1.0],
    ]


def mat4_transform_point(m: List[List[float]], p: Tuple[float, float, float]) -> Tuple[float, float, float]:
    x, y, z = p[0], p[1], p[2]
    return (
        m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3],
        m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3],
        m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3],
    )


def mat4_transform_vector(m: List[List[float]], v: Tuple[float, float, float]) -> Tuple[float, float, float]:
    vx, vy, vz = v[0], v[1], v[2]
    rx = m[0][0] * vx + m[0][1] * vy + m[0][2] * vz
    ry = m[1][0] * vx + m[1][1] * vy + m[1][2] * vz
    rz = m[2][0] * vx + m[2][1] * vy + m[2][2] * vz
    l = math.sqrt(rx * rx + ry * ry + rz * rz)
    if l > 1e-6:
        return (rx / l, ry / l, rz / l)
    return (0.0, 1.0, 0.0)


# ==============================================================================
# Command Classes Supporting Both Tuple Unpacking and Attribute Access
# ==============================================================================

class BaseCommand:
    """Base class for parsed commands providing tuple-like indexing and attribute access."""
    def __init__(self, cmd_type: str, items: Tuple[Any, ...]):
        self.cmd_type = cmd_type
        self._items = (cmd_type,) + items

    def __getitem__(self, index):
        return self._items[index]

    def __len__(self):
        return len(self._items)

    def __iter__(self):
        return iter(self._items)

    def __repr__(self):
        return f"{self.__class__.__name__}{self._items}"


class TrisCommand(BaseCommand):
    """Represents a TRIS draw command with counter-clockwise faces."""
    def __init__(
        self,
        offset: int,
        count: int,
        faces: List[Tuple[int, int, int]],
        lod_index: int = 0,
        matrix: Optional[List[List[float]]] = None
    ):
        super().__init__("TRIS", (offset, count, faces, lod_index))
        self.offset = offset
        self.count = count
        self.faces = faces
        self.lod_index = lod_index
        self.matrix = matrix


class AnimBeginCommand(BaseCommand):
    def __init__(self):
        super().__init__(TOKEN_ANIM_BEGIN, ())


class AnimEndCommand(BaseCommand):
    def __init__(self):
        super().__init__(TOKEN_ANIM_END, ())


class AnimRotateCommand(BaseCommand):
    def __init__(
        self,
        ax: float, ay: float, az: float,
        angle1: float, angle2: float,
        val1: float, val2: float,
        dataref: str,
        raw_axis: Tuple[float, float, float]
    ):
        super().__init__(TOKEN_ANIM_ROTATE, (ax, ay, az, angle1, angle2, val1, val2, dataref))
        self.ax = ax
        self.ay = ay
        self.az = az
        self.axis = (ax, ay, az)
        self.angle1 = angle1
        self.angle2 = angle2
        self.val1 = val1
        self.val2 = val2
        self.dataref = dataref
        self.raw_axis = raw_axis


class AnimRotateBeginCommand(BaseCommand):
    def __init__(self, ax: float, ay: float, az: float, dataref: str, raw_axis: Tuple[float, float, float]):
        super().__init__(TOKEN_ANIM_ROTATE_BEGIN, (ax, ay, az, dataref))
        self.ax = ax
        self.ay = ay
        self.az = az
        self.axis = (ax, ay, az)
        self.dataref = dataref
        self.raw_axis = raw_axis
        self.keys: List[Tuple[float, float]] = []  # (val, angle)


class AnimRotateKeyCommand(BaseCommand):
    def __init__(self, val: float, angle: float):
        super().__init__(TOKEN_ANIM_ROTATE_KEY, (val, angle))
        self.val = val
        self.angle = angle


class AnimRotateEndCommand(BaseCommand):
    def __init__(self):
        super().__init__(TOKEN_ANIM_ROTATE_END, ())


class AnimTransCommand(BaseCommand):
    def __init__(
        self,
        p1: Tuple[float, float, float],
        p2: Tuple[float, float, float],
        val1: float, val2: float,
        dataref: str,
        raw_p1: Tuple[float, float, float],
        raw_p2: Tuple[float, float, float]
    ):
        super().__init__(TOKEN_ANIM_TRANS, (p1[0], p1[1], p1[2], p2[0], p2[1], p2[2], val1, val2, dataref))
        self.p1 = p1
        self.p2 = p2
        self.val1 = val1
        self.val2 = val2
        self.dataref = dataref
        self.raw_p1 = raw_p1
        self.raw_p2 = raw_p2


class AnimTransBeginCommand(BaseCommand):
    def __init__(self, dataref: str):
        super().__init__(TOKEN_ANIM_TRANS_BEGIN, (dataref,))
        self.dataref = dataref
        self.keys: List[Tuple[float, float, float, float]] = []  # (val, x_bl, y_bl, z_bl)
        self.raw_keys: List[Tuple[float, float, float, float]] = []  # (val, x_xp, y_xp, z_xp)


class AnimTransKeyCommand(BaseCommand):
    def __init__(self, val: float, x: float, y: float, z: float, raw_point: Tuple[float, float, float]):
        super().__init__(TOKEN_ANIM_TRANS_KEY, (val, x, y, z))
        self.val = val
        self.point = (x, y, z)
        self.raw_point = raw_point


class AnimTransEndCommand(BaseCommand):
    def __init__(self):
        super().__init__(TOKEN_ANIM_TRANS_END, ())


class AnimHideCommand(BaseCommand):
    def __init__(self, min_val: float, max_val: float, dataref: str):
        super().__init__(TOKEN_ANIM_HIDE, (min_val, max_val, dataref))
        self.min_val = min_val
        self.max_val = max_val
        self.dataref = dataref


class AnimShowCommand(BaseCommand):
    def __init__(self, min_val: float, max_val: float, dataref: str):
        super().__init__(TOKEN_ANIM_SHOW, (min_val, max_val, dataref))
        self.min_val = min_val
        self.max_val = max_val
        self.dataref = dataref


class AnimKeyframeLoopCommand(BaseCommand):
    def __init__(self, modulus: float):
        super().__init__(TOKEN_ANIM_KEYFRAME_LOOP, (modulus,))
        self.modulus = modulus


class AttrLodCommand(BaseCommand):
    def __init__(self, near: float, far: float, lod_index: int):
        super().__init__(TOKEN_ATTR_LOD, (near, far, lod_index))
        self.near = near
        self.far = far
        self.lod_index = lod_index


# ==============================================================================
# ParsedOBJ8 Data Structure
# ==============================================================================

@dataclass
class ParsedOBJ8:
    """
    Complete parsed representation of an X-Plane 12 OBJ8 asset.
    All vertices and normals are converted to Blender coordinate space (+X Right, +Y Forward, +Z Up).
    """
    name: str = "OBJ8_Model"
    filepath: str = ""
    vertices: List[Tuple[float, float, float]] = field(default_factory=list)
    normals: List[Tuple[float, float, float]] = field(default_factory=list)
    uvs: List[Tuple[float, float]] = field(default_factory=list)
    materials: Dict[str, Any] = field(default_factory=dict)
    commands: List[Any] = field(default_factory=list)
    lod_ranges: List[Tuple[float, float]] = field(default_factory=list)
    indices: List[int] = field(default_factory=list)
    raw_vertices: List[Tuple[float, float, float]] = field(default_factory=list)
    raw_normals: List[Tuple[float, float, float]] = field(default_factory=list)
    point_counts: Tuple[int, int, int, int] = (0, 0, 0, 0)
    global_properties: Dict[str, Any] = field(default_factory=dict)
    initial_matrix: Optional[List[List[float]]] = None


from .anim_rigging import (
    AnimNode,
    has_animation_commands,
    parse_animation_hierarchy,
    build_armature,
)


# ==============================================================================
# Parser Implementation
# ==============================================================================

def parse_obj8(filepath: str, initial_matrix: Optional[List[List[float]]] = None) -> ParsedOBJ8:
    """
    Parses an X-Plane 12 OBJ8 file into a structured ParsedOBJ8 instance.

    :param filepath: Path to the .obj file
    :param initial_matrix: Optional 4x4 transformation matrix to pre-seed the modelview stack
    :return: ParsedOBJ8 containing converted geometry, custom normals, UVs, and commands
    :raises ValueError: If the header is invalid or the file is malformed
    :raises FileNotFoundError: If the file does not exist
    """
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"OBJ8 file not found: {filepath}")

    base_name = os.path.splitext(os.path.basename(filepath))[0]
    parsed = ParsedOBJ8(name=base_name, filepath=os.path.abspath(filepath))
    parsed.initial_matrix = [row[:] for row in initial_matrix] if initial_matrix else None

    # Read file with utf-8, fallback to latin-1
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        with open(filepath, 'r', encoding='latin-1') as f:
            lines = f.readlines()

    # Locate and validate header lines
    # Header format: Line 1: 'I' or 'A', Line 2: '800', Line 3: 'OBJ'
    header_tokens = []
    line_idx = 0
    while line_idx < len(lines) and len(header_tokens) < 3:
        raw_line = lines[line_idx].strip()
        line_idx += 1
        if not raw_line or raw_line.startswith('#'):
            continue
        header_tokens.append(raw_line)

    if len(header_tokens) < 3 or header_tokens[0] not in ('I', 'A') or header_tokens[1] != '800' or header_tokens[2] != 'OBJ':
        raise ValueError(
            f"Invalid OBJ8 header in '{filepath}'. Expected ['I'|'A', '800', 'OBJ'], got {header_tokens}"
        )

    # Initialize materials dictionary with default configuration
    default_mat = {
        'diffuse': None,
        'lit': None,
        'normal': None,
        'draped': None,
        'normal_metalness': False,
        'specular': 1.0,
        'blend_glass': False,
        'no_shadow': False,
        'luminance': None,
    }
    parsed.materials['default'] = default_mat

    current_lod_index = 0
    init_m = [row[:] for row in initial_matrix] if initial_matrix else mat4_identity()
    matrix_stack: List[List[List[float]]] = [init_m]
    active_rotate_begin: Optional[AnimRotateBeginCommand] = None
    active_trans_begin: Optional[AnimTransBeginCommand] = None

    # Parse remaining lines
    for line_str in lines[line_idx:]:
        line_str = line_str.strip()
        if not line_str or line_str.startswith('#'):
            continue

        tokens = line_str.split()
        if not tokens:
            continue

        token = tokens[0]

        # ----------------------------------------------------------------------
        # Directives & Materials
        # ----------------------------------------------------------------------
        if token == TOKEN_TEXTURE:
            if len(tokens) > 1:
                default_mat['diffuse'] = tokens[1]
                parsed.global_properties['TEXTURE'] = tokens[1]

        elif token == TOKEN_TEXTURE_LIT:
            if len(tokens) > 1:
                default_mat['lit'] = tokens[1]
                parsed.global_properties['TEXTURE_LIT'] = tokens[1]

        elif token == TOKEN_TEXTURE_NORMAL:
            if len(tokens) > 1:
                default_mat['normal'] = tokens[1]
                parsed.global_properties['TEXTURE_NORMAL'] = tokens[1]

        elif token == TOKEN_TEXTURE_DRAPED:
            if len(tokens) > 1:
                default_mat['draped'] = tokens[1]
                parsed.global_properties['TEXTURE_DRAPED'] = tokens[1]

        elif token == TOKEN_NORMAL_METALNESS:
            default_mat['normal_metalness'] = True
            parsed.global_properties['NORMAL_METALNESS'] = True

        elif token == TOKEN_GLOBAL_SPECULAR:
            if len(tokens) > 1:
                try:
                    spec = float(tokens[1])
                    default_mat['specular'] = spec
                    parsed.global_properties['GLOBAL_specular'] = spec
                except ValueError:
                    pass

        elif token == TOKEN_BLEND_GLASS:
            default_mat['blend_glass'] = True
            parsed.global_properties['BLEND_GLASS'] = True

        elif token == TOKEN_GLOBAL_NO_SHADOW:
            default_mat['no_shadow'] = True
            parsed.global_properties['GLOBAL_no_shadow'] = True

        elif token == TOKEN_GLOBAL_LUMINANCE:
            if len(tokens) > 1:
                try:
                    lum = float(tokens[1])
                    default_mat['luminance'] = lum
                    parsed.global_properties['GLOBAL_luminance'] = lum
                except ValueError:
                    pass

        elif token == TOKEN_POINT_COUNTS:
            # POINT_COUNTS <vt> <vline> <vlight> <idx>
            if len(tokens) >= 5:
                try:
                    parsed.point_counts = (
                        int(tokens[1]),
                        int(tokens[2]),
                        int(tokens[3]),
                        int(tokens[4])
                    )
                except ValueError:
                    pass

        # ----------------------------------------------------------------------
        # Data Tables: VT and IDX
        # ----------------------------------------------------------------------
        elif token == TOKEN_VT:
            # VT <x> <y> <z> <nx> <ny> <nz> <s> <t>
            if len(tokens) >= 9:
                try:
                    x_xp, y_xp, z_xp = float(tokens[1]), float(tokens[2]), float(tokens[3])
                    nx_xp, ny_xp, nz_xp = float(tokens[4]), float(tokens[5]), float(tokens[6])
                    s, t = float(tokens[7]), float(tokens[8])

                    # Store raw coordinates
                    parsed.raw_vertices.append((x_xp, y_xp, z_xp))
                    parsed.raw_normals.append((nx_xp, ny_xp, nz_xp))

                    # Convert to Blender coordinate space (+X Right, +Y Forward, +Z Up)
                    bl_vert = xp_to_blender_point(x_xp, y_xp, z_xp)
                    bl_norm_vec = xp_to_blender_vector(nx_xp, ny_xp, nz_xp)

                    # Normalize normal vector
                    nlen = math.sqrt(bl_norm_vec[0]**2 + bl_norm_vec[1]**2 + bl_norm_vec[2]**2)
                    if nlen > 1e-6:
                        bl_norm = (bl_norm_vec[0] / nlen, bl_norm_vec[1] / nlen, bl_norm_vec[2] / nlen)
                    else:
                        bl_norm = (0.0, 0.0, 1.0)

                    parsed.vertices.append(bl_vert)
                    parsed.normals.append(bl_norm)
                    parsed.uvs.append((s, t))
                except ValueError:
                    continue

        elif token == TOKEN_IDX10 or token == TOKEN_IDX:
            try:
                for idx_str in tokens[1:]:
                    parsed.indices.append(int(idx_str))
            except ValueError:
                continue

        # ----------------------------------------------------------------------
        # Drawing & LOD Commands
        # ----------------------------------------------------------------------
        elif token == TOKEN_TRIS:
            # TRIS <offset> <count>
            if len(tokens) >= 3:
                try:
                    offset = int(tokens[1])
                    count = int(tokens[2])
                    idx_slice = parsed.indices[offset:offset + count]

                    # Convert clockwise winding (v0, v1, v2) -> counter-clockwise (v0, v2, v1)
                    faces_ccw = []
                    for i in range(0, len(idx_slice), 3):
                        if i + 2 < len(idx_slice):
                            v0 = idx_slice[i]
                            v1 = idx_slice[i + 1]
                            v2 = idx_slice[i + 2]
                            faces_ccw.append(reverse_winding_triangle(v0, v1, v2))

                    cmd = TrisCommand(
                        offset=offset,
                        count=count,
                        faces=faces_ccw,
                        lod_index=current_lod_index,
                        matrix=[row[:] for row in matrix_stack[-1]]
                    )
                    parsed.commands.append(cmd)
                except ValueError:
                    continue

        elif token == TOKEN_ATTR_LOD:
            # ATTR_LOD <near> <far>
            if len(tokens) >= 3:
                try:
                    near = float(tokens[1])
                    far = float(tokens[2])
                    current_lod_index = len(parsed.lod_ranges)
                    parsed.lod_ranges.append((near, far))
                    cmd = AttrLodCommand(near, far, current_lod_index)
                    parsed.commands.append(cmd)
                except ValueError:
                    continue

        # ----------------------------------------------------------------------
        # Animation Commands (with 3D transformation matrix stack)
        # ----------------------------------------------------------------------
        elif token == TOKEN_ANIM_BEGIN:
            matrix_stack.append([row[:] for row in matrix_stack[-1]])
            parsed.commands.append(AnimBeginCommand())

        elif token == TOKEN_ANIM_END:
            if len(matrix_stack) > 1:
                matrix_stack.pop()
            parsed.commands.append(AnimEndCommand())

        elif token == TOKEN_ANIM_ROTATE:
            # ANIM_rotate <ax> <ay> <az> <angle1> <angle2> [val1 val2 dataref]
            if len(tokens) >= 6:
                try:
                    ax_xp, ay_xp, az_xp = float(tokens[1]), float(tokens[2]), float(tokens[3])
                    angle1 = float(tokens[4])
                    angle2 = float(tokens[5]) if len(tokens) > 5 else angle1
                    val1 = float(tokens[6]) if len(tokens) > 6 else 0.0
                    val2 = float(tokens[7]) if len(tokens) > 7 else 0.0
                    dataref = tokens[8] if len(tokens) > 8 else ""

                    # Transform rotation axis to Blender space
                    bl_axis = xp_to_blender_vector(ax_xp, ay_xp, az_xp)
                    alen = math.sqrt(bl_axis[0]**2 + bl_axis[1]**2 + bl_axis[2]**2)
                    if alen > 1e-6:
                        norm_axis = (bl_axis[0] / alen, bl_axis[1] / alen, bl_axis[2] / alen)
                    else:
                        norm_axis = (0.0, 1.0, 0.0)  # Default fallback along local forward

                    cmd = AnimRotateCommand(
                        ax=norm_axis[0], ay=norm_axis[1], az=norm_axis[2],
                        angle1=angle1, angle2=angle2,
                        val1=val1, val2=val2,
                        dataref=dataref,
                        raw_axis=(ax_xp, ay_xp, az_xp)
                    )
                    parsed.commands.append(cmd)

                    # Apply rest rotation to active matrix stack (only for static transforms without dataref)
                    if not dataref or dataref.lower() in ("none", "no_ref"):
                        R = mat4_rotate(angle1, ax_xp, ay_xp, az_xp)
                        matrix_stack[-1] = mat4_mul(matrix_stack[-1], R)
                except ValueError:
                    continue

        elif token == TOKEN_ANIM_ROTATE_BEGIN:
            # ANIM_rotate_begin <ax> <ay> <az> [dataref]
            if len(tokens) >= 4:
                try:
                    ax_xp, ay_xp, az_xp = float(tokens[1]), float(tokens[2]), float(tokens[3])
                    dataref = tokens[4] if len(tokens) > 4 else ""
                    bl_axis = xp_to_blender_vector(ax_xp, ay_xp, az_xp)
                    alen = math.sqrt(bl_axis[0]**2 + bl_axis[1]**2 + bl_axis[2]**2)
                    norm_axis = (bl_axis[0]/alen, bl_axis[1]/alen, bl_axis[2]/alen) if alen > 1e-6 else (0.0, 1.0, 0.0)
                    cmd = AnimRotateBeginCommand(norm_axis[0], norm_axis[1], norm_axis[2], dataref, (ax_xp, ay_xp, az_xp))
                    active_rotate_begin = cmd
                    parsed.commands.append(cmd)
                except ValueError:
                    continue

        elif token == TOKEN_ANIM_ROTATE_KEY:
            # ANIM_rotate_key <val> <angle>
            if len(tokens) >= 3:
                try:
                    val = float(tokens[1])
                    angle = float(tokens[2])
                    cmd = AnimRotateKeyCommand(val, angle)
                    if active_rotate_begin:
                        active_rotate_begin.keys.append((val, angle))
                    parsed.commands.append(cmd)
                except ValueError:
                    continue

        elif token == TOKEN_ANIM_ROTATE_END:
            if active_rotate_begin and active_rotate_begin.keys:
                dref = active_rotate_begin.dataref
                if not dref or dref.lower() in ("none", "no_ref"):
                    rest_ang = min(active_rotate_begin.keys, key=lambda k: abs(k[0]))[1]
                    raw_ax, raw_ay, raw_az = active_rotate_begin.raw_axis
                    R = mat4_rotate(rest_ang, raw_ax, raw_ay, raw_az)
                    matrix_stack[-1] = mat4_mul(matrix_stack[-1], R)
            active_rotate_begin = None
            parsed.commands.append(AnimRotateEndCommand())

        elif token == TOKEN_ANIM_TRANS:
            # ANIM_trans <x1> <y1> <z1> <x2> <y2> <z2> [val1 val2 dataref]
            if len(tokens) >= 7:
                try:
                    x1, y1, z1 = float(tokens[1]), float(tokens[2]), float(tokens[3])
                    x2 = float(tokens[4]) if len(tokens) > 4 else x1
                    y2 = float(tokens[5]) if len(tokens) > 5 else y1
                    z2 = float(tokens[6]) if len(tokens) > 6 else z1
                    val1 = float(tokens[7]) if len(tokens) > 7 else 0.0
                    val2 = float(tokens[8]) if len(tokens) > 8 else 0.0
                    dataref = tokens[9] if len(tokens) > 9 else ""

                    p1_bl = xp_to_blender_point(x1, y1, z1)
                    p2_bl = xp_to_blender_point(x2, y2, z2)

                    cmd = AnimTransCommand(
                        p1=p1_bl, p2=p2_bl,
                        val1=val1, val2=val2,
                        dataref=dataref,
                        raw_p1=(x1, y1, z1), raw_p2=(x2, y2, z2)
                    )
                    parsed.commands.append(cmd)

                    # Apply rest translation to active matrix stack
                    T = mat4_translate(x1, y1, z1)
                    matrix_stack[-1] = mat4_mul(matrix_stack[-1], T)
                except ValueError:
                    continue

        elif token == TOKEN_ANIM_TRANS_BEGIN:
            # ANIM_trans_begin [dataref]
            dataref = tokens[1] if len(tokens) > 1 else ""
            cmd = AnimTransBeginCommand(dataref)
            active_trans_begin = cmd
            parsed.commands.append(cmd)

        elif token == TOKEN_ANIM_TRANS_KEY:
            # ANIM_trans_key <val> <x> <y> <z>
            if len(tokens) >= 5:
                try:
                    val = float(tokens[1])
                    x_xp, y_xp, z_xp = float(tokens[2]), float(tokens[3]), float(tokens[4])
                    bl_pt = xp_to_blender_point(x_xp, y_xp, z_xp)
                    cmd = AnimTransKeyCommand(val, bl_pt[0], bl_pt[1], bl_pt[2], (x_xp, y_xp, z_xp))
                    if active_trans_begin:
                        active_trans_begin.keys.append((val, bl_pt[0], bl_pt[1], bl_pt[2]))
                        active_trans_begin.raw_keys.append((val, x_xp, y_xp, z_xp))
                    parsed.commands.append(cmd)
                except ValueError:
                    continue

        elif token == TOKEN_ANIM_TRANS_END:
            if active_trans_begin and active_trans_begin.raw_keys:
                rest_k = min(active_trans_begin.raw_keys, key=lambda k: abs(k[0]))
                T = mat4_translate(rest_k[1], rest_k[2], rest_k[3])
                matrix_stack[-1] = mat4_mul(matrix_stack[-1], T)
            active_trans_begin = None
            parsed.commands.append(AnimTransEndCommand())

        elif token == TOKEN_ANIM_HIDE:
            if len(tokens) >= 4:
                try:
                    parsed.commands.append(AnimHideCommand(float(tokens[1]), float(tokens[2]), tokens[3]))
                except ValueError:
                    continue

        elif token == TOKEN_ANIM_SHOW:
            if len(tokens) >= 4:
                try:
                    parsed.commands.append(AnimShowCommand(float(tokens[1]), float(tokens[2]), tokens[3]))
                except ValueError:
                    continue

        elif token == TOKEN_ANIM_KEYFRAME_LOOP:
            if len(tokens) >= 2:
                try:
                    parsed.commands.append(AnimKeyframeLoopCommand(float(tokens[1])))
                except ValueError:
                    continue

    return parsed


# ==============================================================================
# Texture Loading & Material Construction Helpers
# ==============================================================================

def load_texture(base_filepath: str, tex_rel_name: str) -> Optional[Any]:
    """
    Safely locates and loads an image texture into Blender's bpy.data.images.
    Attempts primary path, case variations, alternate extensions (.png <-> .dds),
    and subfolders. Returns None if the image cannot be found.
    """
    if bpy is None or not tex_rel_name:
        return None

    base_dir = os.path.dirname(os.path.abspath(base_filepath)) if base_filepath else ""
    candidate_paths = [
        os.path.join(base_dir, tex_rel_name),
        os.path.join(base_dir, "objects", tex_rel_name),
        os.path.join(base_dir, "textures", tex_rel_name),
    ]

    # Add alternate extension candidate
    root, ext = os.path.splitext(tex_rel_name)
    alt_ext = ".dds" if ext.lower() == ".png" else ".png"
    alt_name = root + alt_ext
    candidate_paths.extend([
        os.path.join(base_dir, alt_name),
        os.path.join(base_dir, "objects", alt_name),
        os.path.join(base_dir, "textures", alt_name),
    ])

    for p in candidate_paths:
        norm_p = os.path.normpath(p)
        if os.path.isfile(norm_p):
            try:
                # Check if already loaded
                filename = os.path.basename(norm_p)
                if filename in bpy.data.images:
                    return bpy.data.images[filename]
                img = bpy.data.images.load(norm_p, check_existing=True)
                return img
            except Exception:
                continue

    return None


def create_material_for_obj8(
    mat_name: str,
    base_filepath: str,
    material_info: Dict[str, Any]
) -> Any:
    """
    Creates a Blender 4.3+ Material with Principled BSDF v2 and links available textures
    using create_xplane_pbr_material.
    """
    if bpy is None:
        return None

    diffuse_path = material_info.get('diffuse')
    normal_path = material_info.get('normal')
    lit_path = material_info.get('lit')
    use_procedural_normal_z = bool(material_info.get('normal_metalness', True))

    return create_xplane_pbr_material(
        mat_name=mat_name,
        texture_path=diffuse_path,
        normal_texture_path=normal_path,
        lit_texture_path=lit_path,
        use_procedural_normal_z=use_procedural_normal_z,
        base_filepath=base_filepath,
    )


# ==============================================================================
# Mesh Construction & High-Level Import API
# ==============================================================================

def build_mesh(
    parsed_data: ParsedOBJ8,
    context: Optional[Any] = None,
    name: Optional[str] = None,
    lod_level: Optional[int] = 0,
    create_armature: bool = False,
) -> Any:
    """
    Constructs a valid Blender 4.3+ Mesh Object from a ParsedOBJ8 data structure.

    - Uses me.normals_split_custom_set_from_vertices with me.polygons shaded smooth.
    - NEVER sets read-only MeshVertex.normal.
    - Avoids removed mesh.use_auto_smooth and deprecated methods.
    - Sets UV coordinates via high-performance uv_layer.data.foreach_set('uv', flat_uvs).
    - Preserves counter-clockwise face winding.

    :param parsed_data: ParsedOBJ8 instance
    :param context: Blender bpy.context (optional)
    :param name: Custom object name (defaults to parsed_data.name)
    :param lod_level: Specific LOD level to extract, or None for all TRIS
    :return: bpy.types.Object containing the constructed mesh
    """
    if bpy is None:
        raise RuntimeError("Blender 'bpy' module is required to build meshes.")

    if isinstance(context, str) and name is None:
        name, context = context, None

    mesh_name = name or parsed_data.name or "OBJ8_Mesh"
    obj_name = mesh_name

    # 1. Collect faces from TRIS commands
    faces: List[Tuple[int, int, int]] = []
    lod_commands = [cmd for cmd in parsed_data.commands if isinstance(cmd, TrisCommand)]

    if lod_level is not None and len(parsed_data.lod_ranges) > 1:
        # Filter for specific LOD level
        target_tris = [cmd for cmd in lod_commands if cmd.lod_index == lod_level]
        if not target_tris and lod_commands:
            target_tris = lod_commands  # Fallback to all if requested LOD empty
    else:
        target_tris = lod_commands

    for tris_cmd in target_tris:
        faces.extend(tris_cmd.faces)

    # 2. Transform geometry using matrix stack attached to each TRIS command
    final_verts = list(parsed_data.vertices)
    final_normals = list(parsed_data.normals)

    has_matrix_transforms = False
    if parsed_data.initial_matrix:
        has_matrix_transforms = True
        m_init = parsed_data.initial_matrix
        for i in range(len(final_verts)):
            if i < len(parsed_data.raw_vertices):
                xp_pt = mat4_transform_point(m_init, parsed_data.raw_vertices[i])
                final_verts[i] = xp_to_blender_point(xp_pt[0], xp_pt[1], xp_pt[2])
            if i < len(parsed_data.raw_normals):
                xp_norm = mat4_transform_vector(m_init, parsed_data.raw_normals[i])
                final_normals[i] = xp_to_blender_vector(xp_norm[0], xp_norm[1], xp_norm[2])

    for tris_cmd in target_tris:
        m = getattr(tris_cmd, 'matrix', None)
        if m is None:
            continue
        has_matrix_transforms = True
        for f in tris_cmd.faces:
            for v_idx in f:
                if v_idx < len(parsed_data.raw_vertices):
                    raw_pt = parsed_data.raw_vertices[v_idx]
                    xp_pt = mat4_transform_point(m, raw_pt)
                    final_verts[v_idx] = xp_to_blender_point(xp_pt[0], xp_pt[1], xp_pt[2])

                    if v_idx < len(parsed_data.raw_normals):
                        raw_norm = parsed_data.raw_normals[v_idx]
                        xp_norm = mat4_transform_vector(m, raw_norm)
                        final_normals[v_idx] = xp_to_blender_vector(xp_norm[0], xp_norm[1], xp_norm[2])

    if has_matrix_transforms:
        parsed_data.vertices = final_verts
        parsed_data.normals = final_normals

    # 3. Create mesh datablock and assign geometry
    me = bpy.data.meshes.new(name=f"{mesh_name}_Mesh")
    me.from_pydata(final_verts, [], faces)

    # 4. Smooth polygon shading (Required before custom normals in Blender 4.1+)
    if len(me.polygons) > 0:
        me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))

    # 5. Geometry validation
    me.validate(verbose=False, clean_customdata=False)

    # 6. UV coordinates via foreach_set for maximum performance
    if parsed_data.uvs and len(me.loops) > 0:
        uv_layer = me.uv_layers.new(name="UVMap")
        num_uvs = len(parsed_data.uvs)
        flat_uvs = []
        for loop in me.loops:
            v_idx = loop.vertex_index
            if v_idx < num_uvs:
                u, v = parsed_data.uvs[v_idx]
                flat_uvs.extend((u, v))
            else:
                flat_uvs.extend((0.0, 0.0))
        uv_layer.data.foreach_set("uv", flat_uvs)

    # 7. Apply custom split vertex normals
    if final_normals and len(final_normals) == len(me.vertices):
        me.normals_split_custom_set_from_vertices(final_normals)

    me.update()

    # 7. Create Object datablock
    obj = bpy.data.objects.new(obj_name, me)

    # 8. Create and link material
    mat_info = parsed_data.materials.get('default', {})
    if mat_info and (mat_info.get('diffuse') or mat_info.get('normal') or mat_info.get('lit')):
        mat = create_xplane_pbr_material(
            mat_name=f"{mesh_name}_Material",
            texture_path=mat_info.get('diffuse'),
            normal_texture_path=mat_info.get('normal'),
            lit_texture_path=mat_info.get('lit'),
            use_procedural_normal_z=bool(mat_info.get('normal_metalness', False)),
            base_filepath=parsed_data.filepath,
        )
        if mat:
            obj.data.materials.append(mat)


    # 9. Link to collection if context is active
    target_collection = None
    if context and hasattr(context, "collection") and context.collection:
        target_collection = context.collection
    elif bpy.context and hasattr(bpy.context, "scene") and bpy.context.scene:
        target_collection = bpy.context.scene.collection

    if target_collection is not None and obj.name not in target_collection.objects:
        target_collection.objects.link(obj)

    if create_armature and has_animation_commands(parsed_data):
        build_armature(parsed_data, context=context, mesh_objects=[obj])

    return obj


def import_obj8_file(
    filepath: str,
    context: Optional[Any] = None,
    collection: Optional[Any] = None,
    lod_level: Optional[int] = 0,
    create_armature: bool = True,
) -> Any:
    """
    High-level import function: parses an OBJ8 file from disk and instantiates
    its mesh object in Blender linked to the specified collection.
    When create_armature=True and animation directives exist, builds a unified
    Blender Armature and skins the mesh via vertex groups and an Armature modifier.

    :param filepath: Path to .obj file
    :param context: Blender execution context
    :param collection: Target bpy.types.Collection to link object into
    :param lod_level: Target LOD level (default 0)
    :param create_armature: Whether to construct an Armature for animated parts (default True)
    :return: Instantiated bpy.types.Object
    """
    parsed = parse_obj8(filepath)
    obj = build_mesh(parsed, context=context, name=parsed.name, lod_level=lod_level)

    if create_armature and has_animation_commands(parsed):
        arm_obj = build_armature(parsed, context=context, mesh_objects=[obj])
        target_col = collection
        if target_col is None:
            if context and hasattr(context, "collection") and context.collection:
                target_col = context.collection
            elif bpy.context and hasattr(bpy.context, "scene") and bpy.context.scene:
                target_col = bpy.context.scene.collection

        if target_col is not None and arm_obj is not None:
            if arm_obj.name not in target_col.objects:
                target_col.objects.link(arm_obj)
            if bpy.context and bpy.context.scene and target_col != bpy.context.scene.collection:
                if arm_obj.name in bpy.context.scene.collection.objects:
                    bpy.context.scene.collection.objects.unlink(arm_obj)

    if collection is not None:
        if obj.name not in collection.objects:
            collection.objects.link(obj)
        # Unlink from scene default collection if linked there previously
        if bpy.context and bpy.context.scene and collection != bpy.context.scene.collection:
            if obj.name in bpy.context.scene.collection.objects:
                bpy.context.scene.collection.objects.unlink(obj)

    return obj
