from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence
from xml.sax.saxutils import escape

import cv2
import numpy as np


MODULES_WITH_BORDER = 8

# Minimal 5x7 stroke font used for production labels.  Fusion 360 commonly
# drops DXF TEXT entities when inserting a DXF into a sketch, so these glyphs
# are emitted as ordinary LINE rectangles on the BOARD_TEXT layer.
VECTOR_GLYPHS = {
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
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
    "=": ["00000", "00000", "11111", "00000", "11111", "00000", "00000"],
}


@dataclass(frozen=True)
class Config:
    board_count: int = 20
    board_number_start: int = 1
    board_mm: float = 300.0
    tags_per_board: int = 9
    center_tag_mm: float = 128.0
    small_tag_mm: float = 44.0
    center_quiet_mm: float = 10.0
    small_quiet_mm: float = 8.0
    small_center_mm: float = 44.0
    start_id: int = 100
    hole_dia_mm: float = 5.2
    hole_x_mm: float = 96.0
    hole_y_mm: float = 44.0
    sheet_columns: int = 4
    sheet_gap_mm: float = 20.0
    dxf_preview_fills: bool = False

    @property
    def center_module_mm(self) -> float:
        return self.center_tag_mm / MODULES_WITH_BORDER

    @property
    def small_module_mm(self) -> float:
        return self.small_tag_mm / MODULES_WITH_BORDER

    @property
    def holes_mm(self) -> tuple[tuple[float, float], ...]:
        high_x = self.board_mm - self.hole_x_mm
        high_y = self.board_mm - self.hole_y_mm
        return (
            (self.hole_x_mm, self.hole_y_mm),
            (high_x, self.hole_y_mm),
            (self.hole_x_mm, high_y),
            (high_x, high_y),
        )


@dataclass(frozen=True)
class TagSpec:
    board_index: int
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

    @property
    def module_mm(self) -> float:
        return self.size_mm / MODULES_WITH_BORDER


class DxfWriter:
    """Small AutoCAD R12 ASCII writer with only widely supported entities."""

    LAYERS = (
        ("CUT", 7),
        ("MOUNT_HOLE", 6),
        ("BLACK_POCKET", 7),
        ("BOARD_TEXT", 7),
        ("ORIENTATION", 7),
        ("BLACK_FILL_PREVIEW", 8),
        ("TAG_BOUNDARY", 8),
        ("QUIET_ZONE", 5),
        ("LABEL", 3),
    )

    def __init__(self) -> None:
        self.lines: list[str] = []

    def pair(self, code: int, value: int | float | str) -> None:
        self.lines.append(str(code))
        if isinstance(value, float):
            self.lines.append(f"{value:.6f}".rstrip("0").rstrip("."))
        else:
            self.lines.append(str(value))

    def start(self) -> None:
        self.pair(0, "SECTION")
        self.pair(2, "HEADER")
        self.pair(9, "$ACADVER")
        self.pair(1, "AC1009")
        self.pair(0, "ENDSEC")
        self.pair(0, "SECTION")
        self.pair(2, "TABLES")
        self.pair(0, "TABLE")
        self.pair(2, "LAYER")
        self.pair(70, len(self.LAYERS))
        for name, color in self.LAYERS:
            self.pair(0, "LAYER")
            self.pair(2, name)
            self.pair(70, 0)
            self.pair(62, color)
            self.pair(6, "CONTINUOUS")
        self.pair(0, "ENDTAB")
        self.pair(0, "ENDSEC")
        self.pair(0, "SECTION")
        self.pair(2, "ENTITIES")

    def line(self, x1: float, y1: float, x2: float, y2: float, layer: str) -> None:
        self.pair(0, "LINE")
        self.pair(8, layer)
        self.pair(10, x1)
        self.pair(20, y1)
        self.pair(11, x2)
        self.pair(21, y2)

    def rect(self, x: float, y: float, w: float, h: float, layer: str) -> None:
        self.line(x, y, x + w, y, layer)
        self.line(x + w, y, x + w, y + h, layer)
        self.line(x + w, y + h, x, y + h, layer)
        self.line(x, y + h, x, y, layer)

    def circle(self, cx: float, cy: float, radius: float, layer: str) -> None:
        self.pair(0, "CIRCLE")
        self.pair(8, layer)
        self.pair(10, cx)
        self.pair(20, cy)
        self.pair(40, radius)

    def solid_rect(self, x: float, y: float, w: float, h: float, layer: str) -> None:
        self.pair(0, "SOLID")
        self.pair(8, layer)
        for code_x, code_y, px, py in (
            (10, 20, x, y),
            (11, 21, x + w, y),
            (12, 22, x, y + h),
            (13, 23, x + w, y + h),
        ):
            self.pair(code_x, px)
            self.pair(code_y, py)

    def text(self, x: float, y: float, value: str, height: float, layer: str, align_center: bool = False) -> None:
        self.pair(0, "TEXT")
        self.pair(8, layer)
        self.pair(10, x)
        self.pair(20, y)
        self.pair(40, height)
        self.pair(1, value)
        if align_center:
            self.pair(72, 1)
            self.pair(11, x)
            self.pair(21, y)

    def finish(self) -> str:
        self.pair(0, "ENDSEC")
        self.pair(0, "EOF")
        return "\n".join(self.lines) + "\n"


def add_vector_text_to_dxf(
    dxf: DxfWriter,
    x: float,
    y: float,
    value: str,
    height: float,
    layer: str = "BOARD_TEXT",
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
                dxf.rect(
                    x + cursor + col_index * cell,
                    y + (6 - row_index) * cell,
                    cell,
                    cell,
                    layer,
                )
        cursor += cell * 6.0


def marker_grid(dictionary: cv2.aruco.Dictionary, tag_id: int) -> np.ndarray:
    image = cv2.aruco.generateImageMarker(
        dictionary,
        tag_id,
        MODULES_WITH_BORDER,
        borderBits=1,
    )
    return image == 0


def tag_specs_for_board(board_index: int, cfg: Config) -> list[TagSpec]:
    mid = cfg.board_mm / 2.0
    low = cfg.small_center_mm
    high = cfg.board_mm - cfg.small_center_mm
    base_id = cfg.start_id + board_index * cfg.tags_per_board
    tags = [
        TagSpec(board_index, base_id, "CENTER", mid, mid, cfg.center_tag_mm, cfg.center_quiet_mm),
        TagSpec(board_index, base_id + 1, "TL", low, high, cfg.small_tag_mm, cfg.small_quiet_mm),
        TagSpec(board_index, base_id + 2, "T", mid, high, cfg.small_tag_mm, cfg.small_quiet_mm),
        TagSpec(board_index, base_id + 3, "TR", high, high, cfg.small_tag_mm, cfg.small_quiet_mm),
        TagSpec(board_index, base_id + 4, "L", low, mid, cfg.small_tag_mm, cfg.small_quiet_mm),
        TagSpec(board_index, base_id + 5, "R", high, mid, cfg.small_tag_mm, cfg.small_quiet_mm),
        TagSpec(board_index, base_id + 6, "BL", low, low, cfg.small_tag_mm, cfg.small_quiet_mm),
        TagSpec(board_index, base_id + 7, "B", mid, low, cfg.small_tag_mm, cfg.small_quiet_mm),
        TagSpec(board_index, base_id + 8, "BR", high, low, cfg.small_tag_mm, cfg.small_quiet_mm),
    ]
    return tags


def black_cell_rects(
    dictionary: cv2.aruco.Dictionary,
    tag: TagSpec,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
) -> Iterable[tuple[float, float, float, float]]:
    grid = marker_grid(dictionary, tag.tag_id)
    cell = tag.module_mm
    for row in range(MODULES_WITH_BORDER):
        for col in range(MODULES_WITH_BORDER):
            if not bool(grid[row, col]):
                continue
            x = offset_x + tag.x0 + col * cell
            # DXF uses a lower-left origin while marker rows run from the top.
            y = offset_y + tag.y0 + tag.size_mm - (row + 1) * cell
            yield x, y, cell, cell


def circle_intersects_rect(
    cx: float,
    cy: float,
    radius: float,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> bool:
    nearest_x = min(max(cx, x1), x2)
    nearest_y = min(max(cy, y1), y2)
    return math.hypot(cx - nearest_x, cy - nearest_y) <= radius


def validate_config(cfg: Config, dictionary: cv2.aruco.Dictionary) -> None:
    if cfg.board_count <= 0:
        raise ValueError("board_count must be positive")
    if cfg.board_number_start <= 0:
        raise ValueError("board_number_start must be positive")
    if cfg.tags_per_board != 9:
        raise ValueError("This layout requires exactly nine tags per board")
    if cfg.board_mm <= 0 or cfg.center_tag_mm <= 0 or cfg.small_tag_mm <= 0:
        raise ValueError("Board and tag dimensions must be positive")
    if cfg.center_quiet_mm < 0 or cfg.small_quiet_mm < 0:
        raise ValueError("Quiet-zone dimensions cannot be negative")
    max_id = int(dictionary.bytesList.shape[0]) - 1
    last_id = cfg.start_id + cfg.board_count * cfg.tags_per_board - 1
    if cfg.start_id < 0 or last_id > max_id:
        raise ValueError(f"Requested ID range {cfg.start_id}-{last_id} exceeds dictionary range 0-{max_id}")

    tags = tag_specs_for_board(0, cfg)
    for tag in tags:
        margin = tag.size_mm / 2.0 + tag.quiet_mm
        if not margin <= tag.cx <= cfg.board_mm - margin:
            raise ValueError(f"Tag {tag.name} quiet zone crosses the board X boundary")
        if not margin <= tag.cy <= cfg.board_mm - margin:
            raise ValueError(f"Tag {tag.name} quiet zone crosses the board Y boundary")
    for index, first in enumerate(tags):
        ax1, ay1 = first.x0 - first.quiet_mm, first.y0 - first.quiet_mm
        ax2 = first.x0 + first.size_mm + first.quiet_mm
        ay2 = first.y0 + first.size_mm + first.quiet_mm
        for second in tags[index + 1 :]:
            bx1, by1 = second.x0 - second.quiet_mm, second.y0 - second.quiet_mm
            bx2 = second.x0 + second.size_mm + second.quiet_mm
            by2 = second.y0 + second.size_mm + second.quiet_mm
            if min(ax2, bx2) - max(ax1, bx1) > 0 and min(ay2, by2) - max(ay1, by1) > 0:
                raise ValueError(f"Quiet zones overlap: {first.name} and {second.name}")

    radius = cfg.hole_dia_mm / 2.0
    for hx, hy in cfg.holes_mm:
        if hx - radius < 0 or hy - radius < 0 or hx + radius > cfg.board_mm or hy + radius > cfg.board_mm:
            raise ValueError(f"Mounting hole ({hx}, {hy}) crosses the board edge")
        for tag in tags:
            if circle_intersects_rect(
                hx,
                hy,
                radius,
                tag.x0 - tag.quiet_mm,
                tag.y0 - tag.quiet_mm,
                tag.x0 + tag.size_mm + tag.quiet_mm,
                tag.y0 + tag.size_mm + tag.quiet_mm,
            ):
                raise ValueError(f"Mounting hole ({hx}, {hy}) intersects {tag.name} quiet zone")


def add_board_to_dxf(
    dxf: DxfWriter,
    dictionary: cv2.aruco.Dictionary,
    board_index: int,
    cfg: Config,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    guide: bool = False,
) -> None:
    board = cfg.board_mm
    tags = tag_specs_for_board(board_index, cfg)
    dxf.rect(offset_x, offset_y, board, board, "CUT")
    for hx, hy in cfg.holes_mm:
        dxf.circle(offset_x + hx, offset_y + hy, cfg.hole_dia_mm / 2.0, "MOUNT_HOLE")

    arrow_x = offset_x + 204.0
    dxf.line(arrow_x, offset_y + board - 18.0, arrow_x, offset_y + board - 5.0, "ORIENTATION")
    dxf.line(arrow_x, offset_y + board - 5.0, arrow_x - 4.0, offset_y + board - 10.0, "ORIENTATION")
    dxf.line(arrow_x, offset_y + board - 5.0, arrow_x + 4.0, offset_y + board - 10.0, "ORIENTATION")
    add_vector_text_to_dxf(
        dxf,
        offset_x + 5.0,
        offset_y + 4.0,
        f"ID = {tags[0].tag_id}",
        4.5,
    )

    if guide:
        for tag in tags:
            dxf.rect(offset_x + tag.x0, offset_y + tag.y0, tag.size_mm, tag.size_mm, "TAG_BOUNDARY")
            dxf.rect(
                offset_x + tag.x0 - tag.quiet_mm,
                offset_y + tag.y0 - tag.quiet_mm,
                tag.size_mm + 2.0 * tag.quiet_mm,
                tag.size_mm + 2.0 * tag.quiet_mm,
                "QUIET_ZONE",
            )
            dxf.text(offset_x + tag.x0, offset_y + tag.y0 - 5.0, f"{tag.name} ID {tag.tag_id}", 3.5, "LABEL")
        dxf.text(
            offset_x + 4.0,
            offset_y - 12.0,
            f"APRILTAG 36H11 IDS {tags[0].tag_id}-{tags[-1].tag_id}",
            5.0,
            "LABEL",
        )

    for tag in tags:
        for x, y, w, h in black_cell_rects(dictionary, tag, offset_x, offset_y):
            dxf.rect(x, y, w, h, "BLACK_POCKET")
            if cfg.dxf_preview_fills:
                dxf.solid_rect(x, y, w, h, "BLACK_FILL_PREVIEW")


def write_board_dxf(
    path: Path,
    dictionary: cv2.aruco.Dictionary,
    board_index: int,
    cfg: Config,
    guide: bool,
) -> None:
    dxf = DxfWriter()
    dxf.start()
    add_board_to_dxf(dxf, dictionary, board_index, cfg, guide=guide)
    path.write_bytes(dxf.finish().encode("ascii"))


def svg_rect(x: float, y: float, w: float, h: float, **attrs: str | float) -> str:
    attr = " ".join(
        f'{key.replace("_", "-")}="{escape(str(value))}"' for key, value in attrs.items()
    )
    return f'<rect x="{x:.6f}" y="{y:.6f}" width="{w:.6f}" height="{h:.6f}" {attr}/>'


def svg_document(width: float, height: float, body: Sequence[str]) -> str:
    return "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            (
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.3f}mm" '
                f'height="{height:.3f}mm" viewBox="0 0 {width:.6f} {height:.6f}" '
                'shape-rendering="crispEdges">'
            ),
            '<desc>Reservoir AprilTag 36h11 board; all SVG units are millimeters.</desc>',
            *body,
            "</svg>",
            "",
        ]
    )


def add_board_to_svg(
    body: list[str],
    dictionary: cv2.aruco.Dictionary,
    board_index: int,
    cfg: Config,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    guide: bool = False,
) -> None:
    board = cfg.board_mm
    tags = tag_specs_for_board(board_index, cfg)
    body.append(
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

    if guide:
        for tag in tags:
            quiet_y = offset_y + board - (tag.y0 + tag.size_mm + tag.quiet_mm)
            tag_y = offset_y + board - tag.y0 - tag.size_mm
            body.append(
                svg_rect(
                    offset_x + tag.x0 - tag.quiet_mm,
                    quiet_y,
                    tag.size_mm + 2.0 * tag.quiet_mm,
                    tag.size_mm + 2.0 * tag.quiet_mm,
                    fill="none",
                    stroke="#2b6cb0",
                    stroke_width="0.4",
                    stroke_dasharray="2 1",
                )
            )
            body.append(
                svg_rect(
                    offset_x + tag.x0,
                    tag_y,
                    tag.size_mm,
                    tag.size_mm,
                    fill="none",
                    stroke="#718096",
                    stroke_width="0.3",
                )
            )
            body.append(
                f'<text x="{offset_x + tag.x0:.6f}" y="{tag_y - 1.5:.6f}" '
                f'font-family="Arial, sans-serif" font-size="3.5" fill="#2b6cb0">{tag.name} ID {tag.tag_id}</text>'
            )
        for hx, hy in cfg.holes_mm:
            # Convert the lower-left engineering convention to SVG's top-left origin.
            sy = offset_y + board - hy
            body.append(
                f'<circle cx="{offset_x + hx:.6f}" cy="{sy:.6f}" r="{cfg.hole_dia_mm / 2.0:.6f}" '
                'fill="none" stroke="#d53f8c" stroke-width="0.5"/>'
            )
            body.append(
                f'<line x1="{offset_x + hx - 4:.6f}" y1="{sy:.6f}" '
                f'x2="{offset_x + hx + 4:.6f}" y2="{sy:.6f}" stroke="#d53f8c" stroke-width="0.25"/>'
            )
            body.append(
                f'<line x1="{offset_x + hx:.6f}" y1="{sy - 4:.6f}" '
                f'x2="{offset_x + hx:.6f}" y2="{sy + 4:.6f}" stroke="#d53f8c" stroke-width="0.25"/>'
            )

    for tag in tags:
        grid = marker_grid(dictionary, tag.tag_id)
        cell = tag.module_mm
        tag_y = offset_y + board - tag.y0 - tag.size_mm
        for row in range(MODULES_WITH_BORDER):
            for col in range(MODULES_WITH_BORDER):
                if not bool(grid[row, col]):
                    continue
                x = offset_x + tag.x0 + col * cell
                y = tag_y + row * cell
                body.append(svg_rect(x, y, cell, cell, fill="#000000"))

    body.append(
        f'<text x="{offset_x + 5.0:.6f}" y="{offset_y + board - 4.0:.6f}" '
        'font-family="Arial, sans-serif" font-size="5" font-weight="700" '
        f'fill="#111111">ID = {tags[0].tag_id}</text>'
    )
    arrow_x = offset_x + 204.0
    body.append(
        f'<line x1="{arrow_x:.6f}" y1="{offset_y + 18.0:.6f}" '
        f'x2="{arrow_x:.6f}" y2="{offset_y + 5.0:.6f}" stroke="#111111" stroke-width="1.0"/>'
    )
    body.append(
        f'<polyline points="{arrow_x - 4.0:.6f},{offset_y + 10.0:.6f} '
        f'{arrow_x:.6f},{offset_y + 5.0:.6f} {arrow_x + 4.0:.6f},{offset_y + 10.0:.6f}" '
        'fill="none" stroke="#111111" stroke-width="1.0"/>'
    )
def write_board_svg(
    path: Path,
    dictionary: cv2.aruco.Dictionary,
    board_index: int,
    cfg: Config,
    guide: bool,
) -> None:
    body: list[str] = []
    add_board_to_svg(body, dictionary, board_index, cfg, guide=guide)
    path.write_text(svg_document(cfg.board_mm, cfg.board_mm, body), encoding="utf-8")


def write_sheet_svg(path: Path, dictionary: cv2.aruco.Dictionary, cfg: Config, guide: bool) -> None:
    cols = cfg.sheet_columns
    rows = math.ceil(cfg.board_count / cols)
    width = cols * cfg.board_mm + (cols - 1) * cfg.sheet_gap_mm
    height = rows * cfg.board_mm + (rows - 1) * cfg.sheet_gap_mm
    body: list[str] = []
    for board_index in range(cfg.board_count):
        row = board_index // cols
        col = board_index % cols
        offset_x = col * (cfg.board_mm + cfg.sheet_gap_mm)
        offset_y = row * (cfg.board_mm + cfg.sheet_gap_mm)
        add_board_to_svg(body, dictionary, board_index, cfg, offset_x, offset_y, guide)
    path.write_text(svg_document(width, height, body), encoding="utf-8")


def write_sheet_dxf(path: Path, dictionary: cv2.aruco.Dictionary, cfg: Config, guide: bool) -> None:
    dxf = DxfWriter()
    dxf.start()
    cols = cfg.sheet_columns
    rows = math.ceil(cfg.board_count / cols)
    for board_index in range(cfg.board_count):
        row = board_index // cols
        col = board_index % cols
        offset_x = col * (cfg.board_mm + cfg.sheet_gap_mm)
        offset_y = (rows - 1 - row) * (cfg.board_mm + cfg.sheet_gap_mm)
        add_board_to_dxf(dxf, dictionary, board_index, cfg, offset_x, offset_y, guide)
    path.write_bytes(dxf.finish().encode("ascii"))


def write_drill_template_svg(path: Path, cfg: Config) -> None:
    body = [
        svg_rect(0, 0, cfg.board_mm, cfg.board_mm, fill="#ffffff", stroke="#111111", stroke_width="0.5"),
        (
            f'<text x="{cfg.board_mm / 2.0:.6f}" y="{cfg.board_mm / 2.0:.6f}" '
            'font-family="Arial, sans-serif" font-size="9" text-anchor="middle" fill="#111111">'
            f'4 x DIA {cfg.hole_dia_mm:.1f} mm; X=96/204, Y=44/256 mm</text>'
        ),
    ]
    for hx, hy in cfg.holes_mm:
        sy = cfg.board_mm - hy
        body.append(
            f'<circle cx="{hx:.6f}" cy="{sy:.6f}" r="{cfg.hole_dia_mm / 2.0:.6f}" '
            'fill="none" stroke="#d53f8c" stroke-width="0.7"/>'
        )
        body.append(
            f'<line x1="{hx - 6:.6f}" y1="{sy:.6f}" x2="{hx + 6:.6f}" y2="{sy:.6f}" '
            'stroke="#d53f8c" stroke-width="0.3"/>'
        )
        body.append(
            f'<line x1="{hx:.6f}" y1="{sy - 6:.6f}" x2="{hx:.6f}" y2="{sy + 6:.6f}" '
            'stroke="#d53f8c" stroke-width="0.3"/>'
        )
    path.write_text(svg_document(cfg.board_mm, cfg.board_mm, body), encoding="utf-8")


def write_drill_template_dxf(path: Path, cfg: Config) -> None:
    dxf = DxfWriter()
    dxf.start()
    dxf.rect(0.0, 0.0, cfg.board_mm, cfg.board_mm, "CUT")
    for hx, hy in cfg.holes_mm:
        dxf.circle(hx, hy, cfg.hole_dia_mm / 2.0, "MOUNT_HOLE")
    dxf.text(
        cfg.board_mm / 2.0,
        cfg.board_mm / 2.0,
        f"4 X DIA {cfg.hole_dia_mm:.1f}; X=96/204, Y=44/256 MM",
        7.0,
        "LABEL",
        align_center=True,
    )
    path.write_bytes(dxf.finish().encode("ascii"))


def write_id_map(path: Path, cfg: Config) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "board_no",
                "board_label",
                "tag_family",
                "tag_id",
                "tag_position",
                "center_x_mm",
                "center_y_mm",
                "board_size_mm",
                "black_marker_size_mm",
                "module_size_mm",
                "quiet_zone_mm",
            ]
        )
        for board_index in range(cfg.board_count):
            board_number = cfg.board_number_start + board_index
            for tag in tag_specs_for_board(board_index, cfg):
                writer.writerow(
                    [
                        board_number,
                        f"R{board_number:02d}",
                        "AprilTag 36h11",
                        tag.tag_id,
                        tag.name,
                        f"{tag.cx:.1f}",
                        f"{tag.cy:.1f}",
                        f"{cfg.board_mm:.1f}",
                        f"{tag.size_mm:.1f}",
                        f"{tag.module_mm:.3f}",
                        f"{tag.quiet_mm:.1f}",
                    ]
                )


def write_deployment_template(path: Path, cfg: Config) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "board_no",
                "center_tag_id",
                "tag_id_range",
                "reservoir_zone",
                "position_x_m",
                "position_y_m",
                "position_z_m",
                "yaw_deg",
                "pitch_deg",
                "roll_deg",
                "installed_date",
                "photo_reference",
                "notes",
            ]
        )
        for board_index in range(cfg.board_count):
            board_number = cfg.board_number_start + board_index
            tags = tag_specs_for_board(board_index, cfg)
            writer.writerow(
                [
                    f"R{board_number:02d}",
                    tags[0].tag_id,
                    f"{tags[0].tag_id}-{tags[-1].tag_id}",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )


def write_manifest(path: Path, cfg: Config) -> None:
    last_id = cfg.start_id + cfg.board_count * cfg.tags_per_board - 1
    lines = [
        "Reservoir AprilTag board manufacturing manifest",
        "",
        "Tag family: AprilTag 36h11",
        f"Board count: {cfg.board_count}",
        f"Board numbers: {cfg.board_number_start}-{cfg.board_number_start + cfg.board_count - 1}",
        f"Tags per board: {cfg.tags_per_board} (one center plus eight outer tags)",
        f"ID range: {cfg.start_id}-{last_id}",
        f"Board size: {cfg.board_mm:.1f} x {cfg.board_mm:.1f} mm",
        f"Center black marker size: {cfg.center_tag_mm:.1f} x {cfg.center_tag_mm:.1f} mm",
        f"Outer black marker size: {cfg.small_tag_mm:.1f} x {cfg.small_tag_mm:.1f} mm",
        f"Marker modules: {MODULES_WITH_BORDER} x {MODULES_WITH_BORDER}",
        f"Center module / quiet zone: {cfg.center_module_mm:.3f} / {cfg.center_quiet_mm:.1f} mm",
        f"Outer module / quiet zone: {cfg.small_module_mm:.3f} / {cfg.small_quiet_mm:.1f} mm",
        f"Outer tag grid centers: {cfg.small_center_mm:.1f}, {cfg.board_mm / 2.0:.1f}, {cfg.board_mm - cfg.small_center_mm:.1f} mm",
        f"Mounting holes: 4 x diameter {cfg.hole_dia_mm:.1f} mm",
        f"Hole centers from lower-left: {', '.join(f'({x:.1f}, {y:.1f})' for x, y in cfg.holes_mm)}",
        "",
        "Print at 100% scale. Do not use fit-to-page.",
        "Keep the entire quiet zone matte white and free of fasteners, stains, text, or seams.",
        "The SVG files contain physical millimeter dimensions; DXF uses millimeters.",
        "The clean SVG is print artwork. The guide SVG is for inspection and drilling reference.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate independent 300 mm reservoir AprilTag boards.")
    parser.add_argument("--out", type=Path, default=Path("generated"))
    parser.add_argument("--board-count", type=int, default=20)
    parser.add_argument("--board-number-start", type=int, default=1)
    parser.add_argument("--board-mm", type=float, default=300.0)
    parser.add_argument("--center-tag-mm", type=float, default=128.0)
    parser.add_argument("--small-tag-mm", type=float, default=44.0)
    parser.add_argument("--center-quiet-mm", type=float, default=10.0)
    parser.add_argument("--small-quiet-mm", type=float, default=8.0)
    parser.add_argument("--small-center-mm", type=float, default=44.0)
    parser.add_argument("--start-id", type=int, default=100)
    parser.add_argument("--hole-dia-mm", type=float, default=5.2)
    parser.add_argument("--hole-x-mm", type=float, default=96.0)
    parser.add_argument("--hole-y-mm", type=float, default=44.0)
    parser.add_argument("--dxf-preview-fills", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = Config(
        board_count=args.board_count,
        board_number_start=args.board_number_start,
        board_mm=args.board_mm,
        center_tag_mm=args.center_tag_mm,
        small_tag_mm=args.small_tag_mm,
        center_quiet_mm=args.center_quiet_mm,
        small_quiet_mm=args.small_quiet_mm,
        small_center_mm=args.small_center_mm,
        start_id=args.start_id,
        hole_dia_mm=args.hole_dia_mm,
        hole_x_mm=args.hole_x_mm,
        hole_y_mm=args.hole_y_mm,
        dxf_preview_fills=args.dxf_preview_fills,
    )
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    validate_config(cfg, dictionary)
    args.out.mkdir(parents=True, exist_ok=True)

    for board_index in range(cfg.board_count):
        board_number = cfg.board_number_start + board_index
        tags = tag_specs_for_board(board_index, cfg)
        stem = f"board_{board_number:02d}_ids_{tags[0].tag_id:03d}-{tags[-1].tag_id:03d}"
        write_board_svg(args.out / f"{stem}.svg", dictionary, board_index, cfg, guide=False)
        write_board_svg(args.out / f"{stem}_guide.svg", dictionary, board_index, cfg, guide=True)
        write_board_dxf(args.out / f"{stem}.dxf", dictionary, board_index, cfg, guide=False)
        write_board_dxf(args.out / f"{stem}_guide.dxf", dictionary, board_index, cfg, guide=True)

    write_sheet_svg(args.out / "all_boards_sheet.svg", dictionary, cfg, guide=False)
    write_sheet_svg(args.out / "all_boards_sheet_guide.svg", dictionary, cfg, guide=True)
    write_sheet_dxf(args.out / "all_boards_sheet.dxf", dictionary, cfg, guide=False)
    write_sheet_dxf(args.out / "all_boards_sheet_guide.dxf", dictionary, cfg, guide=True)
    write_drill_template_svg(args.out / "board_drill_template.svg", cfg)
    write_drill_template_dxf(args.out / "board_drill_template.dxf", cfg)
    write_id_map(args.out / "id_map.csv", cfg)
    write_deployment_template(args.out / "deployment_survey_template.csv", cfg)
    write_manifest(args.out / "manifest.txt", cfg)
    print(
        f"Generated {cfg.board_count} hybrid boards with IDs "
        f"{cfg.start_id}-{cfg.start_id + cfg.board_count * cfg.tags_per_board - 1}"
    )
    print(f"Output: {args.out.resolve()}")


if __name__ == "__main__":
    main()
