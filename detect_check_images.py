from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


@dataclass
class Detection:
    tag_id: int
    corners: np.ndarray
    area: float
    variant: str


def marker_area(corners: np.ndarray) -> float:
    points = corners.reshape(4, 2).astype(np.float32)
    return float(abs(cv2.contourArea(points)))


def make_detector() -> cv2.aruco.ArucoDetector:
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    parameters = cv2.aruco.DetectorParameters()
    parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    parameters.adaptiveThreshWinSizeMin = 3
    parameters.adaptiveThreshWinSizeMax = 53
    parameters.adaptiveThreshWinSizeStep = 4
    return cv2.aruco.ArucoDetector(dictionary, parameters)


def image_variants(image: np.ndarray) -> list[tuple[str, np.ndarray, float]]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()
    variants: list[tuple[str, np.ndarray, float]] = [("gray", gray, 1.0)]

    for scale in (2.0, 4.0):
        resized = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        variants.append((f"gray_x{scale:g}", resized, scale))

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    variants.append(("clahe", clahe, 1.0))
    variants.append(("clahe_x2", cv2.resize(clahe, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC), 2.0))

    blur = cv2.GaussianBlur(gray, (0, 0), 1.0)
    sharpened = cv2.addWeighted(gray, 1.7, blur, -0.7, 0)
    variants.append(("sharpen", sharpened, 1.0))
    variants.append(("sharpen_x2", cv2.resize(sharpened, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC), 2.0))
    return variants


def detect_image(image: np.ndarray) -> list[Detection]:
    detector = make_detector()
    best_by_id: dict[int, Detection] = {}
    for name, variant, scale in image_variants(image):
        corners, ids, _ = detector.detectMarkers(variant)
        if ids is None:
            continue
        for raw_id, raw_corners in zip(ids.flatten(), corners):
            scaled_corners = raw_corners.astype(np.float32) / scale
            tag_id = int(raw_id)
            detection = Detection(
                tag_id=tag_id,
                corners=scaled_corners,
                area=marker_area(scaled_corners),
                variant=name,
            )
            if tag_id not in best_by_id or detection.area > best_by_id[tag_id].area:
                best_by_id[tag_id] = detection
    return sorted(best_by_id.values(), key=lambda item: item.tag_id)


def draw_debug(image: np.ndarray, detections: list[Detection], output_path: Path) -> None:
    canvas = image.copy()
    if canvas.ndim == 2:
        canvas = cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)
    for detection in detections:
        points = detection.corners.reshape(4, 2).astype(int)
        cv2.polylines(canvas, [points], True, (0, 255, 0), 2, cv2.LINE_AA)
        center = points.mean(axis=0).astype(int)
        label = f"ID {detection.tag_id}"
        cv2.putText(
            canvas,
            label,
            (int(center[0]) - 24, int(center[1])),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), canvas)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect AprilTag 36h11 IDs in check images.")
    parser.add_argument("--input-dir", type=Path, default=Path("check"))
    parser.add_argument("--output-dir", type=Path, default=Path("check_detected"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    image_paths = sorted(path for path in args.input_dir.iterdir() if path.suffix.lower() in IMAGE_EXTS)
    if not image_paths:
        raise FileNotFoundError(f"No images found in {args.input_dir}")

    for path in image_paths:
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            print(f"FAIL {path.name}: cannot read image")
            continue
        detections = detect_image(image)
        ids = [item.tag_id for item in detections]
        variants = ", ".join(f"{item.tag_id}:{item.variant}" for item in detections)
        print(f"{path.name}: shape={image.shape[1]}x{image.shape[0]}, count={len(ids)}, ids={ids}")
        if variants:
            print(f"  variants: {variants}")
        draw_debug(image, detections, args.output_dir / f"{path.stem}_detected.png")


if __name__ == "__main__":
    main()
