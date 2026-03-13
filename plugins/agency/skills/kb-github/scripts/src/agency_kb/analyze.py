"""Analyze: resolve file patterns and score relevance for each outline document."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import rich

from agency_kb.repo_scanner import extract_symbols, run_git_command
from agency_kb.schemas import (
    AnalyzedDocument,
    AnalyzedFile,
    CandidateScore,
    ExportedOutline,
    ExportedOutlineDocument,
    GitChangeSet,
    MatchResolution,
    OutlineAnalysis,
    ScopedFile,
)

_WILDCARD_CHARS = ("*", "?", "[")
_MIN_TOKEN_LENGTH = 2
_RELEVANT_FILE_SCORE_THRESHOLD = 6
_CANDIDATE_FILE_SCORE_THRESHOLD = 3


def run_analyze(
    *,
    outline: ExportedOutline,
    repo_root: Path,
    diff_base: str | None = None,
    document_path: str | None = None,
    source_id: str | None = None,
) -> OutlineAnalysis:
    git_changes = _get_git_changes(repo_root=repo_root, diff_base=diff_base)
    analyzed_documents: list[AnalyzedDocument] = []

    for document in outline.documents:
        if not _matches_filter(document=document, document_path=document_path, source_id=source_id):
            continue

        resolution = _resolve_matches(
            repo_root=repo_root,
            files=document.files,
            globs=document.globs,
        )
        explicit_file_set = set(document.files)
        analyzed_by_path = {
            path: _analyze_file(repo_root=repo_root, relative_path=path)
            for path in resolution.matched_files
        }
        relevant_files = sorted(
            path for path in resolution.matched_files if path in explicit_file_set
        )
        candidate_files: list[ScopedFile] = []
        ignored_files: list[ScopedFile] = []

        for path in sorted(set(resolution.matched_files) - explicit_file_set):
            analyzed_file = analyzed_by_path[path]
            score = _score_candidate_file(
                document=document, file_path=path, analyzed_file=analyzed_file
            )
            if score.score >= _RELEVANT_FILE_SCORE_THRESHOLD:
                relevant_files.append(path)
            elif score.score >= _CANDIDATE_FILE_SCORE_THRESHOLD:
                candidate_files.append(ScopedFile(path=path, reason=score.reason))
            else:
                ignored_files.append(ScopedFile(path=path, reason=score.reason))

        relevant_files = sorted(set(relevant_files))
        changed = [p for p in relevant_files if p in git_changes.changed_files]
        new = [p for p in relevant_files if p in git_changes.new_files]
        all_known_paths = set(document.files) | set(resolution.matched_files)
        deleted = [p for p in git_changes.deleted_files if p in all_known_paths]
        analyzed_files = [analyzed_by_path[p] for p in relevant_files if p in analyzed_by_path]

        analyzed_documents.append(
            AnalyzedDocument(
                document_id=document.document_id,
                title=document.title,
                document_path=document.document_path,
                source_id=document.source_id,
                files=document.files,
                globs=document.globs,
                outline_markdown=document.outline_markdown,
                relevant_files=relevant_files,
                changed_files=changed,
                new_files=new,
                deleted_files=deleted,
                has_matching_changes=bool(changed or new or deleted),
                candidate_files=candidate_files,
                ignored_files=ignored_files,
                missing_files=resolution.missing_files,
                unmatched_globs=resolution.unmatched_globs,
                analyzed_files=analyzed_files,
            )
        )

    rich.print(f"[green]Analyzed {len(analyzed_documents)} documents[/green]")

    return OutlineAnalysis(
        analyzed_at=datetime.now(UTC),
        repo_root=repo_root.resolve().as_posix(),
        outline_path="",
        documents=analyzed_documents,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _matches_filter(
    *,
    document: ExportedOutlineDocument | AnalyzedDocument,
    document_path: str | None,
    source_id: str | None,
) -> bool:
    if document_path is not None and document.document_path != document_path:
        return False
    return source_id is None or document.source_id == source_id


def _is_glob_pattern(pattern: str) -> bool:
    return any(c in pattern for c in _WILDCARD_CHARS)


def _resolve_matches(*, repo_root: Path, files: list[str], globs: list[str]) -> MatchResolution:
    matched: set[str] = set()
    missing: list[str] = []
    unmatched: list[str] = []

    for file_path in files:
        if (repo_root / file_path).is_file():
            matched.add(file_path)
        else:
            missing.append(file_path)

    for pattern in globs:
        expanded = pattern + "/*" if pattern.endswith("**") else pattern
        glob_matches = [
            p.relative_to(repo_root).as_posix() for p in repo_root.glob(expanded) if p.is_file()
        ]
        if glob_matches:
            matched.update(glob_matches)
        else:
            unmatched.append(pattern)

    return MatchResolution(
        matched_files=sorted(matched),
        missing_files=missing,
        unmatched_globs=unmatched,
    )


def _get_git_changes(*, repo_root: Path, diff_base: str | None) -> GitChangeSet:
    changed: set[str] = set()
    new: set[str] = set()
    deleted: set[str] = set()

    if diff_base is not None:
        lines = run_git_command(
            repo_root=repo_root,
            args=["diff", "--name-status", "--diff-filter=ACMRD", f"{diff_base}...HEAD"],
        )
        for line in lines:
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            status = parts[0]
            if status.startswith("R"):
                # Rename: old_path -> new_path; treat old as deleted, new as new
                if len(parts) >= 3:
                    deleted.add(parts[1])
                    new.add(parts[2])
            elif status == "A":
                new.add(parts[1])
            elif status == "D":
                deleted.add(parts[1])
            else:
                changed.add(parts[1])

        for path in run_git_command(
            repo_root=repo_root,
            args=["ls-files", "--others", "--exclude-standard"],
        ):
            new.add(path)
    else:
        lines = run_git_command(
            repo_root=repo_root,
            args=["status", "--porcelain=v1", "--untracked-files=all"],
        )
        for line in lines:
            status = line[:2]
            path = line[3:]
            if not path:
                continue
            if "->" in path:
                path = path.split("->", maxsplit=1)[1].strip()
            if status == "??":
                new.add(path)
            elif status.strip() == "D":
                deleted.add(path)
            else:
                changed.add(path)

    return GitChangeSet(
        changed_files=sorted(changed),
        new_files=sorted(new),
        deleted_files=sorted(deleted),
    )


def _analyze_file(*, repo_root: Path, relative_path: str) -> AnalyzedFile:
    absolute = repo_root / relative_path
    content = absolute.read_text(encoding="utf-8", errors="ignore")
    symbols = extract_symbols(content, suffix=absolute.suffix)
    return AnalyzedFile(
        path=relative_path,
        line_count=content.count("\n") + 1 if content else 0,
        symbol_hints=symbols,
    )


def _tokenize(value: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", value.lower()) if len(t) > _MIN_TOKEN_LENGTH}


def _score_candidate_file(
    *,
    document: ExportedOutlineDocument,
    file_path: str,
    analyzed_file: AnalyzedFile,
) -> CandidateScore:
    doc_tokens = _tokenize(
        " ".join(filter(None, [document.title, document.source_id, document.outline_markdown]))
    )
    path_tokens = _tokenize(file_path.replace("/", " "))
    symbol_tokens = _tokenize(" ".join(analyzed_file.symbol_hints))

    title_overlap = doc_tokens & path_tokens
    symbol_overlap = doc_tokens & symbol_tokens
    score = (3 * len(title_overlap)) + len(symbol_overlap)

    if title_overlap:
        reason = f"title/path overlap: {', '.join(sorted(title_overlap)[:4])}"
    elif symbol_overlap:
        reason = f"title/symbol overlap: {', '.join(sorted(symbol_overlap)[:4])}"
    else:
        reason = "glob match only"

    return CandidateScore(score=score, reason=reason)
