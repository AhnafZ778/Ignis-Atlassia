"""Truthful capability state for every optional Studio integration.

Nothing here probes the network. Each entry says whether the feature can run now and, if not, exactly why.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "fireatlas" / "static"
RENDER_DIR = ROOT / "studio-render"
LIMITS = {"cards_per_board": 100, "chapters_per_story": 24, "workflow_nodes": 40, "live_maps": 2, "expanded_terrain_views": 1,
          "render_jobs_at_a_time": 1, "narration_segment_characters": 800, "narration_daily_characters": 4000,
          "workflow_records": 5000, "workflow_tool_calls": 8, "workflow_seconds": 120}
LICENSE_ACKS = ("free-eligible", "company-license")


def features():
    """Which optional editor modules the committed Studio build actually contains."""
    path = STATIC / "studio-assets" / "features.json"
    if path.is_file():
        try:
            return json.loads(path.read_text())
        except ValueError:
            return {}
    return {}


def canvas():
    built = bool(features().get("tldraw"))
    key = bool(os.getenv("FIREATLAS_TLDRAW_LICENSE_KEY"))
    if built and key:
        return {"tldraw": {"available": True, "reason": None}, "active": "tldraw", "public_license_key": os.getenv("FIREATLAS_TLDRAW_LICENSE_KEY")}
    reason = ("The Studio build does not include tldraw." if not built else
              "Set FIREATLAS_TLDRAW_LICENSE_KEY to a tldraw license key to enable the tldraw canvas.")
    return {"tldraw": {"available": False, "reason": reason}, "active": "outline-board",
            "message": "Using the built-in card board and linear outline. Evidence inspection and story reading are unaffected."}


def workflow_editor():
    if features().get("reactflow"):
        return {"react_flow": {"available": True, "reason": None}, "active": "react-flow"}
    return {"react_flow": {"available": False, "reason": "The Studio build does not include React Flow."}, "active": "linear-outline"}


def video(node=None):
    node = node or shutil.which("node")
    from .resources import monitor_available
    if not monitor_available():
        return {"available": False, "reason": "Local video needs the Linux process-resource monitor. Story editing and reader exports remain available."}
    if os.getenv("FIREATLAS_STUDIO_LOCAL_RENDER", "").lower() in {"1", "true", "yes", "on"}:
        ffmpeg = shutil.which("ffmpeg")
        browser = next((shutil.which(name) for name in ("chromium", "chromium-browser", "google-chrome") if shutil.which(name)), None)
        if ffmpeg and browser and node:
            return {"available": True, "reason": None, "engine": "local-svg-ffmpeg", "profile": "briefing-1080p-landscape",
                    "rasterizer": "chromium",
                    "disclosure": "Local documentary render with schematic scene fallbacks and captions; no live imagery is embedded."}
        return {"available": False, "reason": "Local rendering needs Node.js, ffmpeg and Chromium/Google Chrome."}
    if not node:
        return {"available": False, "reason": "Node.js is required to render video."}
    if not shutil.which('ffmpeg'):
        return {"available": False, "reason": "ffmpeg is required to embed frozen subtitles and assemble optional narration."}
    if not (RENDER_DIR / "node_modules" / "remotion").is_dir():
        return {"available": False, "reason": "Run npm ci in studio-render/ to install Remotion."}
    ack = os.getenv("FIREATLAS_REMOTION_LICENSE_ACK", "")
    if ack not in LICENSE_ACKS:
        return {"available": False, "reason": "Remotion needs a license decision: set FIREATLAS_REMOTION_LICENSE_ACK to 'free-eligible' "
                                              "(eligible individual or organization of up to three people under current Remotion terms) or 'company-license' (you hold the applicable Remotion license)."}
    if not (RENDER_DIR / "render.mjs").is_file():
        return {"available": False, "reason": "The Remotion renderer entry point is missing."}
    return {"available": True, "reason": None, "license_acknowledgement": ack, "profile": "briefing-1080p-landscape"}


def narration():
    if os.getenv("FIREATLAS_AI_PROVIDER") == "openrouter":
        return {"available": False, "reason": "Paid speech is disabled in free-only mode. Captions and transcript remain available."}
    if not os.getenv("OPENAI_API_KEY") or importlib.util.find_spec("openai") is None:
        return {"available": False, "reason": "A server-side OPENAI_API_KEY and the openai package are required. Captions and transcript remain available."}
    if not shutil.which('ffprobe'):
        return {"available": False, "reason": "ffprobe is required to verify generated speech duration before rendering. Captions and transcript remain available."}
    try:
        rate = float(os.getenv("FIREATLAS_TTS_MAX_REQUEST_USD", "0"))
        budget = float(os.getenv("FIREATLAS_STUDIO_NARRATION_MAX_USD", "0"))
    except ValueError:
        rate = budget = 0.0
    import math
    if not math.isfinite(rate) or not math.isfinite(budget) or not rate > 0 or not budget > 0:
        return {"available": False, "reason": "Set FIREATLAS_TTS_MAX_REQUEST_USD and FIREATLAS_STUDIO_NARRATION_MAX_USD to verified positive amounts."}
    return {"available": True, "reason": None, "disclosure": "AI-generated voice; checked fields cite frozen evidence and explanatory prose remains authored interpretation. Not an eyewitness account.",
            "per_request_usd": rate, "story_budget_usd": budget}


def mcp_apps():
    if importlib.util.find_spec("fastmcp") is None:
        return {"available": False, "reason": "Install the assistant extra (fastmcp) to run the private stdio MCP server.",
                "fallback": "text and JSON results"}
    if not (STATIC / "studio-mcp/index.html").is_file():
        return {"available": False, "reason": "Run npm ci and npm run build in studio-mcp-app/ to prepare the MCP Apps SDK resource.", "fallback": "text and JSON results"}
    return {"available": True, "reason": None, "transport": "stdio (private)", "resource": "ui://fireatlas/studio/app.html",
            "host_status": "external client not verified", "fallback": "text and JSON results when the host lacks MCP Apps"}


def describe(collaboration, store_version, science_operations=None, release=None):
    from .context_layers import catalog
    from .resources import CPU_SECONDS, FREE_HEADROOM, MEMORY_LIMIT, STORAGE_FILES, STORAGE_LIMIT
    return {"schema": "fireatlas-studio-capabilities-v1", "store_version": store_version, "canvas": canvas(), "workflow": workflow_editor(),
            "video": video(), "narration": narration(), "collaboration": collaboration.describe(), "mcp_apps": mcp_apps(),
            "static_reader": {"available": True, "authoring": "local service only"}, "context_layers": catalog()['layers'], "limits": LIMITS,
            "operations": list(science_operations or []), "release": release,
            "render_resources": {"summed_resident_bytes": MEMORY_LIMIT, "sampled_cpu_seconds": CPU_SECONDS,
                                 "retained_storage_bytes": STORAGE_LIMIT, "retained_file_limit": STORAGE_FILES,
                                 "free_disk_headroom_bytes": FREE_HEADROOM, "sampling_seconds": .2,
                                 "policy": "Sampled process limits and storage admission; no automatic deletion of completed exports."}}
