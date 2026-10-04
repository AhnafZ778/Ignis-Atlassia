"""Transparent, local prompt editing. No model call and no invented locations."""
import re
from ..replay import CASES
from .contracts import normalize_context


def prepare_question(question, context, selection=None):
    if not isinstance(question, str) or not question.strip() or len(question) > 1800:
        raise ValueError("Enter a question of at most 1,800 characters before adding study context.")
    cfg = normalize_context(context)
    cleaned = re.sub(r"\s+", " ", question).strip()
    issues, operation = [], None
    lower = cleaned.lower()
    if re.search(r"\b(hottest|hotter|temperature|severity)\b", lower):
        issues.append("Reported FRP measures radiative power, not ground temperature or severity. Keep sensor values separate.")
        operation = "replay"
    if re.search(r"\b(spread|simulate|simulation|forecast|predict)\b", lower):
        issues.append("This archive can compare observed locations over time; it cannot reconstruct continuous fire spread or predict the next location.")
        operation = "compare"
    if re.search(r"\b(previous|earlier|historical|archive|past fires)\b", lower):
        operation = "archive_search"
        issues.append("Search earlier detection windows in the selected boundary. Windows are not confirmed incidents.")
    if re.search(r"\b(gaps?|missing|incomplete)\b", lower):
        operation = "missingness"
    if re.search(r"\b(compare|overlap|agree)\b", lower) and "modis" in lower and "viirs" in lower:
        operation = "research"
        if cfg["start"][:7] != cfg["end"][:7]:
            issues.append("Sensor overlap uses one UTC month. Select the month explicitly before calculating it.")
    named = next((k for k in CASES if re.search(r"\b"+re.escape(k.split("-")[0])+r"(?:\s+fire)?\b", lower)), None)
    if named and named != cfg.get("case"):
        issues.append("Your question names a different saved fire. Switch studies, or explicitly request a comparison; this editor will not change your map.")
    scope = f"Study context: {cfg.get('case') or 'custom observation area'}; UTC {cfg['start']} through {cfg['end']}; west/south/east/north {', '.join(map(str,cfg['bbox']))}; source {cfg['source']}."
    if named and named != cfg.get("case"):
        scope = "Resolve the named fire from the saved catalog before querying its readings. The map currently shows another study. " + scope
    selected = ""
    if isinstance(selection, dict) and selection.get("result_id") and selection.get("path"):
        selected = f" Inspect the selected returned observation at {str(selection['path'])[:200]} in result {str(selection['result_id'])[:100]}."
    boundary = "Use archive tools and checked source values. Keep MODIS and VIIRS readings separate; report units and completeness. Distinguish missing data from zero. Show or annotate actual returned cells when relevant."
    if issues: boundary += " " + " ".join(issues)
    return {"original": question, "suggested_question": cleaned+"\n\n"+scope+selected+"\n"+boundary, "issues": issues, "suggested_operation": operation, "named_case": named, "context_changed": False, "kind": "local rule-based prompt editor; no AI request"}
