---
name: kb-github
description: Set up and maintain an Agency Knowledge Base from a GitHub repo. Covers authoring an outline, interactively refining the TOC, and generating content. Use when setting up KB, editing KB outline, or running agency-kb.
---

# Agency Knowledge Base (GitHub)

You are the primary intelligence behind generating a knowledge base from source code. The CLI (`agency-kb`) is a thin utility — **you** do the research, exploration, outline generation, and refinement.

## How it works

The KB is a collection of documents in Agency. Each document has a filesystem-like path (`integrations/slack`, `admin/security/sso`), content in markdown, and metadata linking it to source code via globs. Collections are created manually in the Agency UI — this skill does not create them.

## Entry point

Every conversation starts here. Check the current state and route to the right flow:

1. Read `.agency-kb/config.yaml` — does it exist? Does it have a `collection_id`?
2. Read `.agency-kb/.env` — are the API keys configured?
3. If both exist, **test the connection by running sync** to see if the collection has documents:
   ```bash
   sh ${CLAUDE_SKILL_DIR}/scripts/run.sh sync
   ```
   - If it prints "No documents found in collection" → the collection is empty, route to **Init**
   - If it exports documents and starts analyzing → the collection is live, cancel and route to **Sync** or **Review**

**If no config, no keys, or empty collection:** You must complete **Init** before anything else. Tell the user: "Let's get your knowledge base set up and published first."

**If the collection already has documents:** Ask the user: "Your KB has [N] published articles. Do you want to **sync** (update existing articles from code changes) or **review** (find gaps and add new articles)?"

---

## Init

Goal: get from zero to a published collection. Walk the user through every sub-step — don't skip ahead.

### 1. Collect all setup info upfront

Before doing anything else, gather everything you need **in a single message**. Don't drip-feed questions one at a time. Ask for all of these at once:

> To get started, I need a few things:
>
> 1. **Collection ID** — from the Agency UI (see below for how to find it)
> 2. **Agency API key** — from Agency settings (see below)
> 3. **Anthropic API key** — from console.anthropic.com
> 4. **Product website or docs URL** — so I can understand your product
>
> **How to get your Collection ID:**
> - In Agency, go to **Knowledge** in the left sidebar, then **Knowledge Base**
> - If you don't have a collection yet: click **Create New Collection**, give it a name, and choose visibility (Internal = for your team's questions, Public = used in customer responses)
> - Find your collection in the list, hover over it, click the **⋯** menu, and select **Copy Collection ID**
>
> **How to get your Agency API key:**
> - In Agency, go to **Settings > API**
> - Click **Create API Key**, give it a name like "Knowledge Base Sync", and click Create
> - Copy the key immediately — it's only shown once (note: there's no visual feedback when you click copy, but it does work)
>
> **Anthropic API key:**
> - Go to https://console.anthropic.com/settings/keys
> - Create a new key or copy an existing one

Wait for the user to provide all of these before proceeding.

### 2. Write config and credentials

Once you have everything:

1. **Write `.agency-kb/config.yaml`:**
   ```yaml
   collection_id: <their-collection-id>
   api_base_url: https://api.agency.inc/external
   ```

2. **Write `.agency-kb/.env`:**
   ```
   AGENCY_API_KEY=<their-agency-key>
   ANTHROPIC_API_KEY=<their-anthropic-key>
   ```

3. **Verify `.agency-kb/.env` is gitignored.** Check if `.gitignore` exists and includes `.env` or `.agency-kb/.env`. If not, add it. Tell the user: "I've added `.agency-kb/.env` to `.gitignore` to keep your keys out of version control."

### 3. Research the product

You need to understand the product before writing anything.

1. **Search the web**: Fetch the homepage and/or docs URL the user provided. Extract:
   - What the product does (value proposition)
   - Key features and capabilities
   - Target users and personas
   - Navigation structure and terminology
   - Integrations and connected services
2. **Explore the codebase**:
   - Read the README
   - Scan directory structure with `Glob`
   - Find route/page files (Next.js `app/**/page.tsx`, React Router, etc.)
   - Read config files (`package.json`, `pyproject.toml`, etc.)
   - Skim feature directories

### 4. Write PROMPT.md

Write `.agency-kb/PROMPT.md` before the outline. This gives the LLM product-specific context when generating article content later. Include:

- Product name and what it does (from the website)
- Key terminology (e.g., "workspace" not "organization", "deal" not "opportunity")
- Target audience
- Tone (e.g., "concise like Linear docs", "professional like Stripe docs")
- Navigation structure (top-level sections users see)
- What to emphasize or avoid

Example:

```markdown
# Product context

Acme CRM is a sales pipeline tool for B2B teams. Users are sales reps and managers.

## Terminology
- "deal" not "opportunity"
- "pipeline" not "funnel"
- "workspace" not "organization"

## Tone
Concise, second person, practical. Like Linear or Notion help docs.

## Navigation
Main sidebar: Inbox, Pipeline, Contacts, Reporting, Settings.

## Notes
- Mobile app is in beta — don't document it yet
- Admin features are under Settings > Organization
```

If `PROMPT.md` already exists, read it and ask if the user wants to update it with what you learned from web research.

### 5. Generate the outline

Draft the outline and present it to the user **before writing JSON**:

- Group articles by category (path prefix)
- Show title, path, summary, and topics for each
- Highlight areas you're unsure about

**Outline rules:**
- Every article documents something a user can see, do, or configure
- One article per feature area (Stripe/Linear help docs level)
- Paths: lowercase slugs, 2-3 segments (`integrations/slack`, `admin/security/sso`)
- Globs: specific patterns mapping to source files
- Topics: 3-8 bullet points, user-facing behavior only
- Cover all major areas — better to propose too many and trim

After the user approves, write `.agency-kb/outline.json`.

### 6. Publish

Run init to validate, then publish:

```bash
# Preview
sh ${CLAUDE_SKILL_DIR}/scripts/run.sh init --collection-id=<id>

# Publish stubs (only works on empty collections)
sh ${CLAUDE_SKILL_DIR}/scripts/run.sh init --publish
```

Then generate full content. Run all articles with concurrency — this is the default, don't make the user ask for it:

```bash
# Preview locally
sh ${CLAUDE_SKILL_DIR}/scripts/run.sh sync --all

# Publish to Agency
sh ${CLAUDE_SKILL_DIR}/scripts/run.sh sync --all --publish
```

**Before running sync**, tell the user approximately how many articles will be generated so they know what to expect in terms of time and API usage. For example: "This will generate 24 articles. With concurrency of 4, it should take a few minutes and use roughly X Anthropic API calls."

**Init is complete when full content is published.** Only then can the user move to sync or review.

---

## Sync

Goal: update existing articles based on code changes.

```bash
# Incremental (only changed articles)
sh ${CLAUDE_SKILL_DIR}/scripts/run.sh sync --publish --diff-base=origin/main

# Full regeneration
sh ${CLAUDE_SKILL_DIR}/scripts/run.sh sync --all --publish

# Preview locally first (omit --publish)
sh ${CLAUDE_SKILL_DIR}/scripts/run.sh sync --diff-base=origin/main
```

Results are saved to `.agency-kb/upload/` for review before publishing. Without `--publish`, nothing is uploaded.

For CI (GitHub Actions):

```yaml
- name: Update knowledge base
  env:
    AGENCY_API_KEY: ${{ secrets.AGENCY_API_KEY }}
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  run: |
    pip install agency-kb
    agency-kb sync --publish --diff-base=origin/main
```

---

## Review

Goal: find coverage gaps and add new articles to an existing collection.

### 1. Scan for gaps

```bash
sh ${CLAUDE_SKILL_DIR}/scripts/run.sh review
```

This writes `.agency-kb/review/gaps.json` listing uncovered source files.

### 2. Analyze and propose

Read the gaps file and explore the uncovered source files. Not every gap needs an article — focus on user-facing features. Present proposals to the user and get approval.

### 3. Write proposals

For each approved article, write a `.json` file to `.agency-kb/review/`:

```json
{
  "title": "Feature Name",
  "path": "category/feature-name",
  "topics": ["Topic 1", "Topic 2"],
  "globs": ["src/features/feature/**/*.ts"],
  "source_id": "github:owner/repo:main",
  "metadata": {
    "source_type": "github",
    "owner": "owner",
    "repo": "repo",
    "branch": "main",
    "globs": ["src/features/feature/**/*.ts"]
  }
}
```

Get `source_id`, `owner`, `repo`, `branch` from an existing article's metadata in `.agency-kb/download/`.

### 4. Publish

```bash
sh ${CLAUDE_SKILL_DIR}/scripts/run.sh review --publish
sh ${CLAUDE_SKILL_DIR}/scripts/run.sh sync --all --publish
```

---

## Reference

### CLI commands

| Command | What it does |
|---------|-------------|
| `agency-kb init` | Validate config and outline, preview bootstrap artifacts |
| `agency-kb init --publish` | Publish initial docs to an empty collection |
| `agency-kb sync` | Export, analyze, generate locally (`--path-prefix`, `--all`, `--diff-base`) |
| `agency-kb sync --publish` | Generate and upload to Agency |
| `agency-kb review` | Scan for uncovered files, write `review/gaps.json` |
| `agency-kb review --publish` | Create stub articles from proposals in `review/` |
| `agency-kb validate-outline` | Check `outline.json` syntax |

### Running the CLI

```bash
sh ${CLAUDE_SKILL_DIR}/scripts/run.sh <command>
```

Auto-installs on first use. Reads API keys from `.agency-kb/.env`.

### Editing an existing outline

- Prefer editing existing articles over regenerating from scratch
- Preserve stable paths — renaming changes the document identity
- After init, `sync` is driven by the collection in Agency, not the local outline
