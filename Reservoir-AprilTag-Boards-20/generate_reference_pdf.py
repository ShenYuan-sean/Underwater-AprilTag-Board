from __future__ import annotations

import argparse
from pathlib import Path

import cv2
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from generate_reservoir_boards import (
    Config,
    TagSpec,
    marker_grid,
    tag_specs_for_board,
    validate_config,
)


PAGE_SIZE = landscape(A4)
BLUE = colors.HexColor("#2B6CB0")
MAGENTA = colors.HexColor("#D53F8C")
GRAY = colors.HexColor("#718096")
DARK = colors.HexColor("#1A202C")
LIGHT = colors.HexColor("#EDF2F7")


def draw_tag(
    pdf: canvas.Canvas,
    dictionary: cv2.aruco.Dictionary,
    tag: TagSpec,
    origin_x: float,
    origin_y: float,
    scale: float,
) -> None:
    def px(value_mm: float) -> float:
        return origin_x + value_mm * scale

    def py(value_mm: float) -> float:
        return origin_y + value_mm * scale

    quiet_x = tag.x0 - tag.quiet_mm
    quiet_y = tag.y0 - tag.quiet_mm
    quiet_size = tag.size_mm + 2.0 * tag.quiet_mm
    pdf.saveState()
    pdf.setStrokeColor(BLUE)
    pdf.setLineWidth(0.35)
    pdf.setDash(3, 2)
    pdf.rect(px(quiet_x), py(quiet_y), quiet_size * scale, quiet_size * scale, stroke=1, fill=0)
    pdf.setDash()
    pdf.setStrokeColor(GRAY)
    pdf.setLineWidth(0.25)
    pdf.rect(px(tag.x0), py(tag.y0), tag.size_mm * scale, tag.size_mm * scale, stroke=1, fill=0)
    pdf.restoreState()

    grid = marker_grid(dictionary, tag.tag_id)
    cell = tag.module_mm
    pdf.saveState()
    pdf.setFillColor(colors.black)
    for row in range(8):
        for col in range(8):
            if not bool(grid[row, col]):
                continue
            x = tag.x0 + col * cell
            y = tag.y0 + tag.size_mm - (row + 1) * cell
            pdf.rect(px(x), py(y), cell * scale, cell * scale, stroke=0, fill=1)
    pdf.restoreState()

    label_y = tag.y0 + tag.size_mm + 2.0
    pdf.saveState()
    pdf.setFillColor(BLUE)
    pdf.setFont("Helvetica", 5.5)
    pdf.drawString(px(tag.x0), py(label_y), f"{tag.name} ID {tag.tag_id}")
    pdf.restoreState()


def draw_board_diagram(
    pdf: canvas.Canvas,
    dictionary: cv2.aruco.Dictionary,
    board_index: int,
    cfg: Config,
    origin_x: float,
    origin_y: float,
    diagram_size: float,
) -> None:
    scale = diagram_size / cfg.board_mm
    tags = tag_specs_for_board(board_index, cfg)

    pdf.saveState()
    pdf.setFillColor(colors.white)
    pdf.setStrokeColor(DARK)
    pdf.setLineWidth(0.65)
    pdf.rect(origin_x, origin_y, diagram_size, diagram_size, stroke=1, fill=1)
    pdf.restoreState()

    for tag in tags:
        draw_tag(pdf, dictionary, tag, origin_x, origin_y, scale)

    pdf.saveState()
    pdf.setStrokeColor(MAGENTA)
    pdf.setLineWidth(0.6)
    for hx, hy in cfg.holes_mm:
        cx = origin_x + hx * scale
        cy = origin_y + hy * scale
        radius = cfg.hole_dia_mm / 2.0 * scale
        cross = 4.0 * scale
        pdf.circle(cx, cy, radius, stroke=1, fill=0)
        pdf.setLineWidth(0.25)
        pdf.line(cx - cross, cy, cx + cross, cy)
        pdf.line(cx, cy - cross, cx, cy + cross)
        pdf.setLineWidth(0.6)
    pdf.restoreState()

    # Production orientation arrow.
    arrow_x = origin_x + 204.0 * scale
    arrow_y1 = origin_y + (cfg.board_mm - 18.0) * scale
    arrow_y2 = origin_y + (cfg.board_mm - 5.0) * scale
    pdf.saveState()
    pdf.setStrokeColor(DARK)
    pdf.setLineWidth(1.1)
    pdf.line(arrow_x, arrow_y1, arrow_x, arrow_y2)
    pdf.line(arrow_x, arrow_y2, arrow_x - 4.0 * scale, arrow_y2 - 5.0 * scale)
    pdf.line(arrow_x, arrow_y2, arrow_x + 4.0 * scale, arrow_y2 - 5.0 * scale)
    pdf.restoreState()

    pdf.saveState()
    pdf.setFillColor(DARK)
    pdf.setFont("Helvetica-Bold", 6.5)
    pdf.drawString(origin_x + 5.0 * scale, origin_y + 4.0 * scale, f"ID = {tags[0].tag_id}")
    pdf.restoreState()


def draw_detail_panel(
    pdf: canvas.Canvas,
    board_index: int,
    cfg: Config,
    panel_x: float,
    panel_y: float,
    panel_w: float,
) -> None:
    tags = tag_specs_for_board(board_index, cfg)
    first_id, last_id = tags[0].tag_id, tags[-1].tag_id
    board_number = cfg.board_number_start + board_index

    pdf.saveState()
    pdf.setFillColor(DARK)
    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawString(panel_x, panel_y, f"BOARD {board_number:02d}")
    pdf.setFont("Helvetica", 9)
    pdf.setFillColor(GRAY)
    pdf.drawString(panel_x, panel_y - 7 * mm, f"Center ID {first_id} | IDs {first_id}-{last_id}")

    y = panel_y - 17 * mm
    rows = [
        ("Board", f"{cfg.board_mm:.0f} x {cfg.board_mm:.0f} mm"),
        ("Center marker", f"{cfg.center_tag_mm:.0f} mm"),
        ("Outer markers", f"8 x {cfg.small_tag_mm:.0f} mm"),
        ("Mount holes", f"4 x DIA {cfg.hole_dia_mm:.1f} mm"),
        ("Hole X", f"{cfg.hole_x_mm:.0f}, {cfg.board_mm - cfg.hole_x_mm:.0f} mm"),
        ("Hole Y", f"{cfg.hole_y_mm:.0f}, {cfg.board_mm - cfg.hole_y_mm:.0f} mm"),
    ]
    row_h = 8 * mm
    pdf.setLineWidth(0.35)
    for index, (key, value) in enumerate(rows):
        top = y - index * row_h
        pdf.setFillColor(LIGHT if index % 2 == 0 else colors.white)
        pdf.rect(panel_x, top - row_h + 1.2 * mm, panel_w, row_h, stroke=0, fill=1)
        pdf.setFillColor(GRAY)
        pdf.setFont("Helvetica", 7.5)
        pdf.drawString(panel_x + 2.5 * mm, top - 4.1 * mm, key)
        pdf.setFillColor(DARK)
        pdf.setFont("Helvetica-Bold", 7.5)
        pdf.drawRightString(panel_x + panel_w - 2.5 * mm, top - 4.1 * mm, value)

    grid_top = y - len(rows) * row_h - 7 * mm
    pdf.setFillColor(DARK)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(panel_x, grid_top, "ID LAYOUT")
    cell_w = panel_w / 3.0
    cell_h = 12 * mm
    layout = [
        [tags[1], tags[2], tags[3]],
        [tags[4], tags[0], tags[5]],
        [tags[6], tags[7], tags[8]],
    ]
    grid_y = grid_top - 5 * mm
    for row_index, row in enumerate(layout):
        for col_index, tag in enumerate(row):
            x = panel_x + col_index * cell_w
            cell_y = grid_y - (row_index + 1) * cell_h
            pdf.setFillColor(LIGHT if tag.name != "CENTER" else colors.HexColor("#E6FFFA"))
            pdf.setStrokeColor(colors.HexColor("#CBD5E0"))
            pdf.rect(x, cell_y, cell_w, cell_h, stroke=1, fill=1)
            pdf.setFillColor(GRAY)
            pdf.setFont("Helvetica", 6.5)
            pdf.drawCentredString(x + cell_w / 2.0, cell_y + 7.0 * mm, tag.name)
            pdf.setFillColor(DARK)
            pdf.setFont("Helvetica-Bold", 9)
            pdf.drawCentredString(x + cell_w / 2.0, cell_y + 2.7 * mm, str(tag.tag_id))

    note_y = grid_y - 3 * cell_h - 10 * mm
    pdf.setFillColor(GRAY)
    pdf.setFont("Helvetica", 6.5)
    notes = [
        "Blue dashed: required white quiet zone",
        "Magenta: mounting holes and centers",
        "Reference diagram is scaled, not 1:1",
        "Manufacture from DXF/SVG; DXF units are mm",
    ]
    for index, note in enumerate(notes):
        pdf.drawString(panel_x, note_y - index * 4.2 * mm, note)

    dxf_name = f"board_{board_number:02d}_ids_{first_id:03d}-{last_id:03d}.dxf"
    pdf.setFillColor(DARK)
    pdf.setFont("Helvetica-Bold", 6.5)
    pdf.drawString(panel_x, 12 * mm, dxf_name)
    pdf.restoreState()


def generate_pdf(path: Path, cfg: Config) -> None:
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    validate_config(cfg, dictionary)
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(path), pagesize=PAGE_SIZE, pageCompression=1)
    board_number_end = cfg.board_number_start + cfg.board_count - 1
    pdf.setTitle(
        f"Reservoir AprilTag Boards {cfg.board_number_start}-{board_number_end} DXF Reference"
    )
    pdf.setAuthor("Ocean Hub")
    page_w, page_h = PAGE_SIZE

    diagram_size = 175 * mm
    origin_x = 10 * mm
    origin_y = 17 * mm
    panel_x = 193 * mm
    panel_w = 94 * mm
    panel_y = page_h - 15 * mm

    for board_index in range(cfg.board_count):
        tags = tag_specs_for_board(board_index, cfg)
        pdf.setFillColor(DARK)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(10 * mm, page_h - 10 * mm, "RESERVOIR APRILTAG BOARD - DXF REFERENCE")
        pdf.setFillColor(GRAY)
        pdf.setFont("Helvetica", 7)
        pdf.drawRightString(
            page_w - 10 * mm,
            page_h - 10 * mm,
            f"Page {board_index + 1} / {cfg.board_count} | Center ID {tags[0].tag_id}",
        )
        draw_board_diagram(pdf, dictionary, board_index, cfg, origin_x, origin_y, diagram_size)
        draw_detail_panel(pdf, board_index, cfg, panel_x, panel_y, panel_w)
        pdf.showPage()

    pdf.save()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a PDF reference for a reservoir board set.")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("output") / "pdf" / "reservoir_apriltag_20_board_reference.pdf",
    )
    parser.add_argument("--board-count", type=int, default=20)
    parser.add_argument("--board-number-start", type=int, default=1)
    parser.add_argument("--start-id", type=int, default=100)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = Config(
        board_count=args.board_count,
        board_number_start=args.board_number_start,
        start_id=args.start_id,
    )
    generate_pdf(args.out, cfg)
    print(f"Wrote PDF reference: {args.out.resolve()}")


if __name__ == "__main__":
    main()
