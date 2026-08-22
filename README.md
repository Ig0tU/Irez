# IREZ

Ultra-resolution aerial mosaic of **West Lafayette, Indiana** — USGS National Map imagery at zoom 17–18 (about 0.9–0.45 m/px). Tuned for a ~36 km² city, not a state-scale stitch.

The interactive atlas streams the same public-domain tiles in the browser (Purdue campus landmarks, city boundary, viewport export). This repository is the **offline stitcher**: Nominatim boundary → Web Mercator grid → async USGS fetch → PNG + GeoTIFF.

## Scale

| Parameter | West Lafayette |
| --- | --- |
| Area | ~36.3 km² |
| Optimal zoom | 17 (~0.9 m/px) or 18 (~0.45 m/px) |
| Admin bbox tiles at z17 | ~1,276 (the bbox is taller than the urban core) |
| Canvas at z17 | ~7,424 × 11,264 px |
| Source | USGS National Map `USGSImageryOnly` (public domain) |

## Workflow

```text
West Lafayette, Indiana
        │
        ▼
Geocode OSM Nominatim polygon (relation 127730)
        │
        ▼
Web Mercator tile grid at zoom 16–18
        │
        ▼
Async fetch USGS 256px imagery tiles
        │
        ▼
In-memory mosaic
        │
        ├◦ West_Lafayette_HighRes.png
        └◦ West_Lafayette_HighRes.tif  (EPSG:4326, QGIS/ArcGIS)
```

## Stitcher

```bash
pip install -r requirements.txt
python stitch_west_lafayette.py
python stitch_west_lafayette.py --zoom 16
```

No API key. Tiles are cached under `west_lafayette_tiles/` so reruns skip downloads.

## Why this works at city scale

1. **Detail** — Zoom 17 resolves Ross–Ade yard lines, Memorial Mall Mall walks, and roof texture across Purdue.
2. **GIS** — The GeoTIFF carries `EPSG:4326` bounds from tile indices (`mercantile.ul`).
3. **RAM** — A city mosaic fits in ordinary memory; a Texas-scale NAIP stitch does not.
4. **License** — USGS National Map imagery is U.S. government public domain.

## Keyboard (atlas)

`+` / `-` zoom · `C` campus · `F` city · `G` tile grid · `L` labels
