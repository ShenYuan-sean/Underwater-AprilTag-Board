from __future__ import annotations

import argparse
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import cv2
import numpy as np


SVG_NS = "{http://www.w3.org/2000/svg}"
NAME_RE = re.compile(r"^board_(\d+)_ids_(\d+)-(\d+)\.svg$")


def parse_number(value: str) -> float:
    match = re.match(r"^\s*([-+]?\d+(?:\.\d+)?)", value)
    if not match:
        raise ValueError(f"Cannot parse numeric value from {value!r}")
    return float(match.group(1))


def parse_svg(svg_path: Path) -> tuple[tuple[float, float, float, float], list[tuple[float, float, float, float]]]:
    root = ET.parse(svg_path).getroot()
    if "viewBox" in root.attrib:
        values = [float(value) for value in root.attrib["viewBox"].replace(",", " ").split()]
        if len(values) != 4:
            raise ValueError(f"Invalid viewBox in {svg_path}")
        viewbox = (values[0], values[1], values[2], values[3])
    else:
        viewbox = (0.0, 0.0, parse_number(root.attrib["width"]), parse_number(root.attrib["height"]))

    black_rects: list[tuple[float, float, float, float]] = []
    for rect in root.iter(f"{SVG_NS}rect"):
        if rect.attrib.get("fill", "").lower() not in {"black", "#000", "#000000"}:
            continue
        black_rects.append(
            (
                float(rect.attrib["x"]),
                float(rect.attrib["y"]),
                float(rect.attrib["width"]),
                float(rect.attrib["height"]),
            )
        )
    return viewbox, black_rects


def rasterize(svg_path: Path, px_per_mm: float) -> np.ndarray:
    (min_x, min_y, width_mm, height_mm), rects = parse_svg(svg_path)
    image = np.full(
        (int(round(height_mm * px_per_mm)), int(round(width_mm * px_per_mm))),
        255,
        dtype=np.uint8,
    )
    for x, y, width, height in rects:
        x1 = int(round((x - min_x) * px_per_mm))
        y1 = int(round((y - min_y) * px_per_mm))
        x2 = int(round((x - min_x + width) * px_per_mm))
        y2 = int(round((y - min_y + height) * px_per_mm))
        cv2.rectangle(image, (x1, y1), (x2, y2), 0, thickness=-1)
    return image


def detect(image: np.ndarray) -> tuple[list[int], list[np.ndarray]]:
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    parameters = cv2.aruco.DetectorParameters()
    parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    detector = cv2.aruco.ArucoDetector(dictionary, parameters)
    corners, ids, _ = detector.detectMarkers(image)
    if ids is None:
        return [], []
    return [int(value) for value in ids.flatten()], corners


def write_debug(path: Path, image: np.ndarray, ids: list[int], corners: list[np.ndarray]) -> None:
    canvas = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if ids:
        cv2.aruco.drawDetectedMarkers(canvas, corners, np.array(ids, dtype=np.int32))
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), canvas)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify generated reservoir AprilTag SVG files.")
    parser.add_argument("--input-dir", type=Path, default=Path("generated"))
    parser.add_argument("--px-per-mm", type=float, default=4.0)
    parser.add_argument("--debug-dir", type=Path, default=Path("generated") / "verification_debug")
    parser.add_argument("--no-debug", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    svg_files = sorted(
        path for path in args.input_dir.glob("board_*_ids_*.svg") if NAME_RE.match(path.name)
    )
    if not svg_files:
        raise FileNotFoundError(f"No clean board SVG files found under {args.input_dir}")

    failures = 0
    for svg_path in svg_files:
        match = NAME_RE.match(svg_path.name)
        assert match is not None
        first_id = int(match.group(2))
        last_id = int(match.group(3))
        expected_ids = list(range(first_id, last_id + 1))
        image = rasterize(svg_path, args.px_per_mm)
        found, corners = detect(image)
        found = sorted(found)
        ok = found == expected_ids
        print(f"{'OK' if ok else 'FAIL'} {svg_path.name}: found={found}, expected={expected_ids}")
        failures += int(not ok)
        if not args.no_debug:
            write_debug(args.debug_dir / f"{svg_path.stem}_detected.png", image, found, corners)

    if failures:
        raise SystemExit(f"{failures} of {len(svg_files)} boards failed verification")
    print(f"All {len(svg_files)} board SVG files passed AprilTag 36h11 ID verification.")


if __name__ == "__main__":
    main()
