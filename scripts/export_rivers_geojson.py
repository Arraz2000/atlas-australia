#!/usr/bin/env python3
"""
Export river network to GeoJSON with basin colour + weight for PMTiles conversion.
Run: /usr/bin/python3 export_rivers_geojson.py
"""
import sys, json
from pathlib import Path
import geopandas as gpd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from render_rivers import (
    SH_NETWORK_GDB, HR_REGIONS_GDB, DIVISION_COLOURS,
    load_divisions, assign_basin_colours, OUTPUT
)

OUT_GEOJSON = OUTPUT / "rivers.geojson"

print("Loading divisions...")
divisions = load_divisions()

print("Loading river network (top 30% by drainage area)...")
rivers = gpd.read_file(SH_NETWORK_GDB, layer="AHGFNetworkStream",
                       where="UpstrDArea > 19500000")
rivers = rivers.to_crs("EPSG:4326")
print(f"  {len(rivers):,} features loaded")

rivers["weight"] = rivers["UpstrDArea"].fillna(0)

print("Assigning basin colours...")
rivers_c = assign_basin_colours(rivers, divisions)

# Normalise weight to 0-1 scale for use as line-width expression in MapLibre
max_w = rivers_c["weight"].quantile(0.999)
rivers_c["w"] = (rivers_c["weight"].clip(0, max_w) / max_w).round(4)

# Keep only fields needed for rendering
out = rivers_c[["geometry", "colour", "w", "DivNumber", "Division", "Name"]].copy()
out = out.rename(columns={"Name": "river_name", "DivNumber": "div", "Division": "basin"})

print(f"Writing {OUT_GEOJSON}...")
out.to_file(OUT_GEOJSON, driver="GeoJSON")
print(f"Done — {OUT_GEOJSON.stat().st_size/1e6:.1f} MB")
