"""Curated, local documentation retrieval; no dataset fetching or arbitrary URLs."""
from __future__ import annotations
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILES = ("README.md", "docs/DATA.md", "docs/AI_USE.md", "docs/NATIVE_MASK_VALIDATION.md", "docs/NASA_DATA_IMPORT.md")
OFFICIAL = [
    {"title": "NASA FIRMS", "url": "https://firms.modaps.eosdis.nasa.gov/", "topic": "MODIS VIIRS active fire observations and availability"},
    {"title": "NASA documented Suomi-NPP processing gap", "url": "https://landweb.modaps.eosdis.nasa.gov/displayissue?id=716", "topic": "VIIRS Suomi NPP missing processing July 2024 gap"},
    {"title": "CAL FIRE Park incident reference", "url": "https://www.fire.ca.gov/incidents/2024/7/24/park-fire/", "topic": "Park Fire official incident reference"},
]


def search(query):
    words = set(re.findall(r"[a-z]{3,}", query.lower()))
    matches = []
    for name in FILES:
        path = ROOT/name
        if not path.is_file():
            continue
        for index, paragraph in enumerate(re.split(r"\n\s*\n",path.read_text(encoding="utf-8"))):
            score = len(words & set(re.findall(r"[a-z]{3,}",paragraph.lower())))
            if score:
                matches.append({"title": name, "paragraph": index+1, "excerpt": paragraph[:1500], "score": score, "kind": "project documentation"})
    return {"query": query, "passages": sorted(matches,key=lambda r:-r["score"])[:5], "official_links": [s for s in OFFICIAL if words & set(re.findall(r"[a-z]{3,}",s["topic"].lower()))], "note": "Local curated documentation. External links are references, not fetched observations or independent validation."}
