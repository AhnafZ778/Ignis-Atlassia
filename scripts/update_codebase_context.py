"""Generate the LLM source index and detect inventory drift without importing the app.

Run from any directory with Python 3.10+: write with no arguments; verify with --check.
Only source/configuration is inspected; local databases and credentials are excluded.
Human-written segment guides still require review after behavior changes.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "context"
ROOT_FILES = {"README.md", "PRD.md", "PROJECT_DETAILS.md", "pyproject.toml", "uv.lock", ".gitignore", ".gitattributes", "earth.html", "Globe.html", "fireatlas_terrain_fixed.html"}
SOURCE_ROOTS = {"fireatlas", "scripts", "tests", "studio-app", "studio-mcp-app", "studio-render", "requirements"}
SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".html", ".css", ".json", ".toml", ".yml", ".yaml", ".sh", ".in", ".txt", ".lock", ".md", ".mts"}
SKIP_PARTS = {"node_modules", "__pycache__", "dist", "build", "coverage", "test-results", "playwright-report", ".vite"}
SKIP_PREFIXES = ("fireatlas/static/studio-assets/", "fireatlas/static/studio-mcp/", "fireatlas/static/vendor/", "fireatlas/static/fonts/", "fireatlas/static/incident-media/", "fireatlas/static/replay-context/", "fireatlas/samples/")
SEGMENTS = [
    ("Core science and acquisition", lambda p: p.startswith("fireatlas/") and "/" not in p[len("fireatlas/"):] and p.endswith(".py")),
    ("Scientific assistant", lambda p: p.startswith("fireatlas/assistant/")),
    ("Studio backend", lambda p: p.startswith("fireatlas/studio/")),
    ("Analytical browser sources", lambda p: p.startswith("fireatlas/static/")),
    ("Studio browser sources and build", lambda p: p.startswith("studio-app/")),
    ("MCP Apps browser", lambda p: p.startswith("studio-mcp-app/")),
    ("Video renderer", lambda p: p.startswith("studio-render/")),
    ("Scripts", lambda p: p.startswith("scripts/")),
    ("Tests", lambda p: p.startswith("tests/")),
    ("Runtime, release, and project references", lambda p: True),
]


def git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def selected(name):
    p = Path(name)
    if any(part in SKIP_PARTS for part in p.parts) or name.startswith(SKIP_PREFIXES):
        return False
    if any(part.startswith(".env") for part in p.parts):
        return False
    if name in ROOT_FILES:
        return True
    if name.startswith(".github/workflows/"):
        return p.suffix in {".yaml", ".yml"}
    return bool(p.parts and p.parts[0] in SOURCE_ROOTS and p.suffix in SUFFIXES)


def sha256(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def python_outline(text):
    tree = ast.parse(text)
    symbols, imports, env = [], set(), set()

    def visit(nodes, prefix=""):
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [a.arg for a in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]]
                if node.args.vararg:
                    args.append("*" + node.args.vararg.arg)
                if node.args.kwarg:
                    args.append("**" + node.args.kwarg.arg)
                symbols.append({"name": prefix + node.name, "line": node.lineno, "kind": "function", "arguments": args})
            elif isinstance(node, ast.ClassDef):
                symbols.append({"name": prefix + node.name, "line": node.lineno, "kind": "class"})
                visit(node.body, prefix + node.name + ".")
    visit(tree.body)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add("." * node.level + (node.module or ""))
        elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            if ast.unparse(node.func) in {"os.getenv", "os.environ.get", "environ.get", "getenv"}:
                env.add(node.args[0].value)
        elif isinstance(node, ast.Subscript) and ast.unparse(node.value) == "os.environ" and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            env.add(node.slice.value)
    return (ast.get_docstring(tree) or "").split("\n")[0], symbols, sorted(imports), sorted(env)


def record(name):
    file = ROOT / name
    result = {"path": name, "sha256": sha256(file), "bytes": file.stat().st_size}
    if file.suffix == ".lock" or file.name == "package-lock.json":
        result["purpose"] = "Dependency lockfile; use the matching runtime install command."
        return result
    text = file.read_text(encoding="utf-8")
    result["lines"] = len(text.splitlines())
    if file.suffix == ".py":
        purpose, symbols, imports, env = python_outline(text)
        result.update(purpose=purpose, symbols=symbols, imports=imports, environment_keys=env)
    elif file.suffix in {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".mts"}:
        # Navigation aid only: this is not a complete JS/TS parser or call graph.
        result["symbols"] = [{"name": m.group(1), "line": text.count("\n", 0, m.start()) + 1, "kind": "export"}
            for m in re.finditer(r"(?m)^export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let|interface|type)\s+([A-Za-z_$][\w$]*)", text)]
        result["imports"] = sorted(set(re.findall(r"(?:from\s*|import\s*\(\s*|require\s*\(\s*)['\"]([^'\"]+)['\"]", text)))
    elif file.suffix == ".html":
        result["scripts"] = re.findall(r"<script\b[^>]*\bsrc=['\"]([^'\"]+)['\"]", text, flags=re.I)
    return result


def build():
    names = set(git("ls-files", "--cached", "--others", "--exclude-standard", "-z").decode().split("\0"))
    records = [record(name) for name in sorted(names) if selected(name) and (ROOT / name).is_file() and not (ROOT / name).is_symlink()]
    revision = git("rev-parse", "HEAD").decode().strip()
    manifest = {"schema": "fireatlas-codebase-context-inventory-v1", "base_commit": revision,
        "scope": "Authored source, configuration, tests, build scripts, and selected root references; excludes private inputs, generated bundles, vendor code, and historical docs.",
        "files": records}
    tick = chr(96)
    code = lambda value: tick + value + tick
    lines = ["# Generated source index", "",
        "Generated by " + code("python3 scripts/update_codebase_context.py") + ". Do not edit by hand.", "",
        "Start with [the context entry point](../../CODEBASE_CONTEXT.md); load only the relevant segment and symbols.", "",
        "Static navigation index, not runtime verification. Python symbols use AST; JS/TS exports and imports use a lexical scan. Dynamic and inline browser functions require source inspection.", "",
        "Base commit: " + code(revision) + ". Entries describe current worktree files, including uncommitted source.", "",
        f"Indexed files: {len(records)}. Full hashes, symbols, imports, and Python environment key names: [source-manifest.json](source-manifest.json). No environment values are read.", ""]
    for title, accepts in SEGMENTS:
        group = [item for item in records if accepts(item["path"])]
        records = [item for item in records if not accepts(item["path"])]
        if not group:
            continue
        lines += ["## " + title, ""]
        for item in group:
            name = item["path"]
            lines += [f"### [{name}](../../{name})", "", "SHA-256: " + code(item["sha256"][:16] + "…") + f"; {item['bytes']:,} bytes" + (f"; {item['lines']:,} lines." if "lines" in item else "."), ""]
            if item.get("purpose"):
                lines += [item["purpose"], ""]
            if item.get("symbols"):
                lines += ["Symbols: " + ", ".join(code(s["name"]) + " (L" + str(s["line"]) + ")" for s in item["symbols"]) + ".", ""]
            if item.get("imports"):
                lines += ["Imports: " + ", ".join(code(value) for value in item["imports"]) + ".", ""]
            if item.get("scripts"):
                lines += ["Scripts: " + ", ".join(code(value) for value in item["scripts"]) + ".", ""]
            if item.get("environment_keys"):
                lines += ["Environment key names: " + ", ".join(code(value) for value in item["environment_keys"]) + ".", ""]
    return {"source-manifest.json": json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", "SOURCE_INDEX.md": "\n".join(lines)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Exit nonzero for a stale inventory/index; writes nothing.")
    args = parser.parse_args()
    outputs = build()
    stale = [name for name, body in outputs.items() if not (OUTPUT / name).exists() or (OUTPUT / name).read_text(encoding="utf-8") != body]
    if args.check:
        if stale:
            print("Context inventory is stale: " + ", ".join(stale) + ". Review affected segment guides, then run python3 scripts/update_codebase_context.py.")
            return 1
        print("Context source inventory and symbol index are current. Human-written behavior notes still require review.")
        return 0
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, body in outputs.items():
        (OUTPUT / name).write_text(body, encoding="utf-8")
    count = len(json.loads(outputs["source-manifest.json"])["files"])
    print(f"Updated context source index and inventory ({count} files). Review curated segment notes separately.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
