"""Shared data models for kb-gen pipeline."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Source metadata (mirrors the Agency API schema, standalone)
# ---------------------------------------------------------------------------


class GitHubSourceMetadata(BaseModel):
    source_type: Literal["github"] = "github"
    owner: str
    repo: str
    source_url: str | None = None
    branch: str = "main"
    globs: list[str] = Field(default_factory=list)
    commit_sha: str | None = None
    stub: bool = False


class ManualSourceMetadata(BaseModel):
    source_type: Literal["manual"] = "manual"


DocumentSourceMetadata = Annotated[
    GitHubSourceMetadata | ManualSourceMetadata,
    Field(discriminator="source_type"),
]


# ---------------------------------------------------------------------------
# KB document (API response shape)
# ---------------------------------------------------------------------------


class KnowledgeBaseDocument(BaseModel):
    id: str
    org_id: str | None = None
    path: str
    created_by: str | None = None
    title: str
    content: str
    created_at: datetime
    archived_at: datetime | None = None
    source_id: str | None = None
    collection_id: str
    metadata_: DocumentSourceMetadata


# ---------------------------------------------------------------------------
# Config file (.agency-knows/config.yaml)
# ---------------------------------------------------------------------------


class KbGenConfig(BaseModel):
    """Configuration stored in the customer's repo."""

    collection_id: str
    api_base_url: str = "https://api.agency.inc/external"


# ---------------------------------------------------------------------------
# Export schemas
# ---------------------------------------------------------------------------


class ExportedOutlineDocument(BaseModel):
    document_id: str | None = None
    title: str
    document_path: str
    source_id: str | None = None
    files: list[str] = Field(default_factory=list)
    globs: list[str] = Field(default_factory=list)
    outline_markdown: str = ""
    metadata: DocumentSourceMetadata | None = None


class ExportedOutline(BaseModel):
    version: int = 1
    exported_at: datetime
    org_id: str
    collection_id: str
    documents: list[ExportedOutlineDocument]


# ---------------------------------------------------------------------------
# Analysis schemas
# ---------------------------------------------------------------------------


class AnalyzedFile(BaseModel):
    path: str
    line_count: int
    symbol_hints: list[str] = Field(default_factory=list)


class ScopedFile(BaseModel):
    path: str
    reason: str


class CandidateScore(BaseModel):
    score: int
    reason: str


class AnalyzedDocument(BaseModel):
    document_id: str | None = None
    title: str
    document_path: str
    source_id: str | None = None
    files: list[str] = Field(default_factory=list)
    globs: list[str] = Field(default_factory=list)
    outline_markdown: str = ""
    relevant_files: list[str] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    new_files: list[str] = Field(default_factory=list)
    has_matching_changes: bool = False
    candidate_files: list[ScopedFile] = Field(default_factory=list)
    ignored_files: list[ScopedFile] = Field(default_factory=list)
    missing_files: list[str] = Field(default_factory=list)
    unmatched_globs: list[str] = Field(default_factory=list)
    analyzed_files: list[AnalyzedFile] = Field(default_factory=list)


class OutlineAnalysis(BaseModel):
    version: int = 1
    analyzed_at: datetime
    repo_root: str
    outline_path: str
    documents: list[AnalyzedDocument]


# ---------------------------------------------------------------------------
# Outline schemas
# ---------------------------------------------------------------------------


class InitArticle(BaseModel):
    """A single article in the outline."""

    title: str
    path: str
    summary: str
    globs: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Path is required")
        if stripped.endswith(".md"):
            raise ValueError("Path must not include a .md suffix")
        if stripped.startswith("/") or stripped.endswith("/"):
            raise ValueError("Path must not start or end with /")

        segments = stripped.split("/")
        if len(segments) < 2 or len(segments) > 3:
            raise ValueError(
                "Path must have 2 or 3 slug segments total, e.g. "
                "'integrations/slack' or 'admin/security/sso'"
            )

        for segment in segments:
            parts = segment.split("-")
            if not segment or any(not part.isalnum() or part.lower() != part for part in parts):
                raise ValueError(
                    "Each path segment must be lowercase slug text using only "
                    "letters, numbers, and hyphens"
                )

        return stripped


class InitOutline(BaseModel):
    """The full outline for initializing a knowledge base."""

    product_name: str
    product_summary: str
    articles: list[InitArticle]


# ---------------------------------------------------------------------------
# Internal API helper schemas
# ---------------------------------------------------------------------------


class PathPatternSplit(BaseModel):
    files: list[str] = Field(default_factory=list)
    globs: list[str] = Field(default_factory=list)


class MatchResolution(BaseModel):
    matched_files: list[str] = Field(default_factory=list)
    missing_files: list[str] = Field(default_factory=list)
    unmatched_globs: list[str] = Field(default_factory=list)


class GitChangeSet(BaseModel):
    changed_files: list[str] = Field(default_factory=list)
    new_files: list[str] = Field(default_factory=list)


class _ExternalDocumentSummary(BaseModel):
    id: str


class _ExternalListResponse(BaseModel):
    data: list[_ExternalDocumentSummary]


class _ExternalDocumentResponse(BaseModel):
    data: dict[str, Any]
