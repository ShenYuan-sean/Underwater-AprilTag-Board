from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence
from xml.sax.saxutils import escape

import cv2
import numpy as np


MODULES_WITH_BORDER = 8

VECTOR_GLYPHS = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01111", "10000", "10000", "10111", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "J": ["00111", "00010", "00010", "00010", "10010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "10000", "11110", "00001", "00001", "11110"],
    "6": ["01110", "10000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    "/": ["00001", "00010", "00010", "00100", "01000", "01000", "10000"],
    ".": ["00000", "00000", "00000", "00000", "00000", "01100", "01100"],
    ":": ["00000", "01100", "01100", "00000", "01100", "01100", "00000"],
}


@dataclass(frozen=True)
class Config:
    board_mm: float = 150.0
    face_count: int = 6
    tags_per_face: int = 9
    center_tag_mm: float = 64.0
    small_tag_mm: float = 22.0
    center_quiet_mm: float = 5.0
    small_quiet_mm: float = 4.0
    small_center_mm: float = 22.0
    start_id: int = 0
    sheet_gap_mm: float = 20.0
    dxf_preview_fills: bool = False
    mount_hole_dia_mm: float = 3.4
    mount_holes_mm: tuple[tuple[float, float], ...] = (
        (48.0, 22.0),
        (102.0, 22.0),
        (48.0, 128.0),
        (102.0, 128.0),
    )


@dataclass(frozen=True)
class TagSpec:
    face_index: int
    tag_id: int
    name: str
    cx: float
    cy: float
    size_mm: float
    quiet_mm: float

    @property
    def x0(self) -> float:
        return self.cx - self.size_mm / 2.0

    @property
    def y0(self) -> float:
        return self.cy - self.size_mm / 2.0


class DxfWriter:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def _pair(self, code: int | str, value: int | float | str) -> None:
        self.lines.append(str(code))
        if isinstance(value, float):
            self.lines.append(f"{value:.6f}".rstrip("0").rstrip("."))
        else:
            self.lines.append(str(value))

    def start(self) -> None:
        self._pair(0, "SECTION")
        self._pair(2, "HEADER")
        self._pair(9, "$ACADVER")
        self._pair(1, "AC1009")
        self._pair(0, "ENDSEC")
        self._pair(0, "SECTION")
        self._pair(2, "TABLES")
        self._pair(0, "TABLE")
        self._pair(2, "LTYPE")
        self._pair(70, 1)
        self._pair(0, "LTYPE")
        self._pair(2, "CONTINUOUS")
        self._pair(70, 0)
        self._pair(3, "Solid line")
        self._pair(72, 65)
        self._pair(73, 0)
        self._pair(40, 0.0)
        self._pair(0, "ENDTAB")
        self._pair(0, "TABLE")
        self._pair(2, "LAYER")
        layers = [
            ("CUT", 1),
            ("MOUNT_HOLE", 5),
            ("BLACK_POCKET", 7),
            ("BLACK_FILL_PREVIEW", 250),
            ("BOARD_TEXT", 2),
            ("ORIENTATION", 1),
            ("TAG_BOUNDARY", 8),
            ("QUIET_ZONE", 4),
            ("LABEL", 3),
            ("FIXTURE", 5),
            ("PANEL_SLOT", 2),
            ("CENTERLINE", 6),
        ]
        self._pair(70, len(layers))
        for name, color in layers:
            self._pair(0, "LAYER")
            self._pair(2, name)
            self._pair(70, 0)
            self._pair(62, color)
            self._pair(6, "CONTINUOUS")
        self._pair(0, "ENDTAB")
        self._pair(0, "ENDSEC")
        self._pair(0, "SECTION")
        self._pair(2, "ENTITIES")

    def finish(self) -> str:
        self._pair(0, "ENDSEC")
        self._pair(0, "EOF")
        return "\r\n".join(self.lines) + "\r\n"

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        layer: str,
    ) -> None:
        self._pair(0, "LINE")
        self._pair(8, layer)
        self._pair(10, x1)
        self._pair(20, y1)
        self._pair(11, x2)
        self._pair(21, y2)

    def rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        layer: str,
    ) -> None:
        self.line(x, y, x + w, y, layer)
        self.line(x + w, y, x + w, y + h, layer)
        self.line(x + w, y + h, x, y + h, layer)
        self.line(x, y + h, x, y, layer)

    def polyline_as_lines(
        self,
        points: Sequence[tuple[float, float]],
        layer: str,
        closed: bool = False,
    ) -> None:
        if len(points) < 2:
            return
        for start, end in zip(points, points[1:]):
            self.line(start[0], start[1], end[0], end[1], layer)
        if closed:
            first = points[0]
            last = points[-1]
            self.line(last[0], last[1], first[0], first[1], layer)

    def circle_as_lines(
        self,
        cx: float,
        cy: float,
        radius: float,
        layer: str,
        segments: int = 48,
    ) -> None:
        points = [
            (
                cx + radius * math.cos(2.0 * math.pi * index / segments),
                cy + radius * math.sin(2.0 * math.pi * index / segments),
            )
            for index in range(segments)
        ]
        self.polyline_as_lines(points, layer, closed=True)

    def solid_rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        layer: str,
    ) -> None:
        self._pair(0, "SOLID")
        self._pair(8, layer)
        self._pair(10, x)
        self._pair(20, y)
        self._pair(11, x + w)
        self._pair(21, y)
        self._pair(12, x)
        self._pair(22, y + h)
        self._pair(13, x + w)
        self._pair(23, y + h)

    def text(
        self,
        x: float,
        y: float,
        value: str,
        height: float = 4.0,
        layer: str = "LABEL",
        rotation_deg: float = 0.0,
    ) -> None:
        self._pair(0, "TEXT")
        self._pair(8, layer)
        self._pair(10, x)
        self._pair(20, y)
        self._pair(40, height)
        self._pair(1, value)
        self._pair(50, rotation_deg)


def write_dxf_file(path: Path, dxf: DxfWriter) -> None:
    path.write_bytes(dxf.finish().encode("ascii"))


def rotate_point(
    px: float,
    py: float,
    ox: float,
    oy: float,
    rotation_deg: float,
) -> tuple[float, float]:
    if rotation_deg == 0:
        return px, py
    angle = math.radians(rotation_deg)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    dx = px - ox
    dy = py - oy
    return ox + dx * cos_a - dy * sin_a, oy + dx * sin_a + dy * cos_a


def add_vector_text_to_dxf(
    dxf: DxfWriter,
    x: float,
    y: float,
    value: str,
    height: float,
    layer: str,
    rotation_deg: float = 0.0,
) -> None:
    cell = height / 7.0
    cursor = 0.0
    for char in value.upper():
        if char == " ":
            cursor += cell * 3.0
            continue
        glyph = VECTOR_GLYPHS.get(char)
        if glyph is None:
            cursor += cell * 6.0
            continue
        for row_index, row in enumerate(glyph):
            for col_index, enabled in enumerate(row):
                if enabled != "1":
                    continue
                x0 = x + cursor + col_index * cell
                y0 = y + (6 - row_index) * cell
                points = [
                    rotate_point(x0, y0, x, y, rotation_deg),
                    rotate_point(x0 + cell, y0, x, y, rotation_deg),
                    rotate_point(x0 + cell, y0 + cell, x, y, rotation_deg),
                    rotate_point(x0, y0 + cell, x, y, rotation_deg),
                ]
                dxf.polyline_as_lines(points, layer, closed=True)
        cursor += cell * 6.0


def marker_grid(dictionary: cv2.aruco.Dictionary, tag_id: int) -> np.ndarray:
    image = cv2.aruco.generateImageMarker(
        dictionary,
        tag_id,
        MODULES_WITH_BORDER,
        borderBits=1,
    )
    return image == 0


def tag_specs_for_face(face_index: int, cfg: Config) -> list[TagSpec]:
    board = cfg.board_mm
    low = cfg.small_center_mm
    mid = board / 2.0
    high = board - cfg.small_center_mm
    base_id = cfg.start_id + face_index * cfg.tags_per_face
    specs = [
        TagSpec(
            face_index=face_index,
            tag_id=base_id,
            name="CENTER",
            cx=mid,
            cy=mid,
            size_mm=cfg.center_tag_mm,
            quiet_mm=cfg.center_quiet_mm,
        )
    ]
    small_slots = [
        ("TL", low, high),
        ("T", mid, high),
        ("TR", high, high),
        ("L", low, mid),
        ("R", high, mid),
        ("BL", low, low),
        ("B", mid, low),
        ("BR", high, low),
    ]
    for offset, (name, cx, cy) in enumerate(small_slots, start=1):
        specs.append(
            TagSpec(
                face_index=face_index,
                tag_id=base_id + offset,
                name=name,
                cx=cx,
                cy=cy,
                size_mm=cfg.small_tag_mm,
                quiet_mm=cfg.small_quiet_mm,
            )
        )
    return specs


def all_tag_specs(cfg: Config) -> list[TagSpec]:
    specs: list[TagSpec] = []
    for face_index in range(cfg.face_count):
        specs.extend(tag_specs_for_face(face_index, cfg))
    return specs


def validate_layout(cfg: Config, dictionary: cv2.aruco.Dictionary) -> None:
    max_id = int(dictionary.bytesList.shape[0]) - 1
    requested_ids = [tag.tag_id for tag in all_tag_specs(cfg)]
    if max(requested_ids) > max_id:
        raise ValueError(f"Requested tag ID {max(requested_ids)} exceeds dictionary max {max_id}")
    if len(requested_ids) != len(set(requested_ids)):
        raise ValueError("Tag IDs are not unique")
    for face_index in range(cfg.face_count):
        tags = tag_specs_for_face(face_index, cfg)
        for tag in tags:
            margin = tag.size_mm / 2.0 + tag.quiet_mm
            if tag.cx < margin or tag.cx > cfg.board_mm - margin:
                raise ValueError(f"Tag {tag.tag_id} quiet zone exceeds board X boundary")
            if tag.cy < margin or tag.cy > cfg.board_mm - margin:
                raise ValueError(f"Tag {tag.tag_id} quiet zone exceeds board Y boundary")
        for i, a in enumerate(tags):
            for b in tags[i + 1 :]:
                ax1 = a.x0 - a.quiet_mm
                ay1 = a.y0 - a.quiet_mm
                ax2 = a.x0 + a.size_mm + a.quiet_mm
                ay2 = a.y0 + a.size_mm + a.quiet_mm
                bx1 = b.x0 - b.quiet_mm
                by1 = b.y0 - b.quiet_mm
                bx2 = b.x0 + b.size_mm + b.quiet_mm
                by2 = b.y0 + b.size_mm + b.quiet_mm
                overlap_x = min(ax2, bx2) - max(ax1, bx1)
                overlap_y = min(ay2, by2) - max(ay1, by1)
                if overlap_x > 0 and overlap_y > 0:
                    raise ValueError(
                        f"Quiet zones overlap on face {face_index + 1}: "
                        f"ID {a.tag_id} and ID {b.tag_id}"
                    )


def black_cell_rects(
    dictionary: cv2.aruco.Dictionary,
    tag: TagSpec,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
) -> Iterable[tuple[float, float, float, float]]:
    grid = marker_grid(dictionary, tag.tag_id)
    cell = tag.size_mm / MODULES_WITH_BORDER
    for row in range(MODULES_WITH_BORDER):
        for col in range(MODULES_WITH_BORDER):
            if not bool(grid[row, col]):
                continue
            x = offset_x + tag.x0 + col * cell
            y = offset_y + tag.y0 + tag.size_mm - (row + 1) * cell
            yield (x, y, cell, cell)


def face_id_range(tags: Sequence[TagSpec]) -> tuple[int, int]:
    return tags[0].tag_id, tags[-1].tag_id


def adjacent_face_labels(face_index: int, cfg: Config) -> tuple[int, int]:
    left_face = (face_index - 1) % cfg.face_count + 1
    right_face = (face_index + 1) % cfg.face_count + 1
    return left_face, right_face


def add_orientation_to_dxf(
    dxf: DxfWriter,
    tags: Sequence[TagSpec],
    cfg: Config,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
) -> None:
    board = cfg.board_mm
    face_no = tags[0].face_index + 1
    first_id, last_id = face_id_range(tags)
    left_face, right_face = adjacent_face_labels(tags[0].face_index, cfg)

    add_vector_text_to_dxf(dxf, offset_x + 6, offset_y + board - 5.0, f"TOP / FACE {face_no:02d}", 3.2, "BOARD_TEXT")
    add_vector_text_to_dxf(dxf, offset_x + 105, offset_y + board - 5.0, "OUTSIDE VIEW", 3.2, "BOARD_TEXT")
    add_vector_text_to_dxf(dxf, offset_x + 6, offset_y + 2.2, f"IDS {first_id:03d}-{last_id:03d}", 3.2, "BOARD_TEXT")
    add_vector_text_to_dxf(dxf, offset_x + 84, offset_y + 2.2, f"CENTER ID {first_id:03d}", 3.2, "BOARD_TEXT")
    add_vector_text_to_dxf(dxf, offset_x + 3.0, offset_y + 43, f"LEFT F{left_face:02d}", 2.8, "BOARD_TEXT", rotation_deg=90)
    add_vector_text_to_dxf(dxf, offset_x + board - 3.0, offset_y + 43, f"RIGHT F{right_face:02d}", 2.8, "BOARD_TEXT", rotation_deg=90)

    arrow_x = offset_x + board / 2.0
    dxf.line(arrow_x, offset_y + board - 6.0, arrow_x, offset_y + board - 1.4, "ORIENTATION")
    dxf.line(arrow_x, offset_y + board - 1.4, arrow_x - 2.4, offset_y + board - 3.8, "ORIENTATION")
    dxf.line(arrow_x, offset_y + board - 1.4, arrow_x + 2.4, offset_y + board - 3.8, "ORIENTATION")


def add_mounting_holes_to_dxf(
    dxf: DxfWriter,
    cfg: Config,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
) -> None:
    radius = cfg.mount_hole_dia_mm / 2.0
    for hx, hy in cfg.mount_holes_mm:
        dxf.circle_as_lines(offset_x + hx, offset_y + hy, radius, "MOUNT_HOLE")


def add_board_to_dxf(
    dxf: DxfWriter,
    dictionary: cv2.aruco.Dictionary,
    tags: Sequence[TagSpec],
    cfg: Config,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    include_guides: bool = True,
) -> None:
    board = cfg.board_mm
    dxf.rect(offset_x, offset_y, board, board, "CUT")
    add_mounting_holes_to_dxf(dxf, cfg, offset_x, offset_y)
    add_orientation_to_dxf(dxf, tags, cfg, offset_x, offset_y)
    if include_guides:
        face_no = tags[0].face_index + 1
        dxf.text(offset_x + 4, offset_y + board + 4, f"FACE {face_no}", height=5)
        dxf.text(
            offset_x + 4,
            offset_y - 8,
            f"IDs {tags[0].tag_id:03d}-{tags[-1].tag_id:03d}",
            height=4,
        )
    for tag in tags:
        if include_guides:
            dxf.rect(
                offset_x + tag.x0,
                offset_y + tag.y0,
                tag.size_mm,
                tag.size_mm,
                "TAG_BOUNDARY",
            )
            dxf.rect(
                offset_x + tag.x0 - tag.quiet_mm,
                offset_y + tag.y0 - tag.quiet_mm,
                tag.size_mm + 2 * tag.quiet_mm,
                tag.size_mm + 2 * tag.quiet_mm,
                "QUIET_ZONE",
            )
            dxf.text(
                offset_x + tag.x0,
                offset_y + tag.y0 - 3.5,
                f"{tag.tag_id}",
                height=3.0,
            )
        for x, y, w, h in black_cell_rects(dictionary, tag, offset_x, offset_y):
            dxf.rect(x, y, w, h, "BLACK_POCKET")
            if cfg.dxf_preview_fills:
                dxf.solid_rect(x, y, w, h, "BLACK_FILL_PREVIEW")


def write_face_dxf(
    path: Path,
    dictionary: cv2.aruco.Dictionary,
    tags: Sequence[TagSpec],
    cfg: Config,
    include_guides: bool = False,
) -> None:
    dxf = DxfWriter()
    dxf.start()
    add_board_to_dxf(dxf, dictionary, tags, cfg, include_guides=include_guides)
    write_dxf_file(path, dxf)


def write_sheet_dxf(
    path: Path,
    dictionary: cv2.aruco.Dictionary,
    cfg: Config,
    include_guides: bool = False,
) -> None:
    dxf = DxfWriter()
    dxf.start()
    cols = 3
    for face_index in range(cfg.face_count):
        row = face_index // cols
        col = face_index % cols
        offset_x = col * (cfg.board_mm + cfg.sheet_gap_mm)
        offset_y = (1 - row) * (cfg.board_mm + cfg.sheet_gap_mm)
        tags = tag_specs_for_face(face_index, cfg)
        add_board_to_dxf(dxf, dictionary, tags, cfg, offset_x, offset_y, include_guides=include_guides)
    write_dxf_file(path, dxf)


def svg_rect(x: float, y: float, w: float, h: float, **attrs: str) -> str:
    attr = " ".join(f'{key.replace("_", "-")}="{escape(str(value))}"' for key, value in attrs.items())
    return f'<rect x="{x:.6f}" y="{y:.6f}" width="{w:.6f}" height="{h:.6f}" {attr}/>'


def dxf_y_to_svg_y(board_mm: float, y: float, h: float) -> float:
    return board_mm - y - h


def svg_text(
    x: float,
    y: float,
    value: str,
    font_size: float = 3.2,
    fill: str = "#111111",
    rotate_deg: float | None = None,
) -> str:
    transform = ""
    if rotate_deg is not None:
        transform = f' transform="rotate({rotate_deg:.6f} {x:.6f} {y:.6f})"'
    return (
        f'<text x="{x:.6f}" y="{y:.6f}" font-size="{font_size:.3f}" '
        f'font-family="Arial" fill="{fill}"{transform}>{escape(value)}</text>'
    )


def add_orientation_to_svg(
    lines: list[str],
    tags: Sequence[TagSpec],
    cfg: Config,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
) -> None:
    board = cfg.board_mm
    face_no = tags[0].face_index + 1
    first_id, last_id = face_id_range(tags)
    left_face, right_face = adjacent_face_labels(tags[0].face_index, cfg)

    lines.append(svg_text(offset_x + 6, offset_y + 5.2, f"TOP / FACE {face_no:02d}", 3.2))
    lines.append(svg_text(offset_x + 105, offset_y + 5.2, "OUTSIDE VIEW", 3.2))
    lines.append(svg_text(offset_x + 6, offset_y + board - 2.2, f"IDs {first_id:03d}-{last_id:03d}", 3.2))
    lines.append(svg_text(offset_x + 84, offset_y + board - 2.2, f"CENTER ID {first_id:03d}", 3.2))
    lines.append(svg_text(offset_x + 3.8, offset_y + 108, f"LEFT F{left_face:02d}", 2.8, rotate_deg=-90))
    lines.append(svg_text(offset_x + board - 3.8, offset_y + 42, f"RIGHT F{right_face:02d}", 2.8, rotate_deg=90))

    arrow_x = offset_x + board / 2.0
    lines.append(
        f'<line x1="{arrow_x:.6f}" y1="{offset_y + 6.0:.6f}" '
        f'x2="{arrow_x:.6f}" y2="{offset_y + 1.4:.6f}" '
        'stroke="#111111" stroke-width="0.35"/>'
    )
    lines.append(
        f'<polyline points="{arrow_x - 2.4:.6f},{offset_y + 3.8:.6f} '
        f'{arrow_x:.6f},{offset_y + 1.4:.6f} {arrow_x + 2.4:.6f},{offset_y + 3.8:.6f}" '
        'fill="none" stroke="#111111" stroke-width="0.35"/>'
    )


def add_board_to_svg(
    lines: list[str],
    dictionary: cv2.aruco.Dictionary,
    tags: Sequence[TagSpec],
    cfg: Config,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    guide: bool = False,
) -> None:
    board = cfg.board_mm
    lines.append(
        svg_rect(
            offset_x,
            offset_y,
            board,
            board,
            fill="#ffffff",
            stroke="#111111",
            stroke_width="0.25",
        )
    )
    add_orientation_to_svg(lines, tags, cfg, offset_x, offset_y)
    for tag in tags:
        if guide:
            qx = offset_x + tag.x0 - tag.quiet_mm
            qy = offset_y + dxf_y_to_svg_y(board, tag.y0 + tag.size_mm + tag.quiet_mm, 0)
            lines.append(
                svg_rect(
                    qx,
                    qy,
                    tag.size_mm + 2 * tag.quiet_mm,
                    tag.size_mm + 2 * tag.quiet_mm,
                    fill="none",
                    stroke="#2b6cb0",
                    stroke_width="0.18",
                    opacity="0.7",
                )
            )
            bx = offset_x + tag.x0
            by = offset_y + dxf_y_to_svg_y(board, tag.y0, tag.size_mm)
            lines.append(
                svg_rect(
                    bx,
                    by,
                    tag.size_mm,
                    tag.size_mm,
                    fill="none",
                    stroke="#718096",
                    stroke_width="0.18",
                )
            )
            label_y = by - 1.8 if by > 5 else by + tag.size_mm + 4
            lines.append(
                f'<text x="{bx:.6f}" y="{label_y:.6f}" '
                f'font-size="3.2" font-family="Arial" fill="#2f855a">'
                f'ID {tag.tag_id}</text>'
            )
        for x, y, w, h in black_cell_rects(dictionary, tag):
            sx = offset_x + x
            sy = offset_y + dxf_y_to_svg_y(board, y, h)
            lines.append(svg_rect(sx, sy, w, h, fill="#000000"))
    if guide:
        face_no = tags[0].face_index + 1
        lines.append(
            f'<text x="{offset_x + 4:.6f}" y="{offset_y + board - 4:.6f}" '
            f'font-size="4.2" font-family="Arial" fill="#2d3748">'
            f'FACE {face_no} / IDs {tags[0].tag_id:03d}-{tags[-1].tag_id:03d}</text>'
        )


def svg_document(width: float, height: float, body: Sequence[str]) -> str:
    return "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            (
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.3f}mm" '
                f'height="{height:.3f}mm" viewBox="0 0 {width:.6f} {height:.6f}" '
                'shape-rendering="crispEdges">'
            ),
            "<desc>AprilTag 36h11 calibration boards, units in millimeters.</desc>",
            *body,
            "</svg>",
            "",
        ]
    )


def write_face_svg(
    path: Path,
    dictionary: cv2.aruco.Dictionary,
    tags: Sequence[TagSpec],
    cfg: Config,
    guide: bool,
) -> None:
    body: list[str] = []
    add_board_to_svg(body, dictionary, tags, cfg, guide=guide)
    path.write_text(svg_document(cfg.board_mm, cfg.board_mm, body), encoding="utf-8")


def write_sheet_svg(
    path: Path,
    dictionary: cv2.aruco.Dictionary,
    cfg: Config,
    guide: bool,
) -> None:
    cols = 3
    rows = math.ceil(cfg.face_count / cols)
    width = cols * cfg.board_mm + (cols - 1) * cfg.sheet_gap_mm
    height = rows * cfg.board_mm + (rows - 1) * cfg.sheet_gap_mm
    body: list[str] = []
    for face_index in range(cfg.face_count):
        row = face_index // cols
        col = face_index % cols
        offset_x = col * (cfg.board_mm + cfg.sheet_gap_mm)
        offset_y = row * (cfg.board_mm + cfg.sheet_gap_mm)
        tags = tag_specs_for_face(face_index, cfg)
        add_board_to_svg(body, dictionary, tags, cfg, offset_x, offset_y, guide=guide)
    path.write_text(svg_document(width, height, body), encoding="utf-8")


def regular_polygon(radius: float, count: int, start_deg: float = 0.0) -> list[tuple[float, float]]:
    points = []
    for index in range(count):
        angle = math.radians(start_deg + 360.0 * index / count)
        points.append((radius * math.cos(angle), radius * math.sin(angle)))
    return points


def offset_points(points: Iterable[tuple[float, float]], ox: float, oy: float) -> list[tuple[float, float]]:
    return [(x + ox, y + oy) for x, y in points]


def slot_rect_for_segment(
    p1: tuple[float, float],
    p2: tuple[float, float],
    thickness: float,
) -> list[tuple[float, float]]:
    x1, y1 = p1
    x2, y2 = p2
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    nx = -dy / length * thickness / 2.0
    ny = dx / length * thickness / 2.0
    return [(x1 + nx, y1 + ny), (x2 + nx, y2 + ny), (x2 - nx, y2 - ny), (x1 - nx, y1 - ny)]


def write_fixture_dxf(path: Path, cfg: Config, slot_thickness_mm: float = 3.2) -> None:
    side = cfg.board_mm
    vertices = regular_polygon(side, 6, start_deg=0.0)
    dxf = DxfWriter()
    dxf.start()
    dxf.polyline_as_lines(vertices, "FIXTURE", closed=True)
    hub = regular_polygon(45.0 / math.cos(math.radians(30)), 6, start_deg=30.0)
    dxf.polyline_as_lines(hub, "CENTERLINE", closed=True)
    for index in range(6):
        p1 = vertices[index]
        p2 = vertices[(index + 1) % 6]
        slot = slot_rect_for_segment(p1, p2, slot_thickness_mm)
        dxf.polyline_as_lines(slot, "PANEL_SLOT", closed=True)
        mx = (p1[0] + p2[0]) / 2.0
        my = (p1[1] + p2[1]) / 2.0
        dxf.line(0.0, 0.0, mx, my, "CENTERLINE")
        dxf.text(mx * 1.05, my * 1.05, f"FACE {index + 1}", height=5.0)
    dxf.text(-58, -8, "Top-view fixture concept: 150 mm sides, 60 deg face spacing", height=4.0)
    dxf.text(-42, -16, f"Panel slot guide thickness: {slot_thickness_mm:.1f} mm", height=4.0)
    write_dxf_file(path, dxf)


def write_fixture_svg(path: Path, cfg: Config, slot_thickness_mm: float = 3.2) -> None:
    side = cfg.board_mm
    vertices = regular_polygon(side, 6, start_deg=0.0)
    slots = [
        slot_rect_for_segment(vertices[index], vertices[(index + 1) % 6], slot_thickness_mm)
        for index in range(6)
    ]
    all_points = vertices + [point for slot in slots for point in slot]
    min_x = min(x for x, _ in all_points) - 25
    max_x = max(x for x, _ in all_points) + 25
    min_y = min(y for _, y in all_points) - 25
    max_y = max(y for _, y in all_points) + 25
    width = max_x - min_x
    height = max_y - min_y

    def to_svg(point: tuple[float, float]) -> tuple[float, float]:
        x, y = point
        return x - min_x, max_y - y

    def polygon(points: Sequence[tuple[float, float]], **attrs: str) -> str:
        coords = " ".join(f"{x:.6f},{y:.6f}" for x, y in [to_svg(point) for point in points])
        attr = " ".join(f'{key.replace("_", "-")}="{escape(str(value))}"' for key, value in attrs.items())
        return f'<polygon points="{coords}" {attr}/>'

    body = [
        polygon(vertices, fill="none", stroke="#111111", stroke_width="0.6"),
    ]
    for slot in slots:
        body.append(polygon(slot, fill="none", stroke="#d53f8c", stroke_width="0.35"))
    for index in range(6):
        p1 = vertices[index]
        p2 = vertices[(index + 1) % 6]
        mx = (p1[0] + p2[0]) / 2.0
        my = (p1[1] + p2[1]) / 2.0
        sx, sy = to_svg((mx, my))
        cx, cy = to_svg((0.0, 0.0))
        body.append(
            f'<line x1="{cx:.6f}" y1="{cy:.6f}" x2="{sx:.6f}" y2="{sy:.6f}" '
            'stroke="#718096" stroke-width="0.25"/>'
        )
        body.append(
            f'<text x="{sx:.6f}" y="{sy:.6f}" font-size="5" font-family="Arial" '
            f'fill="#2d3748">FACE {index + 1}</text>'
        )
    body.append(
        f'<text x="10" y="{height - 12:.6f}" font-size="4.5" font-family="Arial" fill="#2d3748">'
        "Top-view fixture concept: 150 mm sides, 60 deg face spacing</text>"
    )
    path.write_text(svg_document(width, height, body), encoding="utf-8")


def write_manifest(path: Path, cfg: Config) -> None:
    lines = [
        "AprilTag 36h11 hex calibration board manifest",
        "",
        f"Board size: {cfg.board_mm:.1f} mm x {cfg.board_mm:.1f} mm",
        f"Faces: {cfg.face_count}",
        f"Tags per face: {cfg.tags_per_face}",
        f"Center tag black-marker size: {cfg.center_tag_mm:.1f} mm",
        f"Small tag black-marker size: {cfg.small_tag_mm:.1f} mm",
        f"Mounting hole diameter: {cfg.mount_hole_dia_mm:.1f} mm",
        "Mounting hole centers: "
        + ", ".join(f"({x:.1f}, {y:.1f})" for x, y in cfg.mount_holes_mm)
        + " from board lower-left",
        "",
        "ID allocation:",
    ]
    for face_index in range(cfg.face_count):
        tags = tag_specs_for_face(face_index, cfg)
        lines.append(
            f"  Face {face_index + 1}: center ID {tags[0].tag_id:03d}; "
            f"small IDs {tags[1].tag_id:03d}-{tags[-1].tag_id:03d}"
        )
    lines.extend(
        [
            "",
            "Generated DXF layers:",
            "  CUT: 150 mm board outline",
            "  MOUNT_HOLE: four line-drawn mounting holes",
            "  BLACK_POCKET: black module outlines for CNC/laser pocketing",
            "  BOARD_TEXT: line-drawn face, ID, and side-direction text",
            "  ORIENTATION: top-edge direction arrow",
            "  BLACK_FILL_PREVIEW: optional filled rectangles for CAD preview",
            "  TAG_BOUNDARY: marker outer edge guides, only in *_guide.dxf",
            "  QUIET_ZONE: recommended white quiet-zone guides, only in *_guide.dxf",
            "  LABEL: extra face and ID labels, only in *_guide.dxf",
            "",
            "Note: tag sizes above mean the black marker square generated by OpenCV.",
            "The surrounding quiet zone should remain white and unmarked.",
            "Clean DXF files are written as AutoCAD R12 ASCII; board text is drawn with LINE entities.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate AprilTag 36h11 board SVG/DXF files.")
    parser.add_argument("--out", type=Path, default=Path("generated"), help="Output directory.")
    parser.add_argument("--board-mm", type=float, default=150.0)
    parser.add_argument("--center-tag-mm", type=float, default=64.0)
    parser.add_argument("--small-tag-mm", type=float, default=22.0)
    parser.add_argument("--start-id", type=int, default=0)
    parser.add_argument("--mount-hole-dia-mm", type=float, default=3.4)
    parser.add_argument("--dxf-preview-fills", action="store_true")
    parser.add_argument("--no-dxf-preview-fills", action="store_false", dest="dxf_preview_fills")
    parser.set_defaults(dxf_preview_fills=False)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = Config(
        board_mm=args.board_mm,
        center_tag_mm=args.center_tag_mm,
        small_tag_mm=args.small_tag_mm,
        start_id=args.start_id,
        dxf_preview_fills=args.dxf_preview_fills,
        mount_hole_dia_mm=args.mount_hole_dia_mm,
    )
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    validate_layout(cfg, dictionary)
    args.out.mkdir(parents=True, exist_ok=True)

    for face_index in range(cfg.face_count):
        tags = tag_specs_for_face(face_index, cfg)
        face_no = face_index + 1
        write_face_svg(args.out / f"face_{face_no:02d}.svg", dictionary, tags, cfg, guide=False)
        write_face_svg(args.out / f"face_{face_no:02d}_guide.svg", dictionary, tags, cfg, guide=True)
        write_face_dxf(args.out / f"face_{face_no:02d}.dxf", dictionary, tags, cfg, include_guides=False)
        write_face_dxf(args.out / f"face_{face_no:02d}_guide.dxf", dictionary, tags, cfg, include_guides=True)

    write_sheet_svg(args.out / "all_faces_sheet.svg", dictionary, cfg, guide=False)
    write_sheet_svg(args.out / "all_faces_sheet_guide.svg", dictionary, cfg, guide=True)
    write_sheet_dxf(args.out / "all_faces_sheet.dxf", dictionary, cfg, include_guides=False)
    write_sheet_dxf(args.out / "all_faces_sheet_guide.dxf", dictionary, cfg, include_guides=True)
    write_fixture_dxf(args.out / "hex_fixture_top_view.dxf", cfg)
    write_fixture_svg(args.out / "hex_fixture_top_view.svg", cfg)
    write_manifest(args.out / "manifest.txt", cfg)
    print(f"Wrote AprilTag 36h11 board files to: {args.out.resolve()}")


if __name__ == "__main__":
    main()
