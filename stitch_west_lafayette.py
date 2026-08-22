#!/usr/bin/env python3
"""IREZ — stitch USGS National Map imagery for West Lafayette, Indiana.

Default zoom 17 (~0.9 m/px at this latitude). The administrative bbox is
taller than the 36 km² city area, so expect ~1,200 tiles at z17 rather than
the urban-core estimate of 200–400.

Outputs a master PNG and a georeferenced GeoTIFF (EPSG:4326) for QGIS/ArcGIS.

Usage:
    pip install -r requirements.txt
    python stitch_west_lafayette.py
    python stitch_west_lafayette.py --zoom 16
"""

from __future__ import annotations

import argparse
import asyncio
import os

import aiofiles
import aiohttp
import mercantile
import numpy as np
import requests
from PIL import Image
from rasterio.transform import from_bounds
from shapely.geometry import shape

PLACE_NAME = "West Lafayette, Indiana, USA"
DEFAULT_ZOOM = 17
OUTPUT_DIR = "west_lafayette_tiles"
FINAL_PNG = "West_Lafayette_HighRes.png"
FINAL_TIFF = "West_Lafayette_HighRes.tif"
USER_AGENT = "IREZ/1.0 (West Lafayette aerial stitcher; https://github.com/Ig0tU/Irez)"


def get_boundary_polygon(place_name: str):
    print(f"[1/5] Geocoding boundary for '{place_name}'...")
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": place_name,
        "format": "geojson",
        "polygon_geojson": 1,
        "limit": 1,
    }
    headers = {"User-Agent": USER_AGENT}
    res = requests.get(url, params=params, headers=headers, timeout=30)
    res.raise_for_status()
    payload = res.json()
    if not payload.get("features"):
        raise ValueError(f"Could not find geographic boundary for {place_name}")
    geom = shape(payload["features"][0]["geometry"])
    bounds = geom.bounds
    print(f"    Boundary box: {bounds}")
    return geom, bounds


def calculate_tile_grid(bounds, zoom: int):
    print(f"[2/5] Calculating tile grid at zoom {zoom}...")
    min_lon, min_lat, max_lon, max_lat = bounds
    tiles = list(mercantile.tiles(min_lon, min_lat, max_lon, max_lat, zooms=zoom))
    min_x = min(t.x for t in tiles)
    max_x = max(t.x for t in tiles)
    min_y = min(t.y for t in tiles)
    max_y = max(t.y for t in tiles)
    width = (max_x - min_x + 1) * 256
    height = (max_y - min_y + 1) * 256
    print(f"    Tiles: {len(tiles)}  canvas: {width} × {height} px")
    return tiles


async def fetch_tile(session: aiohttp.ClientSession, tile, output_dir: str):
    x, y, z = tile.x, tile.y, tile.z
    url = (
        "https://basemap.nationalmap.gov/arcgis/rest/services/"
        f"USGSImageryOnly/MapServer/tile/{z}/{y}/{x}"
    )
    file_path = os.path.join(output_dir, f"{z}_{x}_{y}.jpg")
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        return file_path
    try:
        async with session.get(url, headers={"User-Agent": USER_AGENT}) as response:
            if response.status == 200:
                data = await response.read()
                async with aiofiles.open(file_path, "wb") as handle:
                    await handle.write(data)
                return file_path
            print(f"    warn: tile {z}/{x}/{y} HTTP {response.status}")
            return None
    except Exception as exc:  # noqa: BLE001 — network errors are expected
        print(f"    error: tile {x},{y}: {exc}")
        return None


async def download_all_tiles(tiles, output_dir: str):
    print("[3/5] Downloading USGS imagery tiles...")
    os.makedirs(output_dir, exist_ok=True)
    connector = aiohttp.TCPConnector(limit_per_host=15)
    timeout = aiohttp.ClientTimeout(total=120)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        paths = await asyncio.gather(
            *(fetch_tile(session, tile, output_dir) for tile in tiles)
        )
    valid = [p for p in paths if p]
    print(f"    Retrieved {len(valid)}/{len(tiles)} tiles.")
    return valid


def stitch_and_export(tiles, zoom: int, output_dir: str, png_path: str, tiff_path: str):
    print("[4/5] Assembling mosaic...")
    min_x = min(t.x for t in tiles)
    max_x = max(t.x for t in tiles)
    min_y = min(t.y for t in tiles)
    max_y = max(t.y for t in tiles)
    tile_size = 256
    canvas_width = (max_x - min_x + 1) * tile_size
    canvas_height = (max_y - min_y + 1) * tile_size
    print(f"    Canvas: {canvas_width} × {canvas_height} px")

    canvas = Image.new("RGB", (canvas_width, canvas_height), (11, 12, 10))
    for t in tiles:
        tile_path = os.path.join(output_dir, f"{t.z}_{t.x}_{t.y}.jpg")
        if not os.path.exists(tile_path):
            continue
        with Image.open(tile_path) as tile_img:
            canvas.paste(
                tile_img.convert("RGB"),
                ((t.x - min_x) * tile_size, (t.y - min_y) * tile_size),
            )

    print("[5/5] Writing PNG and GeoTIFF...")
    canvas.save(png_path, "PNG")
    print(f"    PNG  {png_path}")

    import rasterio

    nw = mercantile.ul(min_x, min_y, zoom)
    se = mercantile.ul(max_x + 1, max_y + 1, zoom)
    transform = from_bounds(nw.lng, se.lat, se.lng, nw.lat, canvas_width, canvas_height)
    img_np = np.array(canvas)
    with rasterio.open(
        tiff_path,
        "w",
        driver="GTiff",
        height=canvas_height,
        width=canvas_width,
        count=3,
        dtype=img_np.dtype,
        crs="EPSG:4326",
        transform=transform,
        compress="lzw",
    ) as dst:
        for band in range(3):
            dst.write(img_np[:, :, band], band + 1)
    print(f"    TIF  {tiff_path}")


async def main():
    parser = argparse.ArgumentParser(description=description="Stitch West Lafayette USGS imagery")
    parser.add_argument("--zoom", type=int, default=DEFAULT_ZOOM, choices=range(13, 19))
    parser.add_argument("--place", default=PLACE_NAME)
    parser.add_argument("--tiles", default=OUTPUT_DIR)
    parser.add_argument("--png", default=FINAL_PNG)
    parser.add_argument("--tif", default=FINAL_TIFF)
    args = parser.parse_args()

    _geom, bounds = get_boundary_polygon(args.place)
    tiles = calculate_tile_grid(bounds, args.zoom)
    await download_all_tiles(tiles, args.tiles)
    stitch_and_export(tiles, args.zoom, args.tiles, args.png, args.tif)


if __name__ == "__main__":
    asyncio.run(main())
