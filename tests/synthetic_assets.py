"""
synthetic_assets.py - Synthetic X-Plane 12 Test Asset Generator.

Generates minimal, fully valid synthetic X-Plane 12 assets for automated testing:
- Valid OBJ8 models (geometry, custom normals, UVs, PBR directives, animations, LODs).
- Valid Plane Maker ACF aircraft projects with attached objects and spatial offsets.
- Valid 4-channel X-Plane NORMAL_METALNESS PNG textures (Red=NormX, Green=NormY, Blue=Metalness, Alpha=Roughness).
- Specialized corner-case and boundary-condition assets.

Zero external dependencies: uses Python standard library (struct, zlib, os, math).
"""

import os
import math
import zlib
import struct
from typing import List, Tuple, Dict, Any, Optional


# ==============================================================================
# Pure Python PNG Writer (Zero external dependencies)
# ==============================================================================

def write_rgba_png(filepath: str, width: int, height: int, rgba_bytes: bytes) -> str:
    """
    Writes a standard 32-bit RGBA PNG image to filepath using Python standard library.
    :param filepath: Output path (.png)
    :param width: Image width in pixels
    :param height: Image height in pixels
    :param rgba_bytes: Raw bytes of length width * height * 4
    :return: Absolute path to written file
    """
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    expected_len = width * height * 4
    if len(rgba_bytes) != expected_len:
        raise ValueError(f"rgba_bytes length {len(rgba_bytes)} does not match {width}x{height}*4={expected_len}")

    def png_chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xffffffff
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', crc)

    # IHDR: width(4), height(4), bit_depth=8(1), color_type=6(RGBA, 1), comp=0, filter=0, interlace=0
    ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    ihdr_chunk = png_chunk(b'IHDR', ihdr_data)

    # IDAT: Each scanline begins with filter byte 0x00 (None)
    row_stride = width * 4
    scanlines = bytearray()
    for y in range(height):
        scanlines.append(0)  # Filter byte None
        start = y * row_stride
        scanlines.extend(rgba_bytes[start:start + row_stride])

    compressed_idat = zlib.compress(bytes(scanlines), level=9)
    idat_chunk = png_chunk(b'IDAT', compressed_idat)

    # IEND chunk
    iend_chunk = png_chunk(b'IEND', b'')

    png_signature = b'\x89PNG\r\n\x1a\n'
    with open(filepath, 'wb') as f:
        f.write(png_signature)
        f.write(ihdr_chunk)
        f.write(idat_chunk)
        f.write(iend_chunk)

    return os.path.abspath(filepath)


def create_synthetic_normal_metalness_texture(
    filepath: str,
    width: int = 64,
    height: int = 64,
    norm_x: float = 0.5,
    norm_y: float = 0.5,
    metallic: float = 0.25,
    roughness: float = 0.75,
    quadrant_pattern: bool = False
) -> str:
    """
    Generates a 4-channel X-Plane 12 NORMAL_METALNESS PNG texture.
    - Red: Tangent Normal X (0.0..1.0 -> -1.0..+1.0)
    - Green: Tangent Normal Y (0.0..1.0 -> -1.0..+1.0)
    - Blue: Metallic factor (0.0..1.0)
    - Alpha: Roughness factor (0.0..1.0)
    If quadrant_pattern is True, includes quadrant variations for coordinate tests.
    """
    r_val = int(max(0.0, min(1.0, norm_x)) * 255.0)
    g_val = int(max(0.0, min(1.0, norm_y)) * 255.0)
    b_val = int(max(0.0, min(1.0, metallic)) * 255.0)
    a_val = int(max(0.0, min(1.0, roughness)) * 255.0)

    pixels = bytearray(width * height * 4)
    for y in range(height):
        for x in range(width):
            idx = (y * width + x) * 4
            if quadrant_pattern:
                if x < width // 2 and y < height // 2:
                    pixels[idx] = r_val
                    pixels[idx + 1] = g_val
                    pixels[idx + 2] = b_val
                    pixels[idx + 3] = a_val
                elif x >= width // 2 and y < height // 2:
                    pixels[idx] = 204
                    pixels[idx + 1] = g_val
                    pixels[idx + 2] = b_val
                    pixels[idx + 3] = a_val
                elif x < width // 2 and y >= height // 2:
                    pixels[idx] = r_val
                    pixels[idx + 1] = 204
                    pixels[idx + 2] = 255
                    pixels[idx + 3] = 64
                else:
                    pixels[idx] = 128
                    pixels[idx + 1] = 128
                    pixels[idx + 2] = 0
                    pixels[idx + 3] = 255
            else:
                pixels[idx] = r_val
                pixels[idx + 1] = g_val
                pixels[idx + 2] = b_val
                pixels[idx + 3] = a_val

    return write_rgba_png(filepath, width, height, bytes(pixels))


def create_synthetic_albedo_texture(
    filepath: str,
    width: int = 64,
    height: int = 64,
    r: int = 200,
    g: int = 210,
    b: int = 220,
    a: int = 255
) -> str:
    """Generates an albedo/diffuse texture with a subtle border for testing."""
    pixels = bytearray(width * height * 4)
    for y in range(height):
        for x in range(width):
            idx = (y * width + x) * 4
            is_border = (x == 0 or x == width - 1 or y == 0 or y == height - 1)
            if is_border:
                pixels[idx] = 50
                pixels[idx + 1] = 50
                pixels[idx + 2] = 50
                pixels[idx + 3] = 255
            else:
                pixels[idx] = r
                pixels[idx + 1] = g
                pixels[idx + 2] = b
                pixels[idx + 3] = a

    return write_rgba_png(filepath, width, height, bytes(pixels))


# ==============================================================================
# OBJ8 Syntax Builder & Factory
# ==============================================================================

class OBJ8Builder:
    """Helper class to assemble valid X-Plane OBJ8 source files."""

    def __init__(self):
        self.header_lines = ["I", "800", "OBJ"]
        self.directives: List[str] = []
        self.vertices: List[Tuple[float, float, float, float, float, float, float, float]] = []
        self.indices: List[int] = []
        self.commands: List[str] = []

    def set_textures(
        self,
        diffuse: Optional[str] = None,
        normal: Optional[str] = None,
        lit: Optional[str] = None,
        normal_metalness: bool = True,
        specular: float = 1.0
    ):
        if diffuse:
            self.directives.append(f"TEXTURE {diffuse}")
        if lit:
            self.directives.append(f"TEXTURE_LIT {lit}")
        if normal:
            self.directives.append(f"TEXTURE_NORMAL {normal}")
        if normal_metalness:
            self.directives.append("NORMAL_METALNESS")
        if specular is not None:
            self.directives.append(f"GLOBAL_specular {specular:.1f}")

    def add_directive(self, directive_line: str):
        self.directives.append(directive_line)

    def add_vertex(
        self,
        x: float, y: float, z: float,
        nx: float = 0.0, ny: float = 1.0, nz: float = 0.0,
        s: float = 0.0, t: float = 0.0
    ) -> int:
        idx = len(self.vertices)
        self.vertices.append((x, y, z, nx, ny, nz, s, t))
        return idx

    def add_indices(self, idx_list: List[int]):
        self.indices.extend(idx_list)

    def add_tris(self, offset: int, count: int):
        self.commands.append(f"TRIS {offset} {count}")

    def add_lod(self, near: float, far: float):
        self.commands.append(f"ATTR_LOD {near:.1f} {far:.1f}")

    def begin_anim(self):
        self.commands.append("ANIM_begin")

    def end_anim(self):
        self.commands.append("ANIM_end")

    def anim_rotate(
        self,
        ax: float, ay: float, az: float,
        angle1: float, angle2: float,
        val1: float, val2: float,
        dataref: str
    ):
        self.commands.append(
            f"ANIM_rotate {ax:.4f} {ay:.4f} {az:.4f} {angle1:.2f} {angle2:.2f} {val1:.4f} {val2:.4f} {dataref}"
        )

    def anim_rotate_begin(self, ax: float, ay: float, az: float, dataref: str):
        self.commands.append(f"ANIM_rotate_begin {ax:.4f} {ay:.4f} {az:.4f} {dataref}")

    def anim_rotate_key(self, val: float, angle: float):
        self.commands.append(f"ANIM_rotate_key {val:.4f} {angle:.2f}")

    def anim_rotate_end(self):
        self.commands.append("ANIM_rotate_end")

    def anim_trans(
        self,
        x1: float, y1: float, z1: float,
        x2: float, y2: float, z2: float,
        val1: float, val2: float,
        dataref: str
    ):
        self.commands.append(
            f"ANIM_trans {x1:.4f} {y1:.4f} {z1:.4f} {x2:.4f} {y2:.4f} {z2:.4f} {val1:.4f} {val2:.4f} {dataref}"
        )

    def anim_trans_begin(self, dataref: str):
        self.commands.append(f"ANIM_trans_begin {dataref}")

    def anim_trans_key(self, val: float, x: float, y: float, z: float):
        self.commands.append(f"ANIM_trans_key {val:.4f} {x:.4f} {y:.4f} {z:.4f}")

    def anim_trans_end(self):
        self.commands.append("ANIM_trans_end")

    def to_string(self) -> str:
        lines: List[str] = []
        lines.extend(self.header_lines)
        lines.extend(self.directives)

        # POINT_COUNTS <vt> <vline> <vlight> <idx>
        vt_count = len(self.vertices)
        idx_count = len(self.indices)
        lines.append(f"POINT_COUNTS {vt_count} 0 0 {idx_count}")

        # VT lines
        for v in self.vertices:
            lines.append(f"VT {v[0]:.6f} {v[1]:.6f} {v[2]:.6f} {v[3]:.6f} {v[4]:.6f} {v[5]:.6f} {v[6]:.6f} {v[7]:.6f}")

        # IDX10 lines
        for i in range(0, idx_count, 10):
            chunk = self.indices[i:i + 10]
            if len(chunk) == 10:
                indices_str = " ".join(str(idx) for idx in chunk)
                lines.append(f"IDX10 {indices_str}")
            else:
                for single_idx in chunk:
                    lines.append(f"IDX {single_idx}")

        # Command stream
        lines.extend(self.commands)
        return "\n".join(lines) + "\n"

    def write(self, filepath: str) -> str:
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        content = self.to_string()
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return os.path.abspath(filepath)


# ==============================================================================
# High-Level Synthetic Asset Constructors
# ==============================================================================

def create_minimal_obj8(
    filepath: str,
    diffuse: Optional[str] = "diffuse.png",
    normal: Optional[str] = "normal.png"
) -> str:
    """
    Creates a minimal valid OBJ8 file containing a simple textured unit cube (24 vertices, 12 triangles).
    In X-Plane coordinate system:
    - Lateral: +X (Right)
    - Vertical: +Y (Up)
    - Longitudinal: +Z (Aft/Tail)
    - Clockwise winding order in OBJ8 syntax.
    """
    builder = OBJ8Builder()
    builder.set_textures(diffuse=diffuse, normal=normal, normal_metalness=True)

    # 6 faces of a unit cube centered at (0, 0, 0)
    # Face definitions: (normal, vertices: [p0, p1, p2, p3], uvs)
    # Note: OBJ8 clockwise winding
    faces = [
        # Front face (+Z Aft)
        ((0, 0, 1), [(-0.5, -0.5, 0.5), (-0.5, 0.5, 0.5), (0.5, 0.5, 0.5), (0.5, -0.5, 0.5)]),
        # Back face (-Z Nose)
        ((0, 0, -1), [(0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5), (-0.5, -0.5, -0.5)]),
        # Top face (+Y Up)
        ((0, 1, 0), [(-0.5, 0.5, 0.5), (-0.5, 0.5, -0.5), (0.5, 0.5, -0.5), (0.5, 0.5, 0.5)]),
        # Bottom face (-Y Down)
        ((0, -1, 0), [(-0.5, -0.5, -0.5), (-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (0.5, -0.5, -0.5)]),
        # Right face (+X Starboard)
        ((1, 0, 0), [(0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (0.5, 0.5, -0.5), (0.5, -0.5, -0.5)]),
        # Left face (-X Port)
        ((-1, 0, 0), [(-0.5, -0.5, -0.5), (-0.5, 0.5, -0.5), (-0.5, 0.5, 0.5), (-0.5, -0.5, 0.5)]),
    ]

    uvs = [(0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0)]
    all_indices: List[int] = []

    for norm, quad in faces:
        base_v = len(builder.vertices)
        for i, pt in enumerate(quad):
            builder.add_vertex(pt[0], pt[1], pt[2], norm[0], norm[1], norm[2], uvs[i][0], uvs[i][1])
        # Two triangles with clockwise winding: (0, 1, 2) and (0, 2, 3)
        all_indices.extend([base_v, base_v + 1, base_v + 2, base_v, base_v + 2, base_v + 3])

    builder.add_indices(all_indices)
    builder.add_tris(0, len(all_indices))
    return builder.write(filepath)


def create_animated_aircraft_obj8(
    filepath: str,
    diffuse: Optional[str] = "diffuse.png",
    normal: Optional[str] = "normal.png"
) -> str:
    """
    Creates an OBJ8 asset with static fuselage and multi-level animated flight control surfaces:
    - Root: Fuselage geometry (TRIS)
    - ANIM 1: Aileron Left (ANIM_rotate, DataRef: sim/flightmodel2/controls/left_aileron)
    - ANIM 2: Elevator (ANIM_rotate, DataRef: sim/flightmodel2/controls/elevator)
    - ANIM 3: Rudder (ANIM_rotate, DataRef: sim/flightmodel2/controls/rudder)
    - ANIM 4: Landing Gear Deploy (ANIM_trans, DataRef: sim/flightmodel2/gear/deploy_ratio)
      - Nested ANIM 5: Steerable Wheel (ANIM_rotate, DataRef: sim/flightmodel2/gear/steer_deg)
    """
    builder = OBJ8Builder()
    builder.set_textures(diffuse=diffuse, normal=normal, normal_metalness=True)

    curr_idx_offset = 0

    # 1. Fuselage Static Geometry (Cube at origin)
    f_verts = [
        (-1.0, -0.5, -2.0), (-1.0, 0.5, -2.0), (1.0, 0.5, -2.0), (1.0, -0.5, -2.0),  # Nose
        (-1.0, -0.5, 2.0), (-1.0, 0.5, 2.0), (1.0, 0.5, 2.0), (1.0, -0.5, 2.0),      # Tail
    ]
    for v in f_verts:
        builder.add_vertex(v[0], v[1], v[2], 0.0, 1.0, 0.0, 0.5, 0.5)

    # Fuselage 12 tris (indices)
    fuselage_indices = [
        0, 1, 2, 0, 2, 3,  # Front
        4, 6, 5, 4, 7, 6,  # Back
        1, 5, 6, 1, 6, 2,  # Top
        0, 3, 7, 0, 7, 4,  # Bottom
        3, 2, 6, 3, 6, 7,  # Right
        0, 4, 5, 0, 5, 1   # Left
    ]
    builder.add_indices(fuselage_indices)
    builder.add_tris(curr_idx_offset, len(fuselage_indices))
    curr_idx_offset += len(fuselage_indices)

    # 2. Left Aileron (Rotates around X-axis: 1 0 0, from -20 to 20 deg, dataref -1.0 to 1.0)
    builder.begin_anim()
    builder.anim_rotate(
        ax=1.0, ay=0.0, az=0.0,
        angle1=-20.0, angle2=20.0,
        val1=-1.0, val2=1.0,
        dataref="sim/flightmodel2/controls/left_aileron"
    )
    # Aileron geometry (quad)
    base_v = len(builder.vertices)
    builder.add_vertex(-2.5, 0.0, 0.8, 0.0, 1.0, 0.0, 0.1, 0.1)
    builder.add_vertex(-2.5, 0.0, 1.2, 0.0, 1.0, 0.0, 0.1, 0.9)
    builder.add_vertex(-1.5, 0.0, 1.2, 0.0, 1.0, 0.0, 0.9, 0.9)
    builder.add_vertex(-1.5, 0.0, 0.8, 0.0, 1.0, 0.0, 0.9, 0.1)
    aileron_indices = [base_v, base_v + 1, base_v + 2, base_v, base_v + 2, base_v + 3]
    builder.add_indices(aileron_indices)
    builder.add_tris(curr_idx_offset, len(aileron_indices))
    curr_idx_offset += len(aileron_indices)
    builder.end_anim()

    # 3. Elevator (Rotates around X-axis: 1 0 0, from -15 to 25 deg, dataref -1.0 to 1.0)
    builder.begin_anim()
    builder.anim_rotate(
        ax=1.0, ay=0.0, az=0.0,
        angle1=-15.0, angle2=25.0,
        val1=-1.0, val2=1.0,
        dataref="sim/flightmodel2/controls/elevator"
    )
    base_v = len(builder.vertices)
    builder.add_vertex(-0.8, 0.2, 2.2, 0.0, 1.0, 0.0, 0.2, 0.2)
    builder.add_vertex(-0.8, 0.2, 2.6, 0.0, 1.0, 0.0, 0.2, 0.8)
    builder.add_vertex(0.8, 0.2, 2.6, 0.0, 1.0, 0.0, 0.8, 0.8)
    builder.add_vertex(0.8, 0.2, 2.2, 0.0, 1.0, 0.0, 0.8, 0.2)
    elev_indices = [base_v, base_v + 1, base_v + 2, base_v, base_v + 2, base_v + 3]
    builder.add_indices(elev_indices)
    builder.add_tris(curr_idx_offset, len(elev_indices))
    curr_idx_offset += len(elev_indices)
    builder.end_anim()

    # 4. Rudder (Rotates around Y-axis: 0 1 0, from -25 to 25 deg, dataref -1.0 to 1.0)
    builder.begin_anim()
    builder.anim_rotate(
        ax=0.0, ay=1.0, az=0.0,
        angle1=-25.0, angle2=25.0,
        val1=-1.0, val2=1.0,
        dataref="sim/flightmodel2/controls/rudder"
    )
    base_v = len(builder.vertices)
    builder.add_vertex(0.0, 0.5, 2.2, 1.0, 0.0, 0.0, 0.3, 0.3)
    builder.add_vertex(0.0, 1.5, 2.2, 1.0, 0.0, 0.0, 0.3, 0.7)
    builder.add_vertex(0.0, 1.5, 2.7, 1.0, 0.0, 0.0, 0.7, 0.7)
    builder.add_vertex(0.0, 0.5, 2.7, 1.0, 0.0, 0.0, 0.7, 0.3)
    rudder_indices = [base_v, base_v + 1, base_v + 2, base_v, base_v + 2, base_v + 3]
    builder.add_indices(rudder_indices)
    builder.add_tris(curr_idx_offset, len(rudder_indices))
    curr_idx_offset += len(rudder_indices)
    builder.end_anim()

    # 5. Landing Gear Deploy (Translation along Y: 0 to -1.2m)
    #    with nested Steerable Wheel (Rotation around Y: -30 to 30 deg)
    builder.begin_anim()
    builder.anim_trans(
        x1=0.0, y1=0.0, z1=-1.0,
        x2=0.0, y2=-1.2, z2=-1.0,
        val1=0.0, val2=1.0,
        dataref="sim/flightmodel2/gear/deploy_ratio"
    )
    # Gear strut
    base_v = len(builder.vertices)
    builder.add_vertex(-0.1, 0.0, -1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    builder.add_vertex(-0.1, -1.0, -1.0, 0.0, 0.0, 1.0, 0.0, 1.0)
    builder.add_vertex(0.1, -1.0, -1.0, 0.0, 0.0, 1.0, 1.0, 1.0)
    builder.add_vertex(0.1, 0.0, -1.0, 0.0, 0.0, 1.0, 1.0, 0.0)
    strut_indices = [base_v, base_v + 1, base_v + 2, base_v, base_v + 2, base_v + 3]
    builder.add_indices(strut_indices)
    builder.add_tris(curr_idx_offset, len(strut_indices))
    curr_idx_offset += len(strut_indices)

    # Nested wheel steer
    builder.begin_anim()
    builder.anim_rotate(
        ax=0.0, ay=1.0, az=0.0,
        angle1=-30.0, angle2=30.0,
        val1=-1.0, val2=1.0,
        dataref="sim/flightmodel2/gear/steer_deg"
    )
    base_v = len(builder.vertices)
    builder.add_vertex(-0.2, -1.2, -1.2, 1.0, 0.0, 0.0, 0.4, 0.4)
    builder.add_vertex(-0.2, -1.0, -1.2, 1.0, 0.0, 0.0, 0.4, 0.6)
    builder.add_vertex(-0.2, -1.0, -0.8, 1.0, 0.0, 0.0, 0.6, 0.6)
    builder.add_vertex(-0.2, -1.2, -0.8, 1.0, 0.0, 0.0, 0.6, 0.4)
    wheel_indices = [base_v, base_v + 1, base_v + 2, base_v, base_v + 2, base_v + 3]
    builder.add_indices(wheel_indices)
    builder.add_tris(curr_idx_offset, len(wheel_indices))
    curr_idx_offset += len(wheel_indices)

    builder.end_anim()  # End steer wheel
    builder.end_anim()  # End gear deploy

    return builder.write(filepath)


def create_lod_obj8(filepath: str, diffuse: Optional[str] = "diffuse.png") -> str:
    """Creates an OBJ8 file containing multiple ATTR_LOD levels (LOD 0 and LOD 1)."""
    builder = OBJ8Builder()
    builder.set_textures(diffuse=diffuse, normal_metalness=False)

    # LOD 0: Detailed mesh (distance 0 to 500 meters)
    builder.add_lod(0.0, 500.0)
    v0 = builder.add_vertex(-1.0, 0.0, -1.0, 0, 1, 0, 0, 0)
    v1 = builder.add_vertex(-1.0, 0.0, 1.0, 0, 1, 0, 0, 1)
    v2 = builder.add_vertex(1.0, 0.0, 1.0, 0, 1, 0, 1, 1)
    v3 = builder.add_vertex(1.0, 0.0, -1.0, 0, 1, 0, 1, 0)
    v4 = builder.add_vertex(0.0, 1.0, 0.0, 0, 1, 0, 0.5, 0.5)  # Pyramid peak
    # 4 triangles
    lod0_indices = [
        v0, v1, v4,
        v1, v2, v4,
        v2, v3, v4,
        v3, v0, v4
    ]
    builder.add_indices(lod0_indices)
    builder.add_tris(0, len(lod0_indices))

    # LOD 1: Low-detail mesh (distance 500 to 2500 meters)
    builder.add_lod(500.0, 2500.0)
    u0 = builder.add_vertex(-1.0, 0.0, -1.0, 0, 1, 0, 0, 0)
    u1 = builder.add_vertex(-1.0, 0.0, 1.0, 0, 1, 0, 0, 1)
    u2 = builder.add_vertex(1.0, 0.0, 1.0, 0, 1, 0, 1, 1)
    lod1_indices = [u0, u1, u2]
    builder.add_indices(lod1_indices)
    builder.add_tris(len(lod0_indices), len(lod1_indices))

    return builder.write(filepath)


def create_corner_case_obj8(filepath: str, case_type: str) -> str:
    """
    Creates specialized corner-case OBJ8 files to verify parser robustness:
    - 'empty_lines': Extraneous blank lines, whitespace, tabs, and comments.
    - 'zero_bone_length': ANIM_rotate with rotation axis (0, 0, 0) and zero translation.
    - 'degenerate_tris': Triangles with duplicated vertex indices.
    - 'boundary_dataref': Extreme floats (-1e6 to +1e6, identical key values).
    - 'deep_nesting': 6 levels of hierarchical animation blocks.
    - 'missing_textures': References non-existent image paths.
    """
    builder = OBJ8Builder()

    if case_type == 'empty_lines':
        # Add blank lines, comments, and tabs
        builder.add_directive("# X-Plane 12 Synthetic Test Model")
        builder.add_directive("")
        builder.add_directive("   # Leading whitespace comment")
        builder.add_directive("TEXTURE  test_diffuse.png   ")
        builder.add_directive("\tNORMAL_METALNESS\t")
        builder.add_directive("")
        v0 = builder.add_vertex(0, 0, 0, 0, 1, 0, 0, 0)
        v1 = builder.add_vertex(0, 0, 1, 0, 1, 0, 0, 1)
        v2 = builder.add_vertex(1, 0, 0, 0, 1, 0, 1, 0)
        builder.add_indices([v0, v1, v2])
        builder.commands.append("   # Pre-draw comment")
        builder.commands.append("")
        builder.commands.append("TRIS 0 3")
        builder.commands.append("")

    elif case_type == 'zero_bone_length':
        builder.set_textures("diffuse.png")
        builder.begin_anim()
        # Axis length == 0.0 (must not trigger EditBone silent deletion in Blender)
        builder.anim_rotate(
            ax=0.0, ay=0.0, az=0.0,
            angle1=0.0, angle2=0.0,
            val1=0.0, val2=1.0,
            dataref="sim/custom/zero_axis"
        )
        v0 = builder.add_vertex(0, 0, 0)
        v1 = builder.add_vertex(0, 1, 0)
        v2 = builder.add_vertex(1, 0, 0)
        builder.add_indices([v0, v1, v2])
        builder.add_tris(0, 3)
        builder.end_anim()

    elif case_type == 'degenerate_tris':
        builder.set_textures("diffuse.png")
        v0 = builder.add_vertex(0, 0, 0)
        v1 = builder.add_vertex(1, 1, 1)
        # Degenerate indices: [v0, v0, v1] and [v1, v1, v1]
        builder.add_indices([v0, v0, v1, v1, v1, v1])
        builder.add_tris(0, 6)

    elif case_type == 'boundary_dataref':
        builder.set_textures("diffuse.png")
        builder.begin_anim()
        # Large floating point thresholds
        builder.anim_rotate(
            ax=0.0, ay=1.0, az=0.0,
            angle1=-180.0, angle2=180.0,
            val1=-1000000.0, val2=1000000.0,
            dataref="sim/custom/extreme_range"
        )
        v0 = builder.add_vertex(0, 0, 0)
        v1 = builder.add_vertex(0, 0, 1)
        v2 = builder.add_vertex(1, 0, 0)
        builder.add_indices([v0, v1, v2])
        builder.add_tris(0, 3)
        builder.end_anim()

    elif case_type == 'deep_nesting':
        builder.set_textures("diffuse.png")
        depth = 6
        for d in range(depth):
            builder.begin_anim()
            builder.anim_rotate(
                ax=1.0, ay=0.0, az=0.0,
                angle1=-10.0 * (d + 1), angle2=10.0 * (d + 1),
                val1=-1.0, val2=1.0,
                dataref=f"sim/custom/nest_level_{d}"
            )
            v0 = builder.add_vertex(d * 0.5, 0, 0)
            v1 = builder.add_vertex(d * 0.5, 1, 0)
            v2 = builder.add_vertex(d * 0.5 + 0.5, 0, 0)
            builder.add_indices([v0, v1, v2])
            builder.add_tris(d * 3, 3)

        for _ in range(depth):
            builder.end_anim()

    elif case_type == 'missing_textures':
        # Directives reference files guaranteed not to exist
        builder.set_textures(
            diffuse="non_existent_albedo_404.png",
            normal="non_existent_normal_404.png",
            lit="non_existent_lit_404.png",
            normal_metalness=True
        )
        v0 = builder.add_vertex(0, 0, 0)
        v1 = builder.add_vertex(0, 1, 0)
        v2 = builder.add_vertex(1, 0, 0)
        builder.add_indices([v0, v1, v2])
        builder.add_tris(0, 3)

    else:
        raise ValueError(f"Unknown corner case type: {case_type}")

    return builder.write(filepath)


# ==============================================================================
# Plane Maker ACF Aircraft Project Generator
# ==============================================================================

def create_synthetic_acf(
    filepath: str,
    tailnum: str = "N172SP",
    aircraft_name: str = "Synthetic Skyhawk",
    icao: str = "C172",
    attached_objects: Optional[List[Dict[str, Any]]] = None
) -> str:
    """
    Generates a synthetic Plane Maker ACF (Version 1200) definition file.
    :param filepath: Path to save the .acf file
    :param tailnum: Registration tail number
    :param aircraft_name: Display aircraft name
    :param icao: ICAO type designator
    :param attached_objects: List of dicts specifying attached objects:
           [
             {
               'path': 'objects/fuselage.obj',
               'xyz': (0.0, 0.0, 0.0),
               'is_cockpit': 0,
               'lighting': 0
             },
             ...
           ]
    """
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    lines = [
        "I",
        "1200 Version",
        "ACF",
        f"P acf/_tailnum {tailnum}",
        f"P acf/_name {aircraft_name}",
        f"P acf/_ICAO {icao}",
        "P acf/_pe_xyz/0 -0.250000",
        "P acf/_pe_xyz/1 0.350000",
        "P acf/_pe_xyz/2 -0.800000",
    ]

    if attached_objects:
        for idx, obj_entry in enumerate(attached_objects):
            obj_path = obj_entry.get('path', f'objects/part_{idx}.obj')
            xyz = obj_entry.get('xyz', (0.0, 0.0, 0.0))
            is_cockpit = 1 if obj_entry.get('is_cockpit', False) else 0
            lighting = obj_entry.get('lighting', 0)

            lines.append(f"P acf/_misc_obj_name/{idx} {obj_path}")
            lines.append(f"P acf/_misc_obj_xyz/{idx}/0 {xyz[0]:.6f}")
            lines.append(f"P acf/_misc_obj_xyz/{idx}/1 {xyz[1]:.6f}")
            lines.append(f"P acf/_misc_obj_xyz/{idx}/2 {xyz[2]:.6f}")
            lines.append(f"P acf/_misc_obj_is_cockpit/{idx} {is_cockpit}")
            lines.append(f"P acf/_misc_obj_lighting/{idx} {lighting}")

    content = "\n".join(lines) + "\n"
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    return os.path.abspath(filepath)


def create_full_synthetic_aircraft_project(base_dir: str) -> Dict[str, str]:
    """
    Assembles a complete, self-contained synthetic X-Plane 12 aircraft project:
    <base_dir>/
    ├── aircraft.acf
    └── objects/
        ├── exterior_paint.png
        ├── exterior_NML.png
        ├── cockpit_paint.png
        ├── cockpit_NML.png
        ├── fuselage.obj       (Exterior root)
        ├── wings.obj          (Exterior with animated ailerons)
        ├── cockpit_inn.obj    (Cockpit interior with instrument panel)
        └── landing_gear.obj   (Exterior with animated gear deployment and steering)

    :return: Dict of generated file paths
    """
    os.makedirs(base_dir, exist_ok=True)
    obj_dir = os.path.join(base_dir, "objects")
    os.makedirs(obj_dir, exist_ok=True)

    # 1. Textures
    ext_paint = os.path.join(obj_dir, "exterior_paint.png")
    ext_norm = os.path.join(obj_dir, "exterior_NML.png")
    cockpit_paint = os.path.join(obj_dir, "cockpit_paint.png")
    cockpit_norm = os.path.join(obj_dir, "cockpit_NML.png")

    create_synthetic_albedo_texture(ext_paint, 64, 64, r=220, g=220, b=225)
    create_synthetic_normal_metalness_texture(ext_norm, 64, 64, norm_x=0.5, norm_y=0.5, metallic=0.2, roughness=0.6)
    create_synthetic_albedo_texture(cockpit_paint, 64, 64, r=50, g=55, b=60)
    create_synthetic_normal_metalness_texture(cockpit_norm, 64, 64, norm_x=0.5, norm_y=0.5, metallic=0.05, roughness=0.85)

    # 2. OBJ8 Models
    fuselage_path = os.path.join(obj_dir, "fuselage.obj")
    wings_path = os.path.join(obj_dir, "wings.obj")
    cockpit_path = os.path.join(obj_dir, "cockpit_inn.obj")
    gear_path = os.path.join(obj_dir, "landing_gear.obj")

    # Fuselage (Static)
    create_minimal_obj8(fuselage_path, diffuse="exterior_paint.png", normal="exterior_NML.png")

    # Wings (Animated ailerons)
    wb = OBJ8Builder()
    wb.set_textures(diffuse="exterior_paint.png", normal="exterior_NML.png", normal_metalness=True)
    # Wing root
    w0 = wb.add_vertex(-4.0, 0.2, -0.5, 0, 1, 0, 0, 0)
    w1 = wb.add_vertex(-4.0, 0.2, 0.5, 0, 1, 0, 0, 1)
    w2 = wb.add_vertex(4.0, 0.2, 0.5, 0, 1, 0, 1, 1)
    w3 = wb.add_vertex(4.0, 0.2, -0.5, 0, 1, 0, 1, 0)
    wb.add_indices([w0, w1, w2, w0, w2, w3])
    wb.add_tris(0, 6)

    # Animated Aileron
    wb.begin_anim()
    wb.anim_rotate(1.0, 0.0, 0.0, -20.0, 20.0, -1.0, 1.0, "sim/flightmodel2/controls/left_aileron")
    a0 = wb.add_vertex(-3.8, 0.2, 0.5, 0, 1, 0, 0.1, 0.1)
    a1 = wb.add_vertex(-3.8, 0.2, 0.8, 0, 1, 0, 0.1, 0.9)
    a2 = wb.add_vertex(-2.0, 0.2, 0.8, 0, 1, 0, 0.9, 0.9)
    a3 = wb.add_vertex(-2.0, 0.2, 0.5, 0, 1, 0, 0.9, 0.1)
    wb.add_indices([a0, a1, a2, a0, a2, a3])
    wb.add_tris(6, 6)
    wb.end_anim()
    wb.write(wings_path)

    # Cockpit (Interior panel)
    cb = OBJ8Builder()
    cb.set_textures(diffuse="cockpit_paint.png", normal="cockpit_NML.png", normal_metalness=True)
    c0 = cb.add_vertex(-0.6, 0.8, -0.8, 0, 0, 1, 0, 0)
    c1 = cb.add_vertex(-0.6, 1.4, -0.8, 0, 0, 1, 0, 1)
    c2 = cb.add_vertex(0.6, 1.4, -0.8, 0, 0, 1, 1, 1)
    c3 = cb.add_vertex(0.6, 0.8, -0.8, 0, 0, 1, 1, 0)
    cb.add_indices([c0, c1, c2, c0, c2, c3])
    cb.add_tris(0, 6)
    cb.write(cockpit_path)

    # Landing gear (deploy + wheel steer)
    create_animated_aircraft_obj8(gear_path, diffuse="exterior_paint.png", normal="exterior_NML.png")

    # 3. Aircraft Definition (.acf)
    acf_path = os.path.join(base_dir, "aircraft.acf")
    attached = [
        {'path': 'objects/fuselage.obj', 'xyz': (0.0, 0.0, 0.0), 'is_cockpit': 0, 'lighting': 0},
        {'path': 'objects/wings.obj', 'xyz': (0.0, 0.5, 0.2), 'is_cockpit': 0, 'lighting': 0},
        {'path': 'objects/cockpit_inn.obj', 'xyz': (0.0, 0.4, -0.8), 'is_cockpit': 1, 'lighting': 1},
        {'path': 'objects/landing_gear.obj', 'xyz': (0.0, -0.8, -0.5), 'is_cockpit': 0, 'lighting': 0},
    ]
    create_synthetic_acf(
        filepath=acf_path,
        tailnum="N432XP",
        aircraft_name="Synthetic E2E Aeroplane",
        icao="SYNE",
        attached_objects=attached
    )

    return {
        'base_dir': os.path.abspath(base_dir),
        'acf_path': os.path.abspath(acf_path),
        'fuselage_obj': os.path.abspath(fuselage_path),
        'wings_obj': os.path.abspath(wings_path),
        'cockpit_obj': os.path.abspath(cockpit_path),
        'gear_obj': os.path.abspath(gear_path),
        'exterior_paint': os.path.abspath(ext_paint),
        'exterior_norm': os.path.abspath(ext_norm),
        'cockpit_paint': os.path.abspath(cockpit_paint),
        'cockpit_norm': os.path.abspath(cockpit_norm),
    }


if __name__ == '__main__':
    import tempfile
    test_dir = tempfile.mkdtemp(prefix="xp_synthetic_test_")
    print("Generating test synthetic project in:", test_dir)
    res = create_full_synthetic_aircraft_project(test_dir)
    for k, v in res.items():
        print(f"  {k}: {v} (exists={os.path.exists(v)})")
