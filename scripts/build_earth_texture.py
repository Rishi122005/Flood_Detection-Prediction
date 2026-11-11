#!/usr/bin/env python3
"""Rasterize the bundled public-domain Natural Earth 1:110m countries GeoJSON."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def unwrap_ring(ring: list[list[float]], reference: float | None = None) -> list[tuple[float, float]]:
    points = []
    previous = None
    for lon, lat, *_ in ring:
        lon = float(lon)
        if previous is not None:
            while lon - previous > 180:
                lon -= 360
            while lon - previous < -180:
                lon += 360
        points.append((lon, float(lat)))
        previous = lon
    if points and reference is not None:
        center = sum(x for x, _ in points) / len(points)
        shift = round((reference - center) / 360) * 360
        points = [(x + shift, y) for x, y in points]
    return points


def clip_edge(points: list[tuple[float, float]], axis: int, value: float,
              keep_greater: bool) -> list[tuple[float, float]]:
    if not points:
        return []
    out = []
    prev = points[-1]
    prev_inside = (prev[axis] >= value) if keep_greater else (prev[axis] <= value)
    for cur in points:
        cur_inside = (cur[axis] >= value) if keep_greater else (cur[axis] <= value)
        if cur_inside != prev_inside:
            delta = cur[axis] - prev[axis]
            t = (value - prev[axis]) / delta if delta else 0.0
            out.append((prev[0] + t * (cur[0] - prev[0]), prev[1] + t * (cur[1] - prev[1])))
        if cur_inside:
            out.append(cur)
        prev, prev_inside = cur, cur_inside
    return out


def clip_window(points: list[tuple[float, float]], west: float, east: float) -> list[tuple[float, float]]:
    for axis, value, greater in ((0, west, True), (0, east, False), (1, -90, True), (1, 90, False)):
        points = clip_edge(points, axis, value, greater)
    return points


def xy(point: tuple[float, float], width: int, height: int, scale: int) -> tuple[int, int]:
    lon, lat = point
    return (round((lon + 180) / 360 * width * scale),
            round((90 - lat) / 180 * height * scale))


def _draw_ring(draw: ImageDraw.ImageDraw, ring: list[list[float]], fill, outline,
               width: int, height: int, scale: int, reference: float | None = None) -> float:
    points = unwrap_ring(ring, reference)
    center = sum(x for x, _ in points) / max(1, len(points))
    min_lon, max_lon = min(x for x, _ in points), max(x for x, _ in points)
    first_window = math.floor((min_lon + 180) / 360)
    last_window = math.floor((max_lon + 180) / 360)
    for window in range(first_window, last_window + 1):
        west, east = -180 + window * 360, 180 + window * 360
        shifted = [(x - window * 360, y) for x, y in points]
        clipped = clip_window(shifted, -180, 180)
        if len(clipped) < 3:
            continue
        pixel_points = [xy(p, width, height, scale) for p in clipped]
        draw.polygon(pixel_points, fill=fill)
        if outline:
            draw.line(pixel_points + [pixel_points[0]], fill=outline, width=max(1, round(scale * .42)), joint="curve")
    return center


def build_texture(source: Path, output: Path, width: int = 1440, scale: int = 2) -> None:
    if width < 720 or width > 4096 or width % 2:
        raise ValueError("texture width must be an even value between 720 and 4096")
    data = json.loads(source.read_text(encoding="utf-8"))
    if data.get("type") != "FeatureCollection":
        raise ValueError("Natural Earth source must be a GeoJSON FeatureCollection")
    height = width // 2
    sw, sh = width * scale, height * scale
    image = Image.new("RGB", (sw, sh))
    pixels = image.load()
    for y in range(sh):
        lat_factor = abs((y / sh) * 2 - 1)
        for x in range(sw):
            wave = int(2.5 * math.sin(x * .011) + 1.5 * math.sin((x + y) * .004))
            pixels[x, y] = (10 + int(5 * lat_factor) + wave,
                            38 + int(12 * lat_factor) + wave,
                            51 + int(13 * lat_factor) + wave)
    draw = ImageDraw.Draw(image)
    colors = [(46, 83, 75), (51, 88, 78), (55, 89, 79), (45, 77, 75), (59, 88, 75), (47, 78, 69)]
    outline = (112, 150, 137)
    for feature in data.get("features", []):
        geometry = feature.get("geometry") or {}
        kind, coordinates = geometry.get("type"), geometry.get("coordinates", [])
        polygons = coordinates if kind == "MultiPolygon" else [coordinates] if kind == "Polygon" else []
        props = feature.get("properties") or {}
        name = props.get("ADMIN") or props.get("NAME") or "country"
        color = colors[sum((i + 1) * ord(ch) for i, ch in enumerate(name)) % len(colors)]
        for polygon in polygons:
            if not polygon:
                continue
            outer = polygon[0]
            outer_center = _draw_ring(draw, outer, color, outline, width, height, scale)
            for hole in polygon[1:]:
                _draw_ring(draw, hole, (12, 43, 56), outline, width, height, outer_center)
    image = image.resize((width, height), Image.Resampling.LANCZOS)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "PNG", optimize=True, pnginfo=None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "frontend/earth_countries.geojson")
    parser.add_argument("--output", type=Path, default=ROOT / "frontend/assets/earth_texture.png")
    parser.add_argument("--width", type=int, default=1440)
    args = parser.parse_args()
    build_texture(args.source, args.output, args.width)
    print(f"Created {args.output} ({args.width}x{args.width // 2}) from {args.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
