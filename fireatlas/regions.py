"""Named analysis regions used by the harmonized archive workflow."""

from __future__ import annotations

REGIONS = {
    "norcal": {
        "id": "norcal",
        "name": "Northern California",
        "bbox": (-122.2, 38.8, -120.0, 41.0),
        "description": "Mediterranean-climate forests and shrublands with a summer fire season.",
    },
    "punjab-haryana": {
        "id": "punjab-haryana",
        "name": "Punjab–Haryana",
        "bbox": (73.8, 29.5, 77.6, 32.6),
        "description": "Agricultural landscapes where seasonal crop-residue burning is a major signal.",
    },
}

PRODUCTS = {"MODIS_SP": "MODIS_SP", "VIIRS_SNPP_SP": "VIIRS_SNPP_SP"}


def contains_bbox(outer, inner) -> bool:
    """Return whether outer fully contains inner, in west/south/east/north order."""
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


def intersects_bbox(a, b) -> bool:
    return a[0] <= b[2] and a[2] >= b[0] and a[1] <= b[3] and a[3] >= b[1]
