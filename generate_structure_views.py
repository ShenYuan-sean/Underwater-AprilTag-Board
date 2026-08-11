from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence
from xml.sax.saxutils import escape


@dataclass(frozen=True)
class StructureConfig:
    board_mm: float = 150.0
    board_thickness_mm: float = 3.0
    slot_clearance_mm: float = 0.3
    ring_half_width_mm: float = 25.0
    ring_thickness_mm: float = 8.0
    backing_strip_width_mm: float = 12.0
    backing_strip_thickness_mm: float = 5.0
    hole_dia_mm: float = 3.4
    hole_x_mm: tuple[float, float] = (48.0, 102.0)
    hole_y_mm: tuple[float, float] = (22.0, 128.0)

    @property
    def slot_width_mm(self) -> float:
        return self.board_thickness_mm + self.slot_clearance_mm


class Svg:
    def __init__(self, width: float, height: float) -> None:
        self.width = width
        self.height = height
        self.body: list[str] = []

    def line(self, x1: float, y1: float, x2: float, y2: float, **attrs: str | float) -> None:
        self.body.append(tag("line", x1=x1, y1=y1, x2=x2, y2=y2, **attrs))

    def rect(self, x: float, y: float, w: float, h: float, **attrs: str | float) -> None:
        self.body.append(tag("rect", x=x, y=y, width=w, height=h, **attrs))

    def circle(self, cx: float, cy: float, r: float, **attrs: str | float) -> None:
        self.body.append(tag("circle", cx=cx, cy=cy, r=r, **attrs))

    def polyline(self, points: Sequence[tuple[float, float]], **attrs: str | float) -> None:
        self.body.append(tag("polyline", points=point_string(points), **attrs))

    def polygon(self, points: Sequence[tuple[float, float]], **attrs: str | float) -> None:
        self.body.append(tag("polygon", points=point_string(points), **attrs))

    def text(self, x: float, y: float, value: str, size: float = 4.0, **attrs: str | float) -> None:
        default = {"font_family": "Arial", "font_size": size, "fill": "#111111"}
        default.update(attrs)
        self.body.append(tag("text", escape(value), x=x, y=y, **default))

    def title(self, value: str) -> None:
        self.text(12, 14, value, size=6.0, font_weight="700")

    def save(self, path: Path) -> None:
        path.write_text(
            "\n".join(
                [
                    '<?xml version="1.0" encoding="UTF-8"?>',
                    (
                        f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width:.1f}mm" '
                        f'height="{self.height:.1f}mm" viewBox="0 0 {self.width:.3f} {self.height:.3f}">'
                    ),
                    '<rect x="0" y="0" width="100%" height="100%" fill="#ffffff"/>',
                    '<style>text{dominant-baseline:auto}.dim{fill:#555}.note{fill:#444}</style>',
                    *self.body,
                    "</svg>",
                    "",
                ]
            ),
            encoding="utf-8",
        )


def tag(name: str, content: str = "", **attrs: str | float) -> str:
    attr = " ".join(
        f'{svg_attr_name(key)}="{escape(format_attr(value))}"' for key, value in attrs.items()
    )
    if content:
        return f"<{name} {attr}>{content}</{name}>"
    return f"<{name} {attr}/>"


def svg_attr_name(key: str) -> str:
    if key.endswith("_"):
        return key[:-1]
    return key.replace("_", "-")


def format_attr(value: str | float) -> str:
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def point_string(points: Sequence[tuple[float, float]]) -> str:
    return " ".join(f"{x:.4f},{y:.4f}" for x, y in points)


def regular_hex(side: float, start_deg: float = 0.0) -> list[tuple[float, float]]:
    return [
        (
            side * math.cos(math.radians(start_deg + index * 60.0)),
            side * math.sin(math.radians(start_deg + index * 60.0)),
        )
        for index in range(6)
    ]


def translate(points: Iterable[tuple[float, float]], ox: float, oy: float) -> list[tuple[float, float]]:
    return [(x + ox, y + oy) for x, y in points]


def to_svg_xy(points: Iterable[tuple[float, float]], ox: float, oy: float) -> list[tuple[float, float]]:
    return [(ox + x, oy - y) for x, y in points]


def offset_segment_rect(
    p1: tuple[float, float],
    p2: tuple[float, float],
    width: float,
) -> list[tuple[float, float]]:
    x1, y1 = p1
    x2, y2 = p2
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    nx = -dy / length * width / 2.0
    ny = dx / length * width / 2.0
    return [(x1 + nx, y1 + ny), (x2 + nx, y2 + ny), (x2 - nx, y2 - ny), (x1 - nx, y1 - ny)]


def view_label(svg: Svg, x: float, y: float, label: str) -> None:
    svg.text(x, y, label, size=4.2, font_weight="700")
    svg.line(x, y + 2, x + 52, y + 2, stroke="#111111", stroke_width=0.35)


def dim_h(svg: Svg, x1: float, x2: float, y: float, label: str) -> None:
    svg.line(x1, y, x2, y, stroke="#666666", stroke_width=0.25)
    svg.line(x1, y - 2, x1, y + 2, stroke="#666666", stroke_width=0.25)
    svg.line(x2, y - 2, x2, y + 2, stroke="#666666", stroke_width=0.25)
    svg.text((x1 + x2) / 2 - len(label) * 1.2, y - 2.5, label, size=3.2, class_="dim")


def dim_v(svg: Svg, x: float, y1: float, y2: float, label: str) -> None:
    svg.line(x, y1, x, y2, stroke="#666666", stroke_width=0.25)
    svg.line(x - 2, y1, x + 2, y1, stroke="#666666", stroke_width=0.25)
    svg.line(x - 2, y2, x + 2, y2, stroke="#666666", stroke_width=0.25)
    svg.text(x + 2.5, (y1 + y2) / 2, label, size=3.2, class_="dim")


def draw_board_front(svg: Svg, cfg: StructureConfig, x: float, y: float, show_keepouts: bool) -> None:
    b = cfg.board_mm
    svg.rect(x, y, b, b, fill="none", stroke="#111111", stroke_width=0.45)
    for hx in cfg.hole_x_mm:
        for hy in cfg.hole_y_mm:
            svg.circle(x + hx, y + b - hy, cfg.hole_dia_mm / 2.0, fill="none", stroke="#d53f8c", stroke_width=0.55)
            svg.line(x + hx - 2.8, y + b - hy, x + hx + 2.8, y + b - hy, stroke="#d53f8c", stroke_width=0.25)
            svg.line(x + hx, y + b - hy - 2.8, x + hx, y + b - hy + 2.8, stroke="#d53f8c", stroke_width=0.25)
    if show_keepouts:
        keepouts = [
            (38, 38, 74, 74, "CENTER TAG KEEP OUT"),
            (7, 7, 30, 30, ""),
            (60, 7, 30, 30, ""),
            (113, 7, 30, 30, ""),
            (7, 60, 30, 30, ""),
            (113, 60, 30, 30, ""),
            (7, 113, 30, 30, ""),
            (60, 113, 30, 30, ""),
            (113, 113, 30, 30, ""),
        ]
        for kx, ky, kw, kh, label in keepouts:
            svg.rect(x + kx, y + b - ky - kh, kw, kh, fill="#f7fafc", stroke="#90cdf4", stroke_width=0.25, stroke_dasharray="2 1")
            if label:
                svg.text(x + kx + 4, y + b - ky - kh / 2, label, size=3.0, fill="#2b6cb0")


def draw_hex_ring_top(svg: Svg, cfg: StructureConfig, cx: float, cy: float) -> None:
    apothem = cfg.board_mm * math.sqrt(3.0) / 2.0
    outer_side = (apothem + cfg.ring_half_width_mm) / math.cos(math.radians(30))
    inner_side = (apothem - cfg.ring_half_width_mm) / math.cos(math.radians(30))
    panel_side = cfg.board_mm
    outer = to_svg_xy(regular_hex(outer_side), cx, cy)
    inner = to_svg_xy(regular_hex(inner_side), cx, cy)
    panels = regular_hex(panel_side)
    svg.polygon(outer, fill="#f8fafc", stroke="#111111", stroke_width=0.55)
    svg.polygon(inner, fill="#ffffff", stroke="#111111", stroke_width=0.55)
    for index in range(6):
        p1 = panels[index]
        p2 = panels[(index + 1) % 6]
        slot = to_svg_xy(offset_segment_rect(p1, p2, cfg.slot_width_mm), cx, cy)
        svg.polygon(slot, fill="#fff5f7", stroke="#d53f8c", stroke_width=0.35)
        mx = (p1[0] + p2[0]) / 2.0
        my = (p1[1] + p2[1]) / 2.0
        tx, ty = cx + mx * 0.78, cy - my * 0.78
        svg.text(tx - 7, ty + 1.5, f"F{index + 1}", size=4.0, fill="#444444")
    svg.text(cx - 33, cy + 6, f"SLOT {cfg.slot_width_mm:.1f} mm", size=3.8, fill="#d53f8c")


def generate_ring_plate(path: Path, cfg: StructureConfig) -> None:
    svg = Svg(420, 295)
    svg.title("PART A - TOP/BOTTOM HEX RING PLATE (QTY 2)")
    view_label(svg, 25, 30, "TOP VIEW")
    draw_hex_ring_top(svg, cfg, 145, 155)
    dim_h(svg, 145 - cfg.board_mm, 145 + cfg.board_mm, 270, "panel hex corner span 300")

    view_label(svg, 300, 30, "FRONT VIEW")
    svg.rect(285, 65, 105, cfg.ring_thickness_mm, fill="#f8fafc", stroke="#111111", stroke_width=0.45)
    svg.rect(332, 65, 16, cfg.ring_thickness_mm, fill="#fff5f7", stroke="#d53f8c", stroke_width=0.35)
    dim_h(svg, 285, 390, 83, "one edge section")
    dim_v(svg, 397, 65, 65 + cfg.ring_thickness_mm, f"{cfg.ring_thickness_mm:.0f} thick")
    svg.text(286, 100, "Through slot is shown in pink.", size=3.5, class_="note")

    view_label(svg, 300, 130, "RIGHT VIEW")
    svg.rect(315, 160, 50, cfg.ring_thickness_mm, fill="#f8fafc", stroke="#111111", stroke_width=0.45)
    svg.rect(337, 160, cfg.slot_width_mm * 4, cfg.ring_thickness_mm, fill="#fff5f7", stroke="#d53f8c", stroke_width=0.35)
    dim_h(svg, 315, 365, 178, "ring width 50")
    dim_v(svg, 372, 160, 160 + cfg.ring_thickness_mm, f"{cfg.ring_thickness_mm:.0f} thick")
    svg.text(300, 205, "Material suggestion: POM or 6061 anodized.", size=3.5, class_="note")
    svg.save(path)


def generate_backing_strip(path: Path, cfg: StructureConfig) -> None:
    svg = Svg(340, 230)
    svg.title("PART B - VERTICAL BACKING / PRESS STRIP (QTY 12)")
    view_label(svg, 25, 30, "FRONT VIEW")
    x, y = 60, 50
    svg.rect(x, y, cfg.backing_strip_width_mm, cfg.board_mm, fill="#f8fafc", stroke="#111111", stroke_width=0.45)
    for hy in cfg.hole_y_mm:
        svg.circle(x + cfg.backing_strip_width_mm / 2.0, y + cfg.board_mm - hy, cfg.hole_dia_mm / 2.0, fill="none", stroke="#d53f8c", stroke_width=0.55)
    dim_v(svg, x - 12, y, y + cfg.board_mm, "150")
    dim_h(svg, x, x + cfg.backing_strip_width_mm, y + cfg.board_mm + 12, f"{cfg.backing_strip_width_mm:.0f}")
    svg.text(85, 70, "2 x M3 clearance or tapped holes", size=3.5, class_="note")
    svg.text(85, 82, "Hole Y: 22, 128 mm", size=3.5, class_="note")

    view_label(svg, 190, 30, "RIGHT VIEW")
    svg.rect(220, 50, cfg.backing_strip_thickness_mm, cfg.board_mm, fill="#f8fafc", stroke="#111111", stroke_width=0.45)
    dim_h(svg, 220, 220 + cfg.backing_strip_thickness_mm, 212, f"{cfg.backing_strip_thickness_mm:.0f}")
    dim_v(svg, 235, 50, 200, "150")

    view_label(svg, 190, 170, "TOP VIEW")
    svg.rect(220, 190, cfg.backing_strip_width_mm, cfg.backing_strip_thickness_mm, fill="#f8fafc", stroke="#111111", stroke_width=0.45)
    dim_h(svg, 220, 220 + cfg.backing_strip_width_mm, 205, f"{cfg.backing_strip_width_mm:.0f}")
    svg.save(path)


def generate_board_drill_template(path: Path, cfg: StructureConfig) -> None:
    svg = Svg(380, 260)
    svg.title("PART C - 150 x 150 BOARD DRILL TEMPLATE")
    view_label(svg, 25, 30, "FRONT VIEW")
    draw_board_front(svg, cfg, 45, 55, show_keepouts=True)
    dim_h(svg, 45, 195, 220, "150")
    dim_v(svg, 25, 55, 205, "150")
    svg.text(205, 70, f"Holes: diameter {cfg.hole_dia_mm:.1f} mm", size=3.8, class_="note")
    svg.text(205, 82, "Hole coordinates from lower-left:", size=3.8, class_="note")
    svg.text(205, 94, "(48,22), (102,22),", size=3.8, class_="note")
    svg.text(205, 106, "(48,128), (102,128)", size=3.8, class_="note")

    view_label(svg, 235, 135, "TOP VIEW")
    svg.rect(245, 160, 95, cfg.board_thickness_mm, fill="#f8fafc", stroke="#111111", stroke_width=0.45)
    dim_h(svg, 245, 340, 174, "150 board width")
    dim_v(svg, 348, 160, 160 + cfg.board_thickness_mm, f"{cfg.board_thickness_mm:.1f} thick")

    view_label(svg, 235, 185, "RIGHT VIEW")
    svg.rect(260, 210, cfg.board_thickness_mm, 35, fill="#f8fafc", stroke="#111111", stroke_width=0.45)
    svg.text(275, 230, "Board edge", size=3.5, class_="note")
    svg.save(path)


def generate_assembly(path: Path, cfg: StructureConfig) -> None:
    svg = Svg(440, 310)
    svg.title("ASSEMBLY - SIX BOARD HEX FIXTURE")
    view_label(svg, 25, 30, "TOP VIEW")
    draw_hex_ring_top(svg, cfg, 145, 155)
    panels = regular_hex(cfg.board_mm)
    for index in range(6):
        slot = to_svg_xy(offset_segment_rect(panels[index], panels[(index + 1) % 6], cfg.board_thickness_mm), 145, 155)
        svg.polygon(slot, fill="#111111", stroke="#111111", stroke_width=0.2, opacity="0.45")
    svg.text(45, 282, "Black strips: six calibration boards, viewed from top.", size=3.5, class_="note")

    view_label(svg, 310, 30, "FRONT VIEW")
    x, y = 295, 60
    svg.rect(x, y + cfg.ring_thickness_mm, cfg.board_mm, cfg.board_mm, fill="#ffffff", stroke="#111111", stroke_width=0.45)
    svg.rect(x, y, cfg.board_mm, cfg.ring_thickness_mm, fill="#f8fafc", stroke="#111111", stroke_width=0.45)
    svg.rect(x, y + cfg.ring_thickness_mm + cfg.board_mm, cfg.board_mm, cfg.ring_thickness_mm, fill="#f8fafc", stroke="#111111", stroke_width=0.45)
    for hx in cfg.hole_x_mm:
        for hy in cfg.hole_y_mm:
            svg.circle(x + hx, y + cfg.ring_thickness_mm + cfg.board_mm - hy, cfg.hole_dia_mm / 2, fill="none", stroke="#d53f8c", stroke_width=0.45)
    svg.text(x + 6, y + 22, "TOP RING", size=3.3, class_="note")
    svg.text(x + 6, y + cfg.ring_thickness_mm + cfg.board_mm + 6, "BOTTOM RING", size=3.3, class_="note")
    dim_v(svg, x - 12, y, y + cfg.board_mm + 2 * cfg.ring_thickness_mm, "166 total")

    view_label(svg, 310, 245, "RIGHT VIEW")
    svg.rect(330, 268, cfg.board_thickness_mm, 28, fill="#111111", opacity="0.45")
    svg.rect(325, 265, cfg.slot_width_mm * 2.0, cfg.ring_thickness_mm, fill="#f8fafc", stroke="#111111", stroke_width=0.35)
    svg.text(345, 284, f"slot {cfg.slot_width_mm:.1f}", size=3.3, class_="note")
    svg.save(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate SVG three-view drawings for the hex board fixture.")
    parser.add_argument("--out", type=Path, default=Path("generated") / "structure_views")
    parser.add_argument("--board-thickness-mm", type=float, default=3.0)
    parser.add_argument("--slot-clearance-mm", type=float, default=0.3)
    parser.add_argument("--hole-dia-mm", type=float, default=3.4)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = StructureConfig(
        board_thickness_mm=args.board_thickness_mm,
        slot_clearance_mm=args.slot_clearance_mm,
        hole_dia_mm=args.hole_dia_mm,
    )
    args.out.mkdir(parents=True, exist_ok=True)
    generate_assembly(args.out / "assembly_three_view.svg", cfg)
    generate_ring_plate(args.out / "hex_ring_plate_three_view.svg", cfg)
    generate_backing_strip(args.out / "vertical_backing_strip_three_view.svg", cfg)
    generate_board_drill_template(args.out / "board_drill_template_three_view.svg", cfg)
    print(f"Wrote structure SVG views to: {args.out.resolve()}")


if __name__ == "__main__":
    main()
