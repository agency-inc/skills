"""CLI entrypoint for agency-kb."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import rich
import typer
import yaml
from pydantic import ValidationError

from agency_kb.async_typer import AsyncTyper
from agency_kb.config import load_dotenv
from agency_kb.schemas import ExportedOutlineDocument, KnowledgeBaseDocument

# Load .env early so ANTHROPIC_API_KEY and AGENCY_API_KEY are available
load_dotenv()

app = AsyncTyper(help="Generate and maintain knowledge base articles from source code.")


@app.command()
async def init(
    collection_id: Annotated[
        str,
        typer.Option(help="KB collection ID. If omitted, reuse the value from config.yaml."),
    ] = "",
    api_base_url: Annotated[
        str,
        typer.Option(
            help="Agency external API base URL. If omitted, reuse the value from config.yaml."
        ),
    ] = "",
    publish: Annotated[
        bool,
        typer.Option(
            "--publish/--no-publish", help="Upload the initial docs to an empty collection."
        ),
    ] = False,
    api_key: Annotated[str, typer.Option(help="Agency API key")] = "",
    github_owner: Annotated[str, typer.Option(help="GitHub repo owner override")] = "",
    github_repo: Annotated[str, typer.Option(help="GitHub repo name override")] = "",
    github_branch: Annotated[str, typer.Option(help="GitHub branch")] = "main",
    repo_root: Annotated[Path, typer.Option(help="Repository root")] = Path("."),
) -> None:
    """Initialize local artifacts and optionally publish them to an empty collection."""
    from agency_kb.api_client import KnowledgeBaseApiClient
    from agency_kb.config import (
        config_dir,
        config_path,
        find_repo_root,
        load_config,
        outline_path,
        prompt_path,
        resolve_api_key,
    )
    from agency_kb.init import (
        build_init_documents,
        publish_init_documents,
        write_init_documents,
    )
    from agency_kb.schemas import KbGenConfig

    resolved_root = repo_root.resolve() if repo_root != Path(".") else find_repo_root()
    cfg_path = config_path(resolved_root)
    outline_file = outline_path(resolved_root)
    prompt_file = prompt_path(resolved_root)
    existing_cfg = load_config(resolved_root) if cfg_path.exists() else None

    resolved_collection_id = collection_id or (
        existing_cfg.collection_id if existing_cfg is not None else ""
    )
    resolved_api_base_url = api_base_url or (
        existing_cfg.api_base_url if existing_cfg is not None else "https://api.agency.inc/external"
    )

    if not resolved_collection_id:
        rich.print(
            "[red]No collection id provided and no existing .agency-kb/config.yaml found. "
            "Pass --collection-id or create config first.[/red]"
        )
        raise typer.Exit(1)

    cfg = KbGenConfig(
        collection_id=resolved_collection_id,
        api_base_url=resolved_api_base_url,
    )

    out_dir = config_dir(resolved_root)
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg_serialized = yaml.dump(
        cfg.model_dump(exclude_none=True),
        default_flow_style=False,
        sort_keys=False,
    )
    config_changed = not cfg_path.exists() or cfg_path.read_text(encoding="utf-8") != cfg_serialized
    if config_changed:
        cfg_path.write_text(cfg_serialized, encoding="utf-8")
        rich.print(f"[green]Config written to {cfg_path}[/green]")
    else:
        rich.print(f"[cyan]Using existing config at {cfg_path}[/cyan]")

    if not outline_file.exists():
        rich.print(
            "[yellow]No outline found at .agency-kb/outline.json. "
            "Use the skill to draft the outline first.[/yellow]"
        )
        return

    outline = _load_outline(outline_file)
    project_prompt = _load_project_prompt(prompt_file)
    rich.print(f"[bold]{outline.product_name}[/bold]: {outline.product_summary}\n")
    rich.print(f"[green]Loaded outline with {len(outline.articles)} articles.[/green]")
    if project_prompt:
        rich.print(
            f"[green]Loaded project prompt from {prompt_file} "
            f"({len(project_prompt)} chars).[/green]"
        )
    else:
        rich.print(
            f"[yellow]No PROMPT.md found at {prompt_file}. "
            "Continuing without project-specific instructions.[/yellow]"
        )

    resolved_owner = github_owner or _detect_github_owner(resolved_root)
    resolved_repo = github_repo or _detect_github_repo(resolved_root)
    if not resolved_owner or not resolved_repo:
        rich.print(
            "[red]Could not detect the GitHub owner/repo from origin. "
            "Pass --github-owner and --github-repo.[/red]"
        )
        raise typer.Exit(1)

    init_documents = build_init_documents(
        outline=outline,
        github_owner=resolved_owner,
        github_repo=resolved_repo,
        github_branch=github_branch,
    )

    upload_dir = out_dir / "upload"
    write_init_documents(
        output_dir=upload_dir,
        collection_id=cfg.collection_id,
        documents=init_documents,
    )
    rich.print(
        f"[green]Materialized {len(init_documents)} initial document(s) to {upload_dir}.[/green]"
    )

    rich.print("Init summary:")
    rich.print(f"  collection_id: {cfg.collection_id}")
    rich.print(f"  api_base_url: {cfg.api_base_url}")
    rich.print(f"  github: {resolved_owner}/{resolved_repo}@{github_branch}")
    rich.print(f"  prompt: {prompt_file if project_prompt else 'none'}")
    rich.print("  artifact layout: upload/<path>.md and upload/<path>.json")

    if not publish:
        rich.print("\n[yellow]Dry run only.[/yellow] Re-run with [cyan]--publish[/cyan] to upload.")
        return

    async with KnowledgeBaseApiClient(
        base_url=cfg.api_base_url,
        api_key=resolve_api_key(api_key or None),
    ) as kb_api:
        existing_docs = await kb_api.list_documents(collection_id=cfg.collection_id)
        if existing_docs:
            rich.print(
                f"[red]Collection {cfg.collection_id} already has "
                f"{len(existing_docs)} document(s). "
                "Init only publishes to empty collections.[/red]"
            )
            raise typer.Exit(1)

        rich.print(
            f"[cyan]Publishing {len(init_documents)} initial document(s) to collection "
            f"{cfg.collection_id}...[/cyan]"
        )
        created = await publish_init_documents(
            kb_api=kb_api,
            collection_id=cfg.collection_id,
            documents=init_documents,
        )

    rich.print(f"[green]Published {created} initial document(s).[/green]")
    rich.print("Next: run [cyan]agency-kb sync --dry-run[/cyan] to preview generated updates.")


@app.command(name="validate-outline")
def validate_outline(
    repo_root: Annotated[Path, typer.Option(help="Repository root")] = Path("."),
) -> None:
    """Validate .agency-kb/outline.json against the schema.

    Use this after the Claude Code skill writes the outline to check for errors.
    """
    from agency_kb.config import find_repo_root, outline_path

    resolved_root = repo_root.resolve() if repo_root != Path(".") else find_repo_root()
    outline_file = outline_path(resolved_root)

    if not outline_file.exists():
        rich.print("[red]No outline found at .agency-kb/outline.json[/red]")
        raise typer.Exit(1)

    outline = _load_outline(outline_file)

    rich.print(f"[bold]{outline.product_name}[/bold]: {outline.product_summary}\n")
    rich.print(f"[green]Valid outline with {len(outline.articles)} articles:[/green]")
    for article in outline.articles:
        rich.print(f"  [green]+[/green] {article.path}: {article.title}")
        rich.print(f"      globs: {article.globs}")
        rich.print(f"      topics: {len(article.topics)}")



@app.command()
async def sync(
    repo_root: Annotated[Path, typer.Option(help="Repository root")] = Path("."),
    api_key: Annotated[str, typer.Option(help="Agency API key")] = "",
    diff_base: Annotated[str, typer.Option(help="Git ref for change detection")] = "",
    path_prefix: Annotated[
        str,
        typer.Option(
            help="Only sync article paths with this prefix, e.g. 'workflow/' or 'ai/chat'"
        ),
    ] = "",
    concurrency: Annotated[int, typer.Option(help="Max parallel LLM calls")] = 4,
    only_changed: Annotated[
        bool,
        typer.Option("--only-changed/--all", help="Only regenerate changed docs"),
    ] = True,
    publish: Annotated[
        bool,
        typer.Option(
            "--publish/--no-publish",
            help="Upload generated articles to the API. "
            "Without this flag, results are written to local files only.",
        ),
    ] = False,
    model: Annotated[str, typer.Option(help="Claude model")] = "claude-sonnet-4-20250514",
) -> None:
    """Sync KB articles by exporting current docs, generating updates, and uploading them."""
    from agency_kb.analyze import run_analyze
    from agency_kb.api_client import KnowledgeBaseApiClient
    from agency_kb.config import (
        config_dir,
        find_repo_root,
        load_config,
        prompt_path,
        resolve_api_key,
    )
    from agency_kb.export import run_export
    from agency_kb.generate import GenerationJob, read_source_files, run_generate

    resolved_root = repo_root.resolve() if repo_root != Path(".") else find_repo_root()
    cfg = load_config(resolved_root)
    normalized_prefix = path_prefix.strip().strip("/")
    artifacts_root = config_dir(resolved_root)
    download_dir = artifacts_root / "download"
    upload_dir = artifacts_root / "upload"
    prompt_file = prompt_path(resolved_root)
    project_prompt = _load_project_prompt(prompt_file)

    if project_prompt:
        rich.print(
            f"[cyan]Loaded project prompt from {prompt_file} ({len(project_prompt)} chars).[/cyan]"
        )
    else:
        rich.print(
            f"[yellow]No PROMPT.md found at {prompt_file}. "
            "Sync will run with built-in generation instructions only.[/yellow]"
        )

    async with KnowledgeBaseApiClient(
        base_url=cfg.api_base_url,
        api_key=resolve_api_key(api_key or None),
    ) as kb_api:
        current_documents = await kb_api.list_documents(collection_id=cfg.collection_id)
        if not current_documents:
            rich.print(
                f"[red]No documents found in collection {cfg.collection_id}. "
                "Sync only updates existing KB docs. Run the init flow first.[/red]"
            )
            raise typer.Exit(1)

        rich.print("[cyan]Exporting current outline from API...[/cyan]")
        outline = await run_export(
            kb_api=kb_api,
            collection_id=cfg.collection_id,
        )
        if normalized_prefix:
            outline.documents = [
                doc
                for doc in outline.documents
                if doc.document_path == normalized_prefix
                or doc.document_path.startswith(f"{normalized_prefix}/")
            ]

        if not outline.documents:
            if normalized_prefix:
                rich.print(
                    f"[yellow]No documents found in collection "
                    f"{cfg.collection_id} with path prefix "
                    f"'{normalized_prefix}'.[/yellow]"
                )
            else:
                rich.print("[yellow]No documents found in the configured collection.[/yellow]")
            return

        current_docs_by_path = {doc.path: doc for doc in current_documents}
        _write_download_artifacts(
            download_dir=download_dir,
            exported_documents=outline.documents,
            current_documents_by_path=current_docs_by_path,
        )
        rich.print(
            f"[cyan]Saved {len(outline.documents)} exported document(s) and metadata to "
            f"{download_dir}.[/cyan]"
        )

        rich.print("[cyan]Analyzing repo...[/cyan]")
        analysis = run_analyze(
            outline=outline,
            repo_root=resolved_root,
            diff_base=diff_base or None,
        )

        analyzed_by_path = {d.document_path: d for d in analysis.documents}

        current_documents = await kb_api.list_documents(collection_id=cfg.collection_id)
        doc_by_path = {d.path: d for d in current_documents}

        jobs: list[GenerationJob] = []
        skipped = 0
        for doc in outline.documents:
            analyzed = analyzed_by_path.get(doc.document_path)
            if not analyzed:
                skipped += 1
                continue
            if only_changed and not analyzed.has_matching_changes:
                skipped += 1
                continue
            existing = doc_by_path.get(doc.document_path)
            if not existing:
                skipped += 1
                continue
            source_text = read_source_files(repo_root=resolved_root, files=analyzed.relevant_files)
            if not source_text:
                skipped += 1
                continue
            jobs.append(
                GenerationJob(
                    document=doc,
                    analyzed_document=analyzed,
                    existing_document=existing,
                    source_text=source_text,
                )
            )

        if not jobs:
            rich.print(f"[yellow]Nothing to generate (skipped {skipped}).[/yellow]")
            return

        rich.print(f"[cyan]Generating {len(jobs)} article(s) (concurrency={concurrency})...[/cyan]")
        generated, errored = await run_generate(
            jobs=jobs,
            all_documents=current_documents,
            kb_api=None if not publish else kb_api,
            concurrency=concurrency,
            dry_run=not publish,
            output_dir=upload_dir,
            project_prompt=project_prompt,
            model=model,
        )

    rich.print(
        f"\n[green]Generated {generated}[/green], "
        f"[red]errored {errored}[/red], "
        f"[yellow]skipped {skipped}[/yellow]"
    )
    if not publish:
        rich.print(
            "\n[yellow]Local only.[/yellow] Review results in .agency-kb/upload/, "
            "then re-run with [cyan]--publish[/cyan] to upload."
        )


@app.command()
async def review(
    repo_root: Annotated[Path, typer.Option(help="Repository root")] = Path("."),
    api_key: Annotated[str, typer.Option(help="Agency API key")] = "",
    publish: Annotated[
        bool,
        typer.Option(
            "--publish/--no-publish",
            help="Create stub articles from .agency-kb/review/ in the KB.",
        ),
    ] = False,
) -> None:
    """Discover KB coverage gaps or publish new article stubs.

    Without --publish: exports current docs to download/, scans the repo for
    uncovered source files, and writes review/gaps.json. The Claude Code skill
    reads the gaps, suggests new articles, and writes .json proposals to review/.

    With --publish: creates stub articles (title + topics) from each .json in
    .agency-kb/review/. Run sync --publish afterward to generate full content.
    """
    from agency_kb.api_client import KnowledgeBaseApiClient
    from agency_kb.config import (
        config_dir,
        find_repo_root,
        load_config,
        resolve_api_key,
    )
    from agency_kb.export import run_export
    from agency_kb.review import find_uncovered_files, group_by_directory, write_review_report
    from agency_kb.schemas import GitHubSourceMetadata

    resolved_root = repo_root.resolve() if repo_root != Path(".") else find_repo_root()
    cfg = load_config(resolved_root)
    artifacts_root = config_dir(resolved_root)
    download_dir = artifacts_root / "download"
    review_dir = artifacts_root / "review"

    async with KnowledgeBaseApiClient(
        base_url=cfg.api_base_url,
        api_key=resolve_api_key(api_key or None),
    ) as kb_api:
        current_documents = await kb_api.list_documents(collection_id=cfg.collection_id)
        if not current_documents:
            rich.print(
                f"[red]No documents found in collection {cfg.collection_id}. "
                "Run the init flow first.[/red]"
            )
            raise typer.Exit(1)

        # --- Publish mode: create stubs from review/ proposals ---
        if publish:
            doc_by_path = {d.path: d for d in current_documents}
            json_files = sorted(review_dir.rglob("*.json")) if review_dir.exists() else []
            json_files = [f for f in json_files if f.name != "gaps.json"]
            if not json_files:
                rich.print("[yellow]No proposals found in .agency-kb/review/.[/yellow]")
                return

            created = 0
            for json_path in json_files:
                meta = json.loads(json_path.read_text(encoding="utf-8"))

                article_path = meta.get("path", "")
                if not article_path:
                    rel = json_path.relative_to(review_dir).with_suffix("")
                    article_path = rel.as_posix()

                if article_path in doc_by_path:
                    rich.print(f"  [yellow]SKIP[/yellow] {article_path} (already exists)")
                    continue

                title = meta.get("title", "")
                topics = meta.get("topics", [])
                topics_md = "\n".join(f"- {t}" for t in topics)
                stub_content = f"# {title}\n\n{topics_md}\n"

                source_id = meta.get("source_id")
                metadata_raw = meta.get("metadata", {})
                metadata = GitHubSourceMetadata.model_validate(metadata_raw)
                metadata.stub = True

                new_doc = await kb_api.create_document(
                    title=title,
                    content=stub_content,
                    path=article_path,
                    collection_id=cfg.collection_id,
                    source_id=source_id,
                    metadata=metadata,
                )
                rich.print(f"  [green]+[/green] {new_doc.title} ({new_doc.path})")
                created += 1

            rich.print(f"\n[green]Created {created} stub article(s).[/green]")
            if created > 0:
                rich.print(
                    "Run [cyan]agency-kb sync --all --publish[/cyan] to generate"
                    " full content for all articles."
                )
            return

        # --- Discovery mode: export and scan for gaps ---
        rich.print("[cyan]Exporting current docs to download/...[/cyan]")
        outline = await run_export(
            kb_api=kb_api,
            collection_id=cfg.collection_id,
        )

        if not outline.documents:
            rich.print("[yellow]No documents found in the configured collection.[/yellow]")
            return

        current_docs_by_path = {doc.path: doc for doc in current_documents}
        _write_download_artifacts(
            download_dir=download_dir,
            exported_documents=outline.documents,
            current_documents_by_path=current_docs_by_path,
        )
        rich.print(f"[cyan]Saved {len(outline.documents)} doc(s) to {download_dir}.[/cyan]")

    rich.print("[cyan]Scanning for uncovered files...[/cyan]")
    uncovered = find_uncovered_files(
        repo_root=resolved_root,
        outline=outline,
    )

    if uncovered:
        write_review_report(
            output_path=review_dir / "gaps.json",
            uncovered_files=uncovered,
            existing_article_count=len(outline.documents),
            collection_id=cfg.collection_id,
        )

        grouped = group_by_directory(uncovered)
        rich.print(f"\n[yellow]{len(uncovered)} uncovered source file(s):[/yellow]")
        for directory, files in grouped.items():
            rich.print(f"  [cyan]{directory}/[/cyan] ({len(files)} files)")
            for f in files[:5]:
                rich.print(f"    {f}")
            if len(files) > 5:
                rich.print(f"    ... and {len(files) - 5} more")
        rich.print(f"\n[green]Gap report written to {review_dir / 'gaps.json'}[/green]")
    else:
        rich.print("[green]All source files are covered by existing articles.[/green]")


def _write_download_artifacts(
    *,
    download_dir: Path,
    exported_documents: list[ExportedOutlineDocument],
    current_documents_by_path: dict[str, KnowledgeBaseDocument],
) -> None:
    download_dir.mkdir(parents=True, exist_ok=True)

    for exported_document in exported_documents:
        current_document = current_documents_by_path.get(exported_document.document_path)
        if current_document is None:
            continue

        markdown_path = _artifact_path(
            base_dir=download_dir,
            document_path=exported_document.document_path,
            suffix=".md",
        )
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(current_document.content, encoding="utf-8")

        metadata_path = _artifact_path(
            base_dir=download_dir,
            document_path=exported_document.document_path,
            suffix=".json",
        )
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(
            json.dumps(
                {
                    "title": current_document.title,
                    "path": current_document.path,
                    "document_id": current_document.id,
                    "collection_id": current_document.collection_id,
                    "source_id": current_document.source_id,
                    "metadata": current_document.metadata_.model_dump(),
                    "globs": exported_document.globs,
                    "files": exported_document.files,
                },
                indent=2,
            ),
            encoding="utf-8",
        )


def _artifact_path(*, base_dir: Path, document_path: str, suffix: str) -> Path:
    return base_dir / Path(*document_path.split("/")).with_suffix(suffix)


def _load_outline(outline_file: Path):
    from agency_kb.schemas import InitOutline

    try:
        return InitOutline.model_validate_json(outline_file.read_text(encoding="utf-8"))
    except ValidationError as exc:
        rich.print(f"[red]Invalid outline at {outline_file}:[/red]\n{exc}")
        raise typer.Exit(1) from exc


def _load_project_prompt(prompt_file: Path) -> str:
    if not prompt_file.exists():
        return ""
    return prompt_file.read_text(encoding="utf-8").strip()


def _detect_github_owner(repo_root: Path) -> str | None:
    from agency_kb.repo_scanner import run_git_command

    try:
        lines = run_git_command(repo_root=repo_root, args=["remote", "get-url", "origin"])
        if lines:
            return _parse_github_remote(lines[0])[0]
    except Exception:
        return None
    return None


def _detect_github_repo(repo_root: Path) -> str | None:
    from agency_kb.repo_scanner import run_git_command

    try:
        lines = run_git_command(repo_root=repo_root, args=["remote", "get-url", "origin"])
        if lines:
            return _parse_github_remote(lines[0])[1]
    except Exception:
        return None
    return None


def _parse_github_remote(url: str) -> tuple[str | None, str | None]:
    import re

    match = re.match(r"git@github\.com:([^/]+)/([^/.]+)", url)
    if match:
        return match.group(1), match.group(2)
    match = re.match(r"https://github\.com/([^/]+)/([^/.]+)", url)
    if match:
        return match.group(1), match.group(2)
    return None, None


if __name__ == "__main__":
    app()
