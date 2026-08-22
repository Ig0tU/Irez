# IREZ

Ultra-resolution aerial mosaic of **West Lafayette, Indiana** (Purdue University area).

Offline stitcher: boundary → Web Mercator grid → async tile fetch → PNG + GeoTIFF.

**Default source is Indiana GIO** (state 6-inch / 15 cm ortho, CC0), not USGS. USGS National Map only has reliable tiles through **zoom 16** here; z17+ often returns HTTP 404.

## Quick start

```bash
pip install -r requirements.txt

# Recommended: Purdue campus at z18 from Indiana GIO
python stitch_west_lafayette.py --source indiana --zoom 18 --crop campus

# Full city (OSM polygon) at z17 — more tiles, longer run
python stitch_west_lafayette.py --source indiana --zoom 17 --crop city

# USGS only (works through z16)
python stitch_west_lafayette.py --source usgs --zoom 16

# Per-tile fallback: indiana → esri → usgs
python stitch_west_lafayette.py --source auto --zoom 18 --crop campus
```

No API key. Downloaded tiles are cached under `west_lafayette_tiles/`; re-runs skip existing files. Ctrl+C is safe — partial cache is kept.

## Sources

| `--source` | Endpoint | Practical max zoom (WL) | License / notes |
| --- | --- | --- | --- |
| **`indiana`** (default) | [Indiana GIO L19v4 cache](https://di-ingov.img.arcgis.com/arcgis/rest/services/CacheWebMercator/IndianaCurrentImageryCacheL19v4/MapServer) | **z19** | **CC0** — 6-inch class state ortho |
| `esri` | Esri World Imagery | z19 | Check Esri terms for bulk offline use |
| `usgs` | USGS National Map `USGSImageryOnly` | **z16** | Public domain; z17+ 404s here |
| `auto` | indiana → esri → usgs | depends | Best effort per tile |

Indiana GIO program hub: [imagery.gio.in.gov](https://imagery.gio.in.gov/)  
REST root: [di-ingov.img.arcgis.com/arcgis/rest/services](https://di-ingov.img.arcgis.com/arcgis/rest/services/)  
Raw COGs (AWS Open Data): `s3://gisimageryingov` (`us-east-2`) — [browser](https://gisimageryingov.s3.amazonaws.com/index.html)

Tippecanoe County (West Lafayette) was in the **2023** western-tier collection; next statewide west-tier flight is planned around **2028**.

### Why USGS 404s at z17+

`USGSImageryOnly` is cached to about scale **1:9,028** (LOD 16). Higher LODs are listed in the service metadata but many tiles for this area return 404. That is a server coverage limit, not a bug in the stitcher.

## Crops

| `--crop` | Area |
| --- | --- |
| `city` | OSM Nominatim polygon for West Lafayette |
| `campus` | Fixed Purdue bbox (smaller, faster, high detail) |
| `bbox` | Fixed city bounding box without geocoding |

## Scale (approx.)

| Parameter | Campus z18 (indiana) | Full city z17 (indiana) | Full city z16 (usgs) |
| --- | --- | --- | --- |
| Area focus | Purdue core | ~36 km² admin | ~36 km² admin |
| Tile count | hundreds | ~1,000+ | fewer |
| GSD class | state 15 cm ortho, tiled | same | ~0.9 m/px at lat 40.4 |

Exact tile counts print at runtime.

## Workflow

```text
West Lafayette / Purdue
        │
        ▼
Bounds (Nominatim city | campus | fixed bbox)
        │
        ▼
Web Mercator tile grid (zoom 13–19)
        │
        ▼
Async fetch (Indiana GIO / Esri / USGS)
        │
        ▼
In-memory mosaic
        │
        ├─► West_Lafayette_HighRes.png
        └─► West_Lafayette_HighRes.tif  (EPSG:4326)
```

## Output

- **PNG** — viewing / print
- **GeoTIFF** — `EPSG:4326` with transform from tile corners (`mercantile.ul`) for QGIS / ArcGIS

## CLI

```text
--zoom N          13–19 (default 17)
--source NAME     indiana | esri | usgs | auto (default indiana)
--crop NAME       city | campus | bbox (default city)
--concurrency N   parallel downloads (default 12)
--tiles DIR       cache directory
--png PATH        output PNG
--tif PATH        output GeoTIFF
```

## Higher quality than tiles

For archival 4-band COGs (not Web Mercator screenshots):

1. [Indiana ortho tile footprints](https://www.arcgis.com/home/item.html?id=548c94928bd64ac2a7f1ba94d6b4e7f4) on IndianaMap  
2. Download Tippecanoe COGs from `s3://gisimageryingov`  
3. Mosaic with GDAL / QGIS  

Dynamic export (small AOIs):

```text
.../DynamicWebMercator/Indiana_Current_Imagery/ImageServer/exportImage
```

## License of outputs

- **Indiana GIO** tiles: CC0  
- **USGS** tiles: U.S. government public domain  
- **Esri** tiles: subject to Esri terms — prefer `indiana` for redistribution  
