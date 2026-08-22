# IREZ

Ultra-resolution aerial mosaic of **West Lafayette, Indiana** — USGS National Map imagery at zoom 17–18 (about 0.9–0.45 m/px at this latitude). Tuned for a ~36 km² city, not a state-scale stitch.

This repository is the **offline stitcher**: Nominatim boundary → Web Mercator grid → async USGS fetch → PNG + GeoTIFF.

## Scale (administrative bbox)

| Parameter | Value |
| --- | --- |
| City area | ~36.3 km² |
| Optimal zoom | 17 (~0.9 m/px) or 18 (~0.45 m/px) |
| Tiles at z17 | ~1,276 (bbox is taller than the urban core) |
| Canvas at z17 | ~7,424 × 11,264 px |
| Source | USGS National Map `USGSImageryOnly` (public domain) |

Urban-core-only estimates of ~200–400 tiles assume a tighter crop than the full OSM city polygon.

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
        ├─► West_Lafayette_HighRes.png
        └─► West_Lafayette_HighRes.tif  (EPSG:4326, QGIS/ArcGIS)
```

## Stitcher

```bash
pip install -r requirements.txt
python stitch_west_lafayette.py
python stitch_west_lafayette.py --zoom 16
```

No API key. Tiles are cached under `west_lafayette_tiles/` so reruns skip downloads.

## Why city-scale works

1. **Detail** — Zoom 17 resolves Ross–Ade yard lines, Memorial Mall walks, and roof texture across Purdue.
2. **GIS** — The GeoTIFF carries `EPSG:4326` bounds from tile indices (`mercantile.ul`).
3. **RAM** — A city mosaic fits in ordinary memory; a Texas-scale NAIP stitch does not.
4. **License** — USGS National Map imagery is U.S. government public domain.
