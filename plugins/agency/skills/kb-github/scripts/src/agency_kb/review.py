"""Review: discover gaps in KB coverage and report uncovered files."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from agency_kb.schemas import ExportedOutline

_SOURCE_EXTENSIONS = {
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".py",
    ".go",
    ".rs",
    ".java",
    ".rb",
    ".swift",
    ".kt",
    ".vue",
    ".svelte",
}
_IGNORE_DIRS = {
    "node_modules",
    ".git",
    "__pycache__",
    ".next",
    "dist",
    "build",
    ".venv",
    "venv",
    ".agency-kb",
    ".agency-knows",
    "coverage",
}


def find_uncovered_files(
    *,
    repo_root: Path,
    outline: ExportedOutline,
) -> list[str]:
    """Find source files not covered by any article's globs or explicit file lists."""
    covered: set[str] = set()

    for doc in outline.documents:
        for f in doc.files:
            covered.add(f)
        for pattern in doc.globs:
            expanded = pattern + "/*" if pattern.endswith("**") else pattern
            for match in repo_root.glob(expanded):
                if match.is_file():
                    covered.add(match.relative_to(repo_root).as_posix())

    all_files: list[str] = []

    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in _SOURCE_EXTENSIONS:
            continue
        rel = path.relative_to(repo_root).as_posix()
        parts = rel.split("/")
        if any(part in _IGNORE_DIRS for part in parts):
            continue
        if rel not in covered:
            all_files.append(rel)

    return sorted(all_files)


def group_by_directory(files: list[str]) -> dict[str, list[str]]:
    """Group files by their top-level directory for readable output."""
    groups: dict[str, list[str]] = defaultdict(list)
    for f in files:
        parts = f.split("/")
        key = parts[0] if len(parts) > 1 else "."
        groups[key].append(f)
    return dict(sorted(groups.items()))


def write_review_report(
    *,
    output_path: Path,
    uncovered_files: list[str],
    existing_article_count: int,
    collection_id: str,
) -> None:
    """Write a JSON report of uncovered files to the review directory."""
    grouped = group_by_directory(uncovered_files)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "collection_id": collection_id,
                "existing_articles": existing_article_count,
                "uncovered_file_count": len(uncovered_files),
                "uncovered_by_directory": grouped,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
