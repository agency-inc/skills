"""Export: fetch KB documents from the API and build an outline JSON."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

import rich

from agency_kb.api_client import KnowledgeBaseApiClient
from agency_kb.schemas import (
    ExportedOutline,
    ExportedOutlineDocument,
    GitHubSourceMetadata,
    KnowledgeBaseDocument,
    PathPatternSplit,
)

_WILDCARD_CHARS = ("*", "?", "[")


async def run_export(
    *,
    kb_api: KnowledgeBaseApiClient,
    collection_id: str,
    document_path: str | None = None,
    source_id: str | None = None,
) -> ExportedOutline:
    """Fetch documents from the API and build an ExportedOutline."""
    documents = await kb_api.list_documents(
        collection_id=collection_id,
        document_path=document_path,
        source_id=source_id,
    )

    exported = [
        doc
        for d in documents
        if d.collection_id == collection_id
        for doc in [_build_exported_document(document=d)]
        if _matches_filter(doc, document_path=document_path, source_id=source_id)
    ]
    exported.sort(key=lambda d: d.document_path)

    outline = ExportedOutline(
        exported_at=datetime.now(UTC),
        org_id="",
        collection_id=collection_id,
        documents=exported,
    )

    rich.print(f"[green]Exported {len(exported)} documents[/green]")
    return outline


def _matches_filter(
    doc: ExportedOutlineDocument,
    *,
    document_path: str | None,
    source_id: str | None,
) -> bool:
    if document_path is not None and doc.document_path != document_path:
        return False
    return source_id is None or doc.source_id == source_id


def _build_exported_document(*, document: KnowledgeBaseDocument) -> ExportedOutlineDocument:
    metadata = document.metadata_
    patterns = metadata.globs if isinstance(metadata, GitHubSourceMetadata) else []
    split = _split_files_and_globs(patterns)

    return ExportedOutlineDocument(
        document_id=document.id,
        title=document.title,
        document_path=document.path,
        source_id=document.source_id,
        files=split.files,
        globs=split.globs,
        outline_markdown=_normalize_outline_markdown(document.content, title=document.title),
        metadata=metadata,
    )


def _split_files_and_globs(patterns: Iterable[str]) -> PathPatternSplit:
    files: list[str] = []
    globs: list[str] = []
    for p in patterns:
        if any(c in p for c in _WILDCARD_CHARS):
            globs.append(p)
        else:
            files.append(p)
    return PathPatternSplit(files=sorted(set(files)), globs=sorted(set(globs)))


def _normalize_outline_markdown(markdown: str, *, title: str) -> str:
    lines = markdown.strip().splitlines()
    if lines and lines[0].strip() == f"# {title}":
        lines = lines[1:]
    return "\n".join(lines).strip()


def save_outline(outline: ExportedOutline, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(outline.model_dump_json(indent=2), encoding="utf-8")


def load_outline(path: Path) -> ExportedOutline:
    return ExportedOutline.model_validate_json(path.read_text(encoding="utf-8"))
