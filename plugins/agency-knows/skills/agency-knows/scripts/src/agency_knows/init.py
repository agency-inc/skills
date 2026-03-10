"""Init: materialize and optionally publish initial KB documents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import rich

from agency_knows.api_client import KnowledgeBaseApiClient
from agency_knows.schemas import (
    GitHubSourceMetadata,
    InitOutline,
)


@dataclass
class InitDocument:
    title: str
    path: str
    content: str
    metadata: GitHubSourceMetadata
    source_id: str


def build_init_documents(
    *,
    outline: InitOutline,
    github_owner: str,
    github_repo: str,
    github_branch: str,
) -> list[InitDocument]:
    source_id = f"github:{github_owner}/{github_repo}:{github_branch}"
    documents: list[InitDocument] = []

    for article in outline.articles:
        topics_md = "\n".join(f"- {t}" for t in article.topics)
        content = f"# {article.title}\n\n{topics_md}\n"
        metadata = GitHubSourceMetadata(
            owner=github_owner,
            repo=github_repo,
            branch=github_branch,
            globs=article.globs,
        )
        documents.append(
            InitDocument(
                title=article.title,
                path=article.path,
                content=content,
                metadata=metadata,
                source_id=source_id,
            )
        )

    return documents


def write_init_documents(
    *,
    output_dir: Path,
    collection_id: str,
    documents: list[InitDocument],
) -> None:
    import json

    output_dir.mkdir(parents=True, exist_ok=True)
    for document in documents:
        markdown_path = output_dir / Path(*document.path.split("/")).with_suffix(".md")
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(document.content, encoding="utf-8")

        metadata_path = output_dir / Path(*document.path.split("/")).with_suffix(".json")
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(
            json.dumps(
                {
                    "title": document.title,
                    "path": document.path,
                    "collection_id": collection_id,
                    "source_id": document.source_id,
                    "metadata": document.metadata.model_dump(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )


async def publish_init_documents(
    *,
    kb_api: KnowledgeBaseApiClient,
    collection_id: str,
    documents: list[InitDocument],
) -> int:
    """Create initial KB documents and publish them to the API."""
    created = 0
    for document in documents:
        await kb_api.create_document(
            title=document.title,
            content=document.content,
            path=document.path,
            collection_id=collection_id,
            source_id=document.source_id,
            metadata=document.metadata,
        )
        rich.print(f"  [green]+[/green] {document.path}: {document.title}")
        created += 1

    return created
