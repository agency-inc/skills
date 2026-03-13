"""Generate: call the LLM to produce KB article content from source code."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import anthropic
import rich

from agency_kb.api_client import KnowledgeBaseApiClient
from agency_kb.schemas import (
    AnalyzedDocument,
    ExportedOutlineDocument,
    GitHubSourceMetadata,
    KnowledgeBaseDocument,
)

_GENERATE_MODEL = "claude-sonnet-4-20250514"
_MAX_SOURCE_CHARS = 80_000
_MAX_EXISTING_CONTENT_CHARS = 8_000
_MAX_CONCURRENT = 4

_GENERATE_SYSTEM_PROMPT = """\
You are writing knowledge base articles for a software product.
These articles are loaded into an AI assistant's context so it can answer customer questions.
The assistant reads your articles, then explains things to users in its own words.

## Audience

Your reader is an AI assistant (named "Kai") that helps end users of the product. \
Kai needs to understand:
- What can the user DO? What actions, buttons, screens, and shortcuts exist?
- How does the product BEHAVE? What happens automatically? What triggers what?
- What OPTIONS and SETTINGS exist? What are the defaults? What changes when you toggle them?
- What are the LIMITS and EDGE CASES?
- What WORKFLOWS span multiple features?

## Writing rules

Write from the perspective of someone who uses the product every day.

DO:
- Describe what users see and can do — use the actual visible labels from the source code
- Explain automatic behaviors and timing
- Translate code enum values, state names, and constants into plain English \
(e.g., if code says "on_them", describe it as "waiting for their reply" or whatever the UI shows)
- Be concrete about defaults, limits, thresholds, intervals \
— but only when the code clearly shows them
- Explain lifecycle: setup, processing, active, failure, recovery
- Name UI elements by their visible labels (look for text in JSX, button labels, tab names)
- Cover common workflows and practical tips
- Mention keyboard shortcuts ONLY if you see them explicitly defined in the source code

DO NOT:
- Never mention databases, tables, columns, SQL
- Never mention API endpoints, HTTP methods, tRPC routers
- Never mention file paths, function names, class names, React component names
- Never mention infrastructure (Elasticsearch, Redis, S3, Temporal, PostgreSQL)
- Never mention internal IDs, source types, or enum values from code
- Never say "the system uses X" or "stored in Y" — describe user experience only
- Never list enum values — translate them to user-visible behavior
- Never stop at "supports X" if the code shows how X actually behaves
- NEVER fabricate or guess at specific details (keyboard shortcuts, URL patterns, \
feature names, limits) — only include what you can directly confirm from the source code
- Never invent URL paths or navigation routes that aren't clearly visible in the code
- Never pad articles with vague or generic filler — every sentence should be specific and grounded

## How to extract behavior from source code

1. Start from what the user sees — find UI elements, labels, error messages in JSX/TSX
2. Follow actions — trace what happens on click/submit/toggle
3. Find automations — scheduled jobs, background workers, event handlers
4. Extract constraints — defaults, limits, permissions, feature gates
5. Map the state machine — lifecycle from creation to archival
6. Look for configuration — settings, toggles, admin controls
7. Connect the dots — trace end-to-end user workflows

## Required sections

Every article MUST include these sections (and ONLY these sections):

1. **## Overview** — 2-3 sentences on what this feature is and why it matters
2. **## Where to find it** — Exact navigation path(s) to reach this feature. \
Extract these from the source code route structure (e.g., Next.js app directory paths, \
sidebar navigation items, settings page locations). Use the format users would follow: \
"Go to Settings > Members > Teams" or "Click Train in the sidebar, then Knowledge." \
Include the URL path if clearly visible in the route structure (e.g., `/settings/members/teams`). \
If the feature is accessible from multiple places, list all of them.
3. **## How it works** — Main feature description. This is the meat of the article. \
Describe the UI, the workflow, and the behavior in detail. Use subsections (###) \
to organize by aspect of the feature. 4-8 paragraphs.
4. **## Tips** — 2-4 practical tips or workflow shortcuts grounded in the code. \
Only include tips you can back up with source evidence.
5. **## Limitations and notes** — Known constraints, permissions, caveats. \
Only include what the code actually shows.

## Accuracy over completeness

It is MUCH better to write a shorter, accurate article than a longer article that \
guesses or pads. If the source code doesn't clearly show something, leave it out. \
An article that says five true things is more useful than one that says ten things \
where three are wrong.

## Depth and tone

Write like a well-written help article from Stripe or Linear. Second person ("you"), \
conversational but precise. Every section should have prose paragraphs, not just bullets. \
Aim for 800-2000 words — shorter is fine if the feature is simple.

## Response format

Respond in JSON (no code fence): {"summary": "...", "content": "# Title\\n\\n..."}

Rules:
- summary: one sentence, max 150 chars
- content: markdown starting with # Title
- Aim for 800-2000 words"""


class GenerationJob:
    def __init__(
        self,
        *,
        document: ExportedOutlineDocument,
        analyzed_document: AnalyzedDocument,
        existing_document: KnowledgeBaseDocument,
        source_text: str,
    ) -> None:
        self.document = document
        self.analyzed_document = analyzed_document
        self.existing_document = existing_document
        self.source_text = source_text


async def run_generate(
    *,
    jobs: list[GenerationJob],
    all_documents: list[KnowledgeBaseDocument],
    kb_api: KnowledgeBaseApiClient | None,
    concurrency: int = _MAX_CONCURRENT,
    dry_run: bool = False,
    output_dir: Path | None = None,
    project_prompt: str = "",
    model: str = _GENERATE_MODEL,
    commit_sha: str = "",
) -> tuple[int, int]:
    """Run LLM generation for a batch of jobs. Returns (generated_count, error_count)."""
    client = anthropic.AsyncAnthropic()
    semaphore = asyncio.Semaphore(concurrency)
    generated = 0
    errored = 0

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)

    async def _process(job: GenerationJob) -> bool:
        async with semaphore:
            rich.print(
                f"  [cyan]->[/cyan] {job.document.title} "
                f"({len(job.analyzed_document.relevant_files)} files, "
                f"{len(job.source_text):,} chars)"
            )
            try:
                other_titles = [d.title for d in all_documents if d.id != job.existing_document.id]
                result = await _call_llm(
                    client=client,
                    document=job.document,
                    analyzed_document=job.analyzed_document,
                    source_text=job.source_text,
                    existing_content=_truncate(job.existing_document.content),
                    other_article_titles=other_titles,
                    project_prompt=project_prompt,
                    model=model,
                )
                if output_dir:
                    out_path = _artifact_path(
                        base_dir=output_dir,
                        document_path=job.document.document_path,
                        suffix=".md",
                    )
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(result["content"], encoding="utf-8")
                else:
                    out_path = None

                if output_dir:
                    metadata_path = _artifact_path(
                        base_dir=output_dir,
                        document_path=job.document.document_path,
                        suffix=".json",
                    )
                    metadata_path.parent.mkdir(parents=True, exist_ok=True)
                    metadata_path.write_text(
                        json.dumps(
                            {
                                "title": job.document.title,
                                "path": job.document.document_path,
                                "document_id": job.existing_document.id,
                                "collection_id": job.existing_document.collection_id,
                                "source_id": job.existing_document.source_id,
                                "summary": result["summary"],
                                "metadata": job.existing_document.metadata_.model_dump(),
                                "commit_sha": commit_sha,
                                "relevant_files": job.analyzed_document.relevant_files,
                                "changed_files": job.analyzed_document.changed_files,
                                "new_files": job.analyzed_document.new_files,
                                "deleted_files": job.analyzed_document.deleted_files,
                            },
                            indent=2,
                        ),
                        encoding="utf-8",
                    )

                if kb_api:
                    publish_metadata = job.existing_document.metadata_
                    if isinstance(publish_metadata, GitHubSourceMetadata):
                        updates: dict[str, object] = {"stub": False}
                        if commit_sha:
                            updates["commit_sha"] = commit_sha
                        publish_metadata = publish_metadata.model_copy(update=updates)
                    await kb_api.put_document(
                        document_id=job.existing_document.id,
                        body={
                            "title": job.existing_document.title,
                            "content": result["content"],
                            "path": job.existing_document.path,
                            "collection_id": job.existing_document.collection_id,
                            "source_id": job.existing_document.source_id,
                            "metadata": publish_metadata.model_dump(),
                        },
                    )
                    destination = out_path if out_path else "API"
                    rich.print(
                        f"  [green]OK[/green] {job.document.title}: "
                        f"{result['summary']} -> {destination}"
                    )
                elif out_path:
                    rich.print(f"  [green]OK[/green] {job.document.title} -> {out_path}")
                return True
            except (
                anthropic.APIError,
                json.JSONDecodeError,
                ValueError,
                KeyError,
            ) as exc:
                rich.print(f"  [red]FAIL[/red] {job.document.title}: {exc}")
                return False

    results = await asyncio.gather(*[_process(job) for job in jobs])
    generated = sum(1 for r in results if r)
    errored = sum(1 for r in results if not r)
    return generated, errored


def read_source_files(
    *,
    repo_root: Path,
    files: list[str],
    max_chars: int = _MAX_SOURCE_CHARS,
) -> str:
    parts: list[str] = []
    total = 0
    for relative_path in files:
        absolute = repo_root / relative_path
        try:
            content = absolute.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        header = f"### {relative_path}\n```\n"
        footer = "\n```\n\n"
        chunk = header + content + footer

        if total + len(chunk) > max_chars:
            remaining = max_chars - total
            if remaining > len(header) + len(footer) + 200:
                truncated = content[: remaining - len(header) - len(footer) - 20]
                chunk = header + truncated + "\n... (truncated)" + footer
                parts.append(chunk)
            break

        parts.append(chunk)
        total += len(chunk)

    return "".join(parts)


def _truncate(content: str) -> str:
    if len(content) <= _MAX_EXISTING_CONTENT_CHARS:
        return content
    return content[:_MAX_EXISTING_CONTENT_CHARS] + "\n\n... (truncated)"


def _artifact_path(*, base_dir: Path, document_path: str, suffix: str) -> Path:
    return base_dir / Path(*document_path.split("/")).with_suffix(suffix)


def _classify_files(files: list[str]) -> str:
    frontend = [f for f in files if "web-app" in f or f.endswith((".tsx", ".jsx"))]
    backend = [f for f in files if f.endswith(".py")]
    api_layer = [f for f in files if "trpc" in f or f.endswith(".router.ts")]
    lines: list[str] = []
    if frontend:
        lines.append(f"- Frontend: {', '.join(frontend)}")
    if api_layer:
        lines.append(f"- API layer: {', '.join(api_layer)}")
    if backend:
        lines.append(f"- Backend: {', '.join(backend)}")
    return "\n".join(lines) if lines else "- Mixed source files"


async def _call_llm(
    *,
    client: anthropic.AsyncAnthropic,
    document: ExportedOutlineDocument,
    analyzed_document: AnalyzedDocument,
    source_text: str,
    existing_content: str = "",
    other_article_titles: list[str] | None = None,
    project_prompt: str = "",
    model: str = _GENERATE_MODEL,
) -> dict[str, str]:
    sections: list[str] = []
    sections.append(f"Document: {document.title}")
    sections.append(f"Path: {document.document_path}")

    normalized_project_prompt = project_prompt.strip()
    if normalized_project_prompt:
        sections.append(
            "## Project-specific instructions\n\n"
            "Follow these repository-specific instructions in addition to the built-in rules.\n\n"
            f"{normalized_project_prompt}"
        )

    outline = analyzed_document.outline_markdown.strip()
    if outline:
        sections.append(
            "## Required topics\n\n"
            "This outline defines the topics this article MUST cover. Each bullet "
            "point should become a section or subsection.\n\n"
            f"{outline}"
        )

    if existing_content:
        sections.append(
            "## Previous version of this article\n\n"
            "Use as reference — update with new information from the source code, "
            "but preserve accurate sections and maintain consistent tone.\n\n"
            f"{existing_content}"
        )

    if other_article_titles:
        titles_list = "\n".join(f"- {t}" for t in other_article_titles)
        sections.append(
            "## Other articles in this collection\n\n"
            "When relevant, mention related features by name. "
            "Do NOT generate links or URLs to other articles.\n\n"
            f"{titles_list}"
        )

    file_summary = _classify_files(analyzed_document.relevant_files)
    sections.append(f"## Source file summary\n\n{file_summary}")
    sections.append(f"## Source files\n\n{source_text}")

    user_prompt = "\n\n".join(sections)

    response = await client.messages.create(
        model=model,
        max_tokens=8192,
        system=_GENERATE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    text = next(
        (
            block_text
            for block in response.content
            for block_text in [getattr(block, "text", None)]
            if isinstance(block_text, str)
        ),
        None,
    )
    if text is None:
        raise ValueError("No text content in LLM response")
    return _parse_json(text)


def _parse_json(text: str) -> dict[str, str]:
    start = text.find("{")
    if start < 0:
        raise ValueError("No JSON object found in LLM response")
    decoder = json.JSONDecoder()
    result, _ = decoder.raw_decode(text, start)
    return result
