from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

import cv2
import numpy as np


SVG_NS = "{http://www.w3.org/2000/svg}"


def parse_number(value: str) -> float:
    match = re.match(r"^\s*([-+]?\d+(?:\.\d+)?)", value)
    if not match:
        raise ValueError(f"Cannot parse numeric value from {value!r}")
    return float(match.group(1))


def parse_viewbox(root: ET.Element) -> tuple[float, float, float, float]:
    viewbox = root.attrib.get("viewBox")
    if viewbox:
        parts = [float(item) for item in viewbox.replace(",", " ").split()]
        if len(parts) == 4:
            return parts[0], parts[1], parts[2], parts[3]
    width = parse_number(root.attrib["width"])
    height = parse_number(root.attrib["height"])
    return 0.0, 0.0, width, height


def black_rects_from_svg(svg_path: Path) -> tuple[tuple[float, float, float, float], list[tuple[float, float, float, float]]]:
    root = ET.parse(svg_path).getroot()
    viewbox = parse_viewbox(root)
    rects: list[tuple[float, float, float, float]] = []
    for rect in root.iter(f"{SVG_NS}rect"):
        fill = rect.attrib.get("fill", "").lower()
        if fill not in {"#000000", "black", "#000"}:
            continue
        x = float(rect.attrib["x"])
        y = float(rect.attrib["y"])
        width = float(rect.attrib["width"])
        height = float(rect.attrib["height"])
        rects.append((x, y, width, height))
    return viewbox, rects


def rasterize_svg_tags(svg_path: Path, px_per_mm: float) -> np.ndarray:
    min_x, min_y, width_mm, height_mm = black_rects_from_svg(svg_path)[0]
    _, rects = black_rects_from_svg(svg_path)
    width_px = int(round(width_mm * px_per_mm))
    height_px = int(round(height_mm * px_per_mm))
    image = np.full((height_px, width_px), 255, dtype=np.uint8)
    for x, y, width, height in rects:
        x1 = int(round((x - min_x) * px_per_mm))
        y1 = int(round((y - min_y) * px_per_mm))
        x2 = int(round((x - min_x + width) * px_per_mm))
        y2 = int(round((y - min_y + height) * px_per_mm))
        cv2.rectangle(image, (x1, y1), (x2, y2), 0, thickness=-1)
    return image


def detect_ids(image: np.ndarray) -> tuple[list[int], list[np.ndarray]]:
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    parameters = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(dictionary, parameters)
    corners, ids, _ = detector.detectMarkers(image)
    if ids is None:
        return [], []
    return [int(item) for item in ids.flatten()], corners


def expected_ids_for_face(svg_path: Path, start_id: int, tags_per_face: int) -> list[int] | None:
    match = re.search(r"face_(\d{2})\.svg$", svg_path.name)
    if not match:
        return None
    face_index = int(match.group(1)) - 1
    first = start_id + face_index * tags_per_face
    return list(range(first, first + tags_per_face))


def write_debug_image(
    image: np.ndarray,
    corners: Iterable[np.ndarray],
    ids: list[int],
    debug_path: Path,
) -> None:
    color = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if ids:
        cv2.aruco.drawDetectedMarkers(color, list(corners), np.array(ids, dtype=np.int32))
    debug_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(debug_path), color)


def verify_file(
    svg_path: Path,
    px_per_mm: float,
    start_id: int,
    tags_per_face: int,
    debug_dir: Path | None,
) -> bool:
    image = rasterize_svg_tags(svg_path, px_per_mm)
    ids, corners = detect_ids(image)
    found = sorted(ids)
    expected = expected_ids_for_face(svg_path, start_id, tags_per_face)

    ok = True
    if expected is not None:
        missing = sorted(set(expected) - set(found))
        extra = sorted(set(found) - set(expected))
        ok = not missing and not extra and len(found) == len(expected)
        status = "OK" if ok else "FAIL"
        print(f"{status} {svg_path.name}: found {found}, expected {expected}")
        if missing:
            print(f"  missing: {missing}")
        if extra:
            print(f"  extra: {extra}")
    else:
        print(f"INFO {svg_path.name}: found {found}")

    if debug_dir is not None:
        write_debug_image(image, corners, ids, debug_dir / f"{svg_path.stem}_detected.png")
    return ok


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect AprilTag 36h11 IDs in generated board SVG files.")
    parser.add_argument("--input-dir", type=Path, default=Path("generated"))
    parser.add_argument("--px-per-mm", type=float, default=8.0)
    parser.add_argument("--start-id", type=int, default=0)
    parser.add_argument("--tags-per-face", type=int, default=9)
    parser.add_argument("--debug-dir", type=Path, default=Path("generated") / "verification_debug")
    parser.add_argument("--no-debug", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    svg_files = sorted(args.input_dir.glob("face_[0-9][0-9].svg"))
    if not svg_files:
        raise FileNotFoundError(f"No face_XX.svg files found under {args.input_dir}")
    debug_dir = None if args.no_debug else args.debug_dir
    results = [
        verify_file(svg_path, args.px_per_mm, args.start_id, args.tags_per_face, debug_dir)
        for svg_path in svg_files
    ]
    if not all(results):
        raise SystemExit(1)
    print(f"All {len(svg_files)} board SVG files passed AprilTag ID verification.")


if __name__ == "__main__":
    main()
