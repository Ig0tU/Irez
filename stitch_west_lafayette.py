#!/usr/bin/env python3
"""IREZ — high-res aerial mosaic for West Lafayette, Indiana.

Why z17/z18 404 on USGS?
  USGSImageryOnly's practical max scale is ~1:9,028 (LOD 16). Tiles at z17+
  often return HTTP 404 for this area even though LODs are listed.

Better quality (tested over Purdue campus):
  - indiana  Indiana GIO current ortho cache (CC0) — works z16–z19
  - esri     Esri World Imagery — works z16–z19 (check Esri ToS for bulk use)
  - usgs     USGS National Map — reliable through z16 only
  - auto     try indiana → esri → usgs per tile

Usage:
    pip install -r requirements.txt

    # Best free quality for Indiana (recommended)
    python stitch_west_lafayette.py --source indiana --zoom 18 --crop campus

    # Full city at z16 (USGS works)
    python stitch_west_lafayette.py --source usgs --zoom 16

    # Auto fallback chain
    python stitch_west_lafayette.py --source auto --zoom 18 --crop campus
"""

from __future__ import annotations

import argparse
import asyncio
import os
from typing import Iterable

import aiofiles
import aiohttp
import mercantile
import numpy as np
import requests
from PIL import Image
from rasterio.transform import from_bounds
from shapely.geometry import box, shape

PLACE_NAME = "West Lafayette, Indiana, USA"
USER_AGENT = "IREZ/1.0 (West Lafayette aerial stitcher; https://github.com/Ig0tU/Irez)"

# Purdue campus approx (lon_min, lat_min, lon_max, lat_max)
CAMPUS_BBOX = (-86.928, 40.4185, -86.903, 40.4385)

SOURCES: dict[str, str] = {
    # Indiana GIO current ortho cache — 0.5 ft class imagery, CC0
    "indiana": (
        "https://di-ingov.img.arcgis.com/arcgis/rest/services/"
        "CacheWebMercator/IndianaCurrentImageryCacheL19v4/MapServer/tile/{z}/{y}/{x}"
    ),
    # Esri World Imagery — deep zoom, review terms for bulk download
    "esri": (
        "https://server.arcgisonline.com/ArcGIS/rest/services/"
        "World_Imagery/MapServer/tile/{z}/{y}/{x}"
    ),
    # USGS National Map — public domain, native detail effectively stops ~z16 here
    "usgs": (
        "https://basemap.nationalmap.gov/arcgis/rest/services/"
        "USGSImageryOnly/MapServer/tile/{z}/{y}/{x}"
    ),
}

AUTO_CHAIN = ("indiana", "esri", "usgs")


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


def resolve_bounds(crop: str, place_name: str):
    if crop == "campus":
        b = CAMPUS_BBOX
        print(f"[1/5] Using Purdue campus crop: {b}")
        return box(*b), b
    if crop == "bbox":
        # tight city bbox without full polygon geocode
        b = (-86.9624434, 40.4000158, -86.8869841, 40.4895414)
        print(f"[1/5] Using fixed city bbox: {b}")
        return box(*b), b
    return get_boundary_polygon(place_name)


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
    if zoom >= 17 and len(tiles) > 800:
        print(
            "    tip: full-city z17+ is large — try --crop campus or --zoom 16"
        )
    return tiles


def source_urls(source: str, z: int, y: int, x: int) -> list[tuple[str, str]]:
    """Return ordered (name, url) candidates for one tile."""
    if source == "auto":
        names = AUTO_CHAIN
    else:
        names = (source,)
    out: list[tuple[str, str]] = []
    for name in names:
        tmpl = SOURCES[name]
        out.append((name, tmpl.format(z=z, y=y, x=x)))
    return out


async def fetch_tile(
    session: aiohttp.ClientSession,
    tile,
    output_dir: str,
    source: str,
    retries: int = 2,
):
    x, y, z = tile.x, tile.y, tile.z
    file_path = os.path.join(output_dir, f"{source}_{z}_{x}_{y}.jpg")
    if source == "auto":
        file_path = os.path.join(output_dir, f"auto_{z}_{x}_{y}.jpg")
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        return file_path

    last_status = None
    for name, url in source_urls(source, z, y, x):
        for attempt in range(retries + 1):
            try:
                async with session.get(
                    url, headers={"User-Agent": USER_AGENT}
                ) as response:
                    last_status = response.status
                    if response.status == 200:
                        data = await response.read()
                        if len(data) < 500:
                            # tiny body often means empty/error tile
                            continue
                        async with aiofiles.open(file_path, "wb") as handle:
                            await handle.write(data)
                        return file_path
                    if response.status == 404:
                        break  # try next source
                    await asyncio.sleep(0.4 * (attempt + 1))
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                if attempt == retries:
                    print(f"    error: {name} {z}/{x}/{y}: {exc}")
                await asyncio.sleep(0.4 * (attempt + 1))

    print(f"    warn: tile {z}/{y}/{x} unavailable (last HTTP {last_status})")
    return None


async def download_all_tiles(
    tiles,
    output_dir: str,
    source: str,
    concurrency: int = 12,
):
    print(f"[3/5] Downloading tiles (source={source}, concurrency={concurrency})...")
    os.makedirs(output_dir, exist_ok=True)
    connector = aiohttp.TCPConnector(limit_per_host=concurrency)
    timeout = aiohttp.ClientTimeout(total=180)
    sem = asyncio.Semaphore(concurrency)

    async def limited(tile):
        async with sem:
            return await fetch_tile(session, tile, output_dir, source)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [limited(t) for t in tiles]
        paths: list = []
        done = 0
        total = len(tasks)
        for coro in asyncio.as_completed(tasks):
            paths.append(await coro)
            done += 1
            if done % 25 == 0 or done == total:
                ok = sum(1 for p in paths if p)
                print(f"    progress {done}/{total}  ok={ok}")

    valid = [p for p in paths if p]
    print(f"    Retrieved {len(valid)}/{len(tiles)} tiles.")
    if not valid:
        raise SystemExit(
            "No tiles downloaded. USGS maxes out ~z16 here — use "
            "--source indiana --zoom 18 --crop campus"
        )
    return valid


def tile_filename(source: str, t) -> str:
    prefix = "auto" if source == "auto" else source
    return f"{prefix}_{t.z}_{t.x}_{t.y}.jpg"


def stitch_and_export(
    tiles,
    zoom: int,
    output_dir: str,
    png_path: str,
    tiff_path: str,
    source: str,
):
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
    pasted = 0
    for t in tiles:
        tile_path = os.path.join(output_dir, tile_filename(source, t))
        if not os.path.exists(tile_path):
            continue
        with Image.open(tile_path) as tile_img:
            canvas.paste(
                tile_img.convert("RGB"),
                ((t.x - min_x) * tile_size, (t.y - min_y) * tile_size),
            )
            pasted += 1
    print(f"    Pasted {pasted}/{len(tiles)} tiles")

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
    parser = argparse.ArgumentParser(
        description="Stitch West Lafayette aerial imagery (Indiana GIO / Esri / USGS)"
    )
    parser.add_argument(
        "--zoom",
        type=int,
        default=17,
        choices=range(13, 20),
        help="Web Mercator zoom. USGS only reliable ≤16; indiana/esri work to 19.",
    )
    parser.add_argument(
        "--source",
        choices=(*SOURCES.keys(), "auto"),
        default="indiana",
        help="Tile source (default: indiana). USGS 404s above z16 here.",
    )
    parser.add_argument(
        "--crop",
        choices=("city", "campus", "bbox"),
        default="city",
        help="city=OSM polygon, campus=Purdue only, bbox=fixed city box",
    )
    parser.add_argument("--place", default=PLACE_NAME)
    parser.add_argument("--tiles", default="west_lafayette_tiles")
    parser.add_argument("--png", default="West_Lafayette_HighRes.png")
    parser.add_argument("--tif", default="West_Lafayette_HighRes.tif")
    parser.add_argument("--concurrency", type=int, default=12)
    args = parser.parse_args()

    if args.source == "usgs" and args.zoom > 16:
        print(
            f"warning: USGS ImageryOnly typically 404s above z16 for this area.\n"
            f"         Use --source indiana --zoom {args.zoom} instead.\n"
        )

    _geom, bounds = resolve_bounds(args.crop, args.place)
    tiles = calculate_tile_grid(bounds, args.zoom)
    await download_all_tiles(tiles, args.tiles, args.source, args.concurrency)
    stitch_and_export(
        tiles, args.zoom, args.tiles, args.png, args.tif, args.source
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted — partial tiles are kept in the cache dir; re-run to resume.")
