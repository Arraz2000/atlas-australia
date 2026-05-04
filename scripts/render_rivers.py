#!/usr/bin/env python3
"""
Australian River Basin Map
Renders drainage divisions as coloured river networks on a dark background.
Inspired by the IDV Solutions US river basin map.

Usage:
  python3 render_rivers.py              # uses HR_Catchments AHGFLink (35k lines, fast)
  python3 render_rivers.py --full       # uses SH_Network (detailed, slow — run after download)
"""

import sys
import argparse
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

BASE = Path(__file__).parent.parent / "data" / "geofabric"

HR_REGIONS_GDB  = BASE / "HR_Regions/HR_Regions_GDB/HR_Regions.gdb"
HR_CATCHMENTS_GDB = BASE / "HR_Catchments/HR_Catchments_GDB/HR_Catchments.gdb"
SH_NETWORK_GDB  = BASE / "SH_Network/SH_Network_GDB/SH_Network.gdb"

OUTPUT = Path(__file__).parent.parent / "output"

# 13 drainage divisions — hand-picked colours (inspired by river basin palette)
DIVISION_COLOURS = {
    "1":   "#4FC3F7",  # North East Coast       — light blue
    "2a":  "#81C784",  # South East Coast (NSW) — green
    "2b":  "#AED581",  # South East Coast (VIC) — lime
    "3":   "#F06292",  # Tasmania               — pink
    "4":   "#FFD54F",  # Murray-Darling         — amber/gold
    "5":   "#FF8A65",  # South Australian Gulf  — orange
    "6":   "#CE93D8",  # South Western Plateau  — lavender
    "7":   "#80DEEA",  # South West Coast       — cyan
    "8":   "#EF9A9A",  # Pilbara-Gascoyne       — salmon
    "9":   "#B0BEC5",  # North Western Plateau  — grey-blue
    "10":  "#A5D6A7",  # Tanami-Timor Sea Coast — mint
    "11":  "#FFCC80",  # Lake Eyre Basin        — pale gold
    "12":  "#4DB6AC",  # Carpentaria Coast      — teal
}

def load_divisions():
    print("Loading drainage divisions...")
    gdf = gpd.read_file(HR_REGIONS_GDB, layer="AWRADrainageDivision")
    gdf = gdf.to_crs("EPSG:4326")
    gdf["colour"] = gdf["DivNumber"].map(DIVISION_COLOURS)
    gdf["colour"] = gdf["colour"].fillna("#888888")
    return gdf

def load_rivers_hr():
    print("Loading HR river network (AHGFLink, 35k lines)...")
    rivers = gpd.read_file(HR_CATCHMENTS_GDB, layer="AHGFLink")
    rivers = rivers.to_crs("EPSG:4326")
    return rivers

def load_rivers_sh():
    print("Loading SH river network (AHGFNetworkStream, filtered to top 15% by drainage area)...")
    # 2.5M total features — filter to ~375k for manageable render
    # UpstrDArea 85th pct ≈ 113M — keeps major + mid-tier rivers, drops tiny streams
    rivers = gpd.read_file(
        SH_NETWORK_GDB, layer="AHGFNetworkStream",
        where="UpstrDArea > 113000000"
    )
    rivers = rivers.to_crs("EPSG:4326")
    print(f"  Loaded {len(rivers):,} features")
    rivers["weight"] = rivers["UpstrDArea"].fillna(0)
    return rivers

def assign_basin_colours(rivers, divisions):
    # Explode MultiLineStrings → individual LineStrings to eliminate straight-line artifacts
    print(f"Exploding {len(rivers):,} features into individual line segments...")
    rivers = rivers.explode(index_parts=False).reset_index(drop=True)
    print(f"  → {len(rivers):,} line segments after explode")

    # Filter out artefact lines with implausibly large extent (>2° in any direction)
    bounds = rivers.geometry.bounds
    span_x = bounds["maxx"] - bounds["minx"]
    span_y = bounds["maxy"] - bounds["miny"]
    before = len(rivers)
    rivers = rivers[(span_x < 2) & (span_y < 2)]
    print(f"  → {len(rivers):,} after removing {before - len(rivers)} artefact lines (span >2°)")

    print(f"Spatial join: assigning basin colour to {len(rivers):,} river lines...")
    # Use representative point (midpoint) for join — much faster than full line intersection
    rivers = rivers.copy()
    rivers["_geom_orig"] = rivers.geometry
    rivers["geometry"] = rivers.geometry.representative_point()
    joined = gpd.sjoin(rivers, divisions[["DivNumber","Division","colour","geometry"]],
                       how="left", predicate="within")
    joined["geometry"] = joined["_geom_orig"]
    joined["colour"] = joined["colour"].fillna("#555555")
    return joined.drop(columns=["_geom_orig"])

def render(divisions, rivers, output_path, title="Australian River Basins", dpi=300):
    print(f"Rendering at {dpi} dpi → {output_path}")

    fig, ax = plt.subplots(1, 1, figsize=(20, 22))
    fig.patch.set_facecolor("#0a0a0f")
    ax.set_facecolor("#0a0a0f")

    # Draw drainage division fills (very subtle — dark tint)
    for _, row in divisions.iterrows():
        colour = row.get("colour", "#333333")
        divisions_subset = divisions[divisions["DivNumber"] == row["DivNumber"]]
        divisions_subset.plot(ax=ax, color=colour, alpha=0.06, linewidth=0)

    # Draw drainage division borders (faint)
    divisions.boundary.plot(ax=ax, color="#333344", linewidth=0.3, alpha=0.5)

    # Draw rivers grouped by colour, with line width scaled by drainage area if available
    colours = rivers["colour"].unique()
    has_weight = "weight" in rivers.columns
    if has_weight:
        max_w = rivers["weight"].quantile(0.999)
    for colour in colours:
        subset = rivers[rivers["colour"] == colour]
        if has_weight and max_w > 0:
            # Bin into 4 weight tiers for performance
            w = subset["weight"].clip(0, max_w) / max_w
            for lw, alpha, mask in [
                (1.2, 0.9, w > 0.05),   # major rivers
                (0.6, 0.7, (w > 0.001) & (w <= 0.05)),  # mid
                (0.3, 0.5, w <= 0.001),  # minor
            ]:
                s = subset[mask]
                if len(s): s.plot(ax=ax, color=colour, linewidth=lw, alpha=alpha)
        else:
            subset.plot(ax=ax, color=colour, linewidth=0.4, alpha=0.7)

    # Legend
    legend_entries = []
    div_lookup = divisions.drop_duplicates("DivNumber").set_index("DivNumber")
    for divnum, colour in sorted(DIVISION_COLOURS.items(), key=lambda x: x[0]):
        if divnum in div_lookup.index:
            name = div_lookup.loc[divnum, "Division"]
            legend_entries.append(mpatches.Patch(color=colour, label=f"{divnum}. {name}"))

    ax.legend(
        handles=legend_entries,
        loc="lower left",
        fontsize=7,
        framealpha=0.15,
        facecolor="#0a0a0f",
        edgecolor="#444455",
        labelcolor="white",
        title="Drainage Divisions",
        title_fontsize=8,
    )

    ax.set_title(title, color="white", fontsize=16, pad=12, fontweight="bold")
    ax.axis("off")

    # Remove padding
    ax.set_xlim(divisions.total_bounds[0] - 1, divisions.total_bounds[2] + 1)
    ax.set_ylim(divisions.total_bounds[1] - 1, divisions.total_bounds[3] + 1)

    plt.tight_layout(pad=0.5)
    plt.savefig(output_path, dpi=dpi, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close()
    print(f"Saved: {output_path}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true",
                        help="Use SH_Network (full detail) instead of HR_Catchments")
    parser.add_argument("--dpi", type=int, default=300)
    args = parser.parse_args()

    OUTPUT.mkdir(exist_ok=True)
    divisions = load_divisions()

    if args.full:
        if not SH_NETWORK_GDB.exists():
            print(f"ERROR: SH_Network not found at {SH_NETWORK_GDB}")
            print("Still downloading? Check: ls -lh ~/atlas-australia/data/geofabric/SH_Network_GDB_V3_3.zip")
            sys.exit(1)
        rivers = load_rivers_sh()
        suffix = "full"
    else:
        rivers = load_rivers_hr()
        suffix = "preview"

    rivers_coloured = assign_basin_colours(rivers, divisions)

    out_file = OUTPUT / f"australia_rivers_{suffix}.png"
    render(divisions, rivers_coloured, out_file, dpi=args.dpi)
    print("Done!")

if __name__ == "__main__":
    main()
