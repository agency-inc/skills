"""Scan a repository to build a structural summary."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

# Directories to always skip
_SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".next",
    "dist",
    "build",
    ".agency-kb",
    ".turbo",
    "coverage",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}

# Extensions worth including in the tree
_CODE_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".go",
    ".rs",
    ".java",
    ".rb",
    ".swift",
    ".kt",
    ".cs",
    ".vue",
    ".svelte",
}

_CONFIG_FILES = {
    "package.json",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
    "Gemfile",
    "build.gradle",
    "pom.xml",
    "Makefile",
    "justfile",
    "docker-compose.yml",
    "Dockerfile",
}

_MAX_SYMBOLS_PER_FILE = 8


def scan_repo_structure(repo_root: Path, *, max_depth: int = 4) -> str:
    """Build a compact tree of the repo showing directories and key files."""
    lines: list[str] = []
    _walk_tree(repo_root, repo_root, lines, depth=0, max_depth=max_depth)
    return "\n".join(lines)


def _walk_tree(
    root: Path,
    current: Path,
    lines: list[str],
    *,
    depth: int,
    max_depth: int,
) -> None:
    if depth > max_depth:
        return

    indent = "  " * depth
    rel = current.relative_to(root)
    dir_name = current.name or str(rel)

    if depth > 0:
        lines.append(f"{indent}{dir_name}/")

    try:
        entries = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        return

    dirs: list[Path] = []
    files: list[Path] = []
    for entry in entries:
        if entry.name.startswith(".") and entry.name not in (".github",):
            continue
        if entry.is_dir():
            if entry.name not in _SKIP_DIRS:
                dirs.append(entry)
        elif entry.is_file():
            files.append(entry)

    for f in files:
        if f.suffix in _CODE_EXTENSIONS or f.name in _CONFIG_FILES or f.name == "README.md":
            lines.append(f"{indent}  {f.name}")

    for d in dirs:
        _walk_tree(root, d, lines, depth=depth + 1, max_depth=max_depth)


def scan_route_files(repo_root: Path) -> list[dict[str, str]]:
    """Find route/page definitions that reveal the product's navigation structure."""
    routes: list[dict[str, str]] = []

    # Next.js App Router pages
    for page in repo_root.rglob("**/app/**/page.tsx"):
        if _should_skip(page):
            continue
        rel = page.relative_to(repo_root).as_posix()
        route = _nextjs_path_to_route(rel)
        routes.append({"file": rel, "route": route, "framework": "nextjs"})

    for page in repo_root.rglob("**/app/**/page.jsx"):
        if _should_skip(page):
            continue
        rel = page.relative_to(repo_root).as_posix()
        route = _nextjs_path_to_route(rel)
        routes.append({"file": rel, "route": route, "framework": "nextjs"})

    # Python FastAPI routers
    for router_file in repo_root.rglob("**/router*.py"):
        if _should_skip(router_file):
            continue
        rel = router_file.relative_to(repo_root).as_posix()
        routes.append({"file": rel, "route": "", "framework": "fastapi"})

    return routes


def _should_skip(path: Path) -> bool:
    return any(part in _SKIP_DIRS for part in path.parts)


def _nextjs_path_to_route(file_path: str) -> str:
    """Convert a Next.js app router file path to its URL route."""
    route = file_path
    # Remove everything up to and including /app/
    if "/app/" in route:
        route = route.split("/app/", 1)[1]
    # Remove page.tsx/page.jsx
    route = re.sub(r"page\.(tsx|jsx)$", "", route).rstrip("/")
    # Remove route groups like (main)
    route = re.sub(r"\([^)]+\)/", "", route)
    return f"/{route}" if route else "/"


def extract_symbols(content: str, *, suffix: str) -> list[str]:
    """Extract top-level symbol names from a source file."""
    if suffix == ".py":
        pattern = re.compile(r"^(?:async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
    elif suffix in {".ts", ".tsx", ".js", ".jsx"}:
        pattern = re.compile(
            r"^(?:export\s+)?(?:async\s+function|function|class|const|let|var|interface|type)"
            r"\s+([A-Za-z_][A-Za-z0-9_]*)",
            re.MULTILINE,
        )
    else:
        return []

    ordered: list[str] = []
    for match in pattern.findall(content):
        if match not in ordered:
            ordered.append(match)
        if len(ordered) >= _MAX_SYMBOLS_PER_FILE:
            break
    return ordered


def get_readme_content(repo_root: Path) -> str:
    """Read the repo's root README if it exists."""
    for name in ("README.md", "readme.md", "README.rst", "README"):
        readme = repo_root / name
        if readme.is_file():
            content = readme.read_text(encoding="utf-8", errors="ignore")
            # Truncate long READMEs
            if len(content) > 8000:
                return content[:8000] + "\n\n... (truncated)"
            return content
    return ""


def run_git_command(*, repo_root: Path, args: list[str]) -> list[str]:
    result = subprocess.run(  # noqa: S603, S607
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]
