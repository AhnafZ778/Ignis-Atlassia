#!/usr/bin/env python3
"""Prepare small, georeferenced display layers from the already local NASA rasters.

Uses the system GDAL Python package when available. It does not fetch or install
anything. Outputs are cropped PNG overlays for the replay page, not analysis
inputs or replacements for the original HDF/DEM products.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

try:
    import numpy as np
    from osgeo import gdal, osr
    from pyproj import Transformer
except ImportError as exc:
    raise SystemExit("Local context preparation requires system GDAL, NumPy and pyproj; no packages were installed.") from exc

ROOT = Path(__file__).resolve().parent.parent
INPUTS = ROOT / "NASA_data" / "heatmap_inputs" / "earthdata"
OUTPUT = ROOT / "fireatlas" / "static" / "replay-context"
CASES = {
    "park-2024": (-122.0, 39.5, -121.3, 40.5),
    "camp-2018": (-121.85, 39.6, -121.3, 40.0),
    "grove-2025": (-121.55, 39.25, -121.28, 39.48),
}
WIDTH, HEIGHT = 760, 560
TARGET_CRS = "EPSG:32610"
gdal.UseExceptions()


def source_bounds(case_id: str):
    bbox = CASES[case_id]
    transform = Transformer.from_crs("EPSG:4326", TARGET_CRS, always_xy=True)
    return transform.transform_bounds(*bbox, densify_pts=21)


def tile_sources(case_id: str):
    west, south, east, north = CASES[case_id]
    sources = []
    for archive in sorted((INPUTS / "terrain" / "norcal").glob("NASADEM_HGT_*.zip")):
        match = re.search(r"_n(\d+)w(\d+)\.zip$", archive.name)
        if not match:
            continue
        south_deg, west_deg = map(int, match.groups())
        west_deg = -west_deg
        # The 1-degree HGT tile intersects the case box with a small edge margin.
        if west_deg < east and west_deg + 1 > west and south_deg < north and south_deg + 1 > south:
            with zipfile.ZipFile(archive) as zipped:
                hgt = next((name for name in zipped.namelist() if name.lower().endswith(".hgt")), None)
            if hgt:
                sources.append(f"/vsizip/{archive.resolve()}/{hgt}")
    return sources


def warp_to_case(sources, case_id: str, *, source_nodata=None, destination_nodata=-9999,
                 data_type=gdal.GDT_Float32, resampling="bilinear"):
    bounds = source_bounds(case_id)
    return gdal.Warp("", sources, format="MEM", outputBounds=bounds,
                     outputBoundsSRS=TARGET_CRS, dstSRS=TARGET_CRS,
                     width=WIDTH, height=HEIGHT, resampleAlg=resampling,
                     srcNodata=source_nodata, dstNodata=destination_nodata,
                     outputType=data_type, multithread=True, warpOptions=["NUM_THREADS=ALL_CPUS"])


def png_from_rgba(case_id: str, layer: str, rgba: np.ndarray, description: dict):
    target = OUTPUT / case_id / f"{layer}.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    mem = gdal.GetDriverByName("MEM").Create("", WIDTH, HEIGHT, 4, gdal.GDT_Byte)
    spatial_reference = osr.SpatialReference()
    spatial_reference.ImportFromEPSG(32610)
    mem.SetProjection(spatial_reference.ExportToWkt())
    bounds = source_bounds(case_id)
    transform = ((bounds[0], (bounds[2] - bounds[0]) / WIDTH, 0,
                  bounds[3], 0, -(bounds[3] - bounds[1]) / HEIGHT))
    mem.SetGeoTransform(transform)
    for band in range(4):
        mem.GetRasterBand(band + 1).WriteArray(rgba[:, :, band])
    output = gdal.Warp(str(target), mem, format="PNG", dstSRS="EPSG:4326",
                       outputBounds=CASES[case_id], width=WIDTH, height=HEIGHT,
                       resampleAlg="bilinear", multithread=True)
    output = None
    body = target.read_bytes()
    description.update({"path": target.relative_to(ROOT / "fireatlas" / "static").as_posix(),
                        "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
                        "bounds": list(CASES[case_id]), "width": WIDTH, "height": HEIGHT})
    return description


def valid_mask(values, nodata):
    mask = np.isfinite(values)
    if nodata is not None:
        mask &= values != nodata
    return mask


def render_terrain(case_id: str):
    sources = tile_sources(case_id)
    if not sources:
        return {"status": "unavailable", "reason": "No intersecting local NASADEM tile was found."}
    dem = warp_to_case(sources, case_id, source_nodata=-32768,
                       destination_nodata=-9999, resampling="bilinear")
    hillshade = gdal.DEMProcessing("", dem, "hillshade", format="MEM", azimuth=315,
                                    altitude=42, zFactor=1, scale=1, computeEdges=True)
    values = hillshade.ReadAsArray().astype(np.float32)
    alpha = (valid_mask(dem.ReadAsArray(), -9999).astype(np.uint8) * 145)
    # Warm neutral relief tint, with enough transparency to keep satellite texture visible.
    shade = np.clip((values - 45) * 1.08 + 95, 55, 205).astype(np.uint8)
    rgba = np.dstack((shade, np.clip(shade * .88, 0, 255).astype(np.uint8),
                      np.clip(shade * .68, 0, 255).astype(np.uint8), alpha))
    return png_from_rgba(case_id, "terrain", rgba,
                         {"status": "available", "product": "NASADEM_HGT", "version": "001",
                          "style": "Local NASADEM hillshade draped as transparent terrain context.",
                          "tile_sources": [Path(src.split("/")[-2]).name for src in sources]})


def hdf_band(paths, product_dir: str, pattern: str, expression: str,
             band_name: str):
    files = sorted((INPUTS / product_dir / "norcal").glob(pattern))
    if not files:
        return []
    output = []
    for filename in files:
        dataset = gdal.Open(str(filename))
        subdataset = next((name for name, _ in dataset.GetSubDatasets() if expression in name), None)
        if subdataset:
            output.append((filename, subdataset))
    return output


def render_ndvi(case_id: str):
    if case_id != "park-2024":
        return {"status": "unavailable", "reason": "No local MOD13Q1 composite covers this case year."}
    data_files = hdf_band(None, "ndvi", "MOD13Q1.A2024193.*.hdf", "250m 16 days NDVI", "NDVI")
    qa_files = hdf_band(None, "ndvi", "MOD13Q1.A2024193.*.hdf", "250m 16 days pixel reliability", "QA")
    data_vrt = gdal.BuildVRT("", [item[1] for item in data_files])
    qa_vrt = gdal.BuildVRT("", [item[1] for item in qa_files])
    data = warp_to_case(data_vrt, case_id, source_nodata=-3000, destination_nodata=-9999)
    qa = warp_to_case(qa_vrt, case_id, source_nodata=255, destination_nodata=255,
                      data_type=gdal.GDT_Byte, resampling="near")
    values = data.ReadAsArray().astype(np.float32) * .0001
    quality = qa.ReadAsArray()
    valid = valid_mask(values, -9999) & (quality <= 1) & (values >= -.2) & (values <= 1.0)
    # Sequential beige -> yellow-green -> deep green ramp for an understandable NDVI context layer.
    stops = [(0.0, (112, 78, 55)), (.2, (165, 137, 86)), (.4, (178, 184, 88)),
             (.6, (79, 153, 55)), (.8, (13, 91, 37)), (1.0, (2, 52, 24))]
    norm = np.clip((values + .2) / 1.2, 0, 1)
    channels = [np.interp(norm, [item[0] for item in stops], [item[1][i] for item in stops])
                .astype(np.uint8) for i in range(3)]
    rgba = np.dstack((*channels, valid.astype(np.uint8) * 205))
    return png_from_rgba(case_id, "ndvi", rgba,
                         {"status": "available", "product": "MOD13Q1", "version": "061",
                          "composite_start": "2024-07-11", "composite_window_days": 16,
                          "quality_filter": "pixel reliability 0 or 1; cloud, snow/ice and fill are transparent",
                          "source_granules": [item[0].name for item in data_files]})


IGBP = {
    1: (5, 69, 17), 2: (8, 106, 16), 3: (48, 139, 40), 4: (139, 170, 71),
    5: (20, 120, 55), 6: (200, 200, 60), 7: (223, 221, 84), 8: (202, 139, 26),
    9: (232, 186, 45), 10: (255, 255, 100), 11: (160, 180, 112), 12: (230, 60, 40),
    13: (165, 155, 143), 14: (210, 110, 80), 15: (245, 245, 245), 16: (190, 190, 190),
    17: (70, 110, 170),
}


def render_landcover(case_id: str):
    if case_id != "park-2024":
        return {"status": "unavailable", "reason": "No local MCD12Q1 annual layer covers this case year."}
    pairs = hdf_band(None, "land-cover", "MCD12Q1.A2024001.*.hdf", "LC_Type1", "IGBP")
    vrt = gdal.BuildVRT("", [item[1] for item in pairs])
    data = warp_to_case(vrt, case_id, source_nodata=255, destination_nodata=255,
                        data_type=gdal.GDT_Byte, resampling="near")
    values = data.ReadAsArray().astype(np.uint8)
    rgba = np.zeros((HEIGHT, WIDTH, 4), dtype=np.uint8)
    for code, color in IGBP.items():
        mask = values == code
        rgba[mask, :3] = color
        rgba[mask, 3] = 180
    rgba[values == 255, 3] = 0
    return png_from_rgba(case_id, "landcover", rgba,
                         {"status": "available", "product": "MCD12Q1", "version": "061",
                          "product_year": 2024, "classification": "IGBP LC_Type1, classes 1–17",
                          "source_granules": [item[0].name for item in pairs]})


def render_burned_area(case_id: str):
    if case_id != "park-2024":
        return {"status": "unavailable", "reason": "No local MCD64A1 files cover this case year."}
    data_files = []
    for start_day in ("2024183", "2024214"):
        data_files.extend(hdf_band(None, "burned-area", f"MCD64A1.A{start_day}.*.hdf", "Burn Date", "Burn Date"))
    by_period = defaultdict(list)
    for path, layer in data_files:
        by_period[path.name.split(".")[1]].append((path, layer))
    periods = []
    merged = np.full((HEIGHT, WIDTH), -9999, dtype=np.int16)
    for period, pairs in sorted(by_period.items()):
        vrt = gdal.BuildVRT("", [item[1] for item in pairs])
        data = warp_to_case(vrt, case_id, source_nodata=0, destination_nodata=-9999,
                            data_type=gdal.GDT_Int16, resampling="near")
        values = data.ReadAsArray().astype(np.int16)
        valid = (values >= 1) & (values <= 366)
        replace = valid & ((merged < 1) | (values < merged))
        merged[replace] = values[replace]
        periods.append({"month": "2024-07" if period.endswith("183") else "2024-08",
                        "granules": [item[0].name for item in pairs]})
    valid = (merged >= 1) & (merged <= 366)
    # Date ramp across this 2024 July-August window. Unburned/no-data pixels are transparent.
    day = np.clip(merged - 183, 0, 61).astype(np.float32) / 61
    r = np.interp(day, [0, .5, 1], [255, 247, 177]).astype(np.uint8)
    g = np.interp(day, [0, .5, 1], [190, 104, 39]).astype(np.uint8)
    b = np.interp(day, [0, .5, 1], [62, 42, 20]).astype(np.uint8)
    rgba = np.dstack((r, g, b, valid.astype(np.uint8) * 205))
    return png_from_rgba(case_id, "burned-area", rgba,
                         {"status": "available", "product": "MCD64A1", "version": "061",
                          "date_range": ["2024-07", "2024-08"], "periods": periods,
                          "interpretation": "Burn Date context, shown only where the monthly product contains a date. MODIS-dependent, lagged, and not independent validation."})


def main():
    if not (INPUTS / "terrain" / "norcal").is_dir():
        raise SystemExit("Local NASADEM input directory is missing; no files were downloaded.")
    manifest = {"schema": "fireatlas-replay-context-v1", "layers": {}}
    for case_id in CASES:
        manifest["layers"][case_id] = {"terrain": render_terrain(case_id)}
    manifest["layers"]["park-2024"].update({
        "ndvi": render_ndvi("park-2024"),
        "landcover": render_landcover("park-2024"),
        "burned-area": render_burned_area("park-2024"),
    })
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"manifest": str(path), "layers": manifest["layers"]}, indent=2))


if __name__ == "__main__":
    main()
