---
name: kb-github
description: Set up and maintain an Agency Knowledge Base from a GitHub repo. Covers authoring an outline, interactively refining the TOC, previewing file matches, and generating content. Use when setting up KB, editing KB outline, or running agency-kb.
---

# Agency Knowledge Base (GitHub)

You are the primary intelligence behind generating a knowledge base. The CLI (`agency-kb`) is a thin utility for config, file-matching preview, and content generation. **You** do the research, codebase exploration, outline generation, and collaborative refinement with the user.

## Data model

The KB is a **filesystem**. Documents live inside collections:

```
Collection (id, name, org_id, source_type)
└── Document (id, title, path, content, collection_id, source_id, metadata)
    - path: slug-based like a filesystem ("integrations/slack", "getting-started/onboarding")
    - path is unique per collection (only one active doc per path)
    - metadata: { source_type: "github", owner, repo, branch, globs, stub }
```

The outline you generate maps to this structure — each article becomes a document with a filesystem path.

**Important:** Collections are created manually in the Agency UI. The skill and CLI do not create collections. The `collection_id` is provided by the user during `init`.

## Product model

Treat the workflow as three separate responsibilities:

- **Collection management** happens manually in the Agency UI
- **Outline authoring** is the skill's job
- **Document bootstrap and updates** are the CLI's job

The intended source of truth by phase is:

- **Prompting context**: `.agency-kb/PROMPT.md`
- **Before bootstrap**: `.agency-kb/outline.json`
- **After bootstrap**: the collection contents in Agency
- **Steady state**: `sync` should be driven by the collection contents in Agency, not by the local outline

The intended command semantics are:

- `init`
  Safe by default. Read existing config and outline first, validate them, inspect the target collection, and materialize what would be uploaded.
- `init --publish`
  Only for bootstrapping an **empty** collection from `.agency-kb/outline.json`.
- `sync`
  The normal ongoing command. Export current docs from Agency, generate updates, and only regenerate changed docs unless `--all` is specified.

Never suggest reinitializing or replacing a non-empty collection automatically.

## CLI commands

| Command | What it does |
|---------|-------------|
| `agency-kb init` | Read config/outline first, validate local state, and prepare bootstrap artifacts |
| `agency-kb init --publish` | Publish the initial docs, but only to an empty collection |
| `agency-kb preview` | Show which source files match each article's globs |
| `agency-kb sync` | Export existing docs → analyze → generate to local files only (supports `--path-prefix`) |
| `agency-kb sync --publish` | Same as sync, but also uploads generated articles to the API |

### Installing and running the CLI

```bash
# One-time install (auto-runs on first use if needed)
sh ${CLAUDE_SKILL_DIR}/scripts/install.sh

# Run any command
sh ${CLAUDE_SKILL_DIR}/scripts/run.sh <command>

# Examples:
sh ${CLAUDE_SKILL_DIR}/scripts/run.sh init --collection-id=<id>
sh ${CLAUDE_SKILL_DIR}/scripts/run.sh preview
sh ${CLAUDE_SKILL_DIR}/scripts/run.sh sync --diff-base=origin/main
```

## Init conversation contract

When the user is creating or updating the outline, guide them through a short, explicit flow.

### 1. Inspect existing state first

Before proposing anything new:
- Read `.agency-kb/config.yaml` if it exists
- Read `.agency-kb/PROMPT.md` if it exists
- Read `.agency-kb/outline.json` if it exists
- Summarize what already exists before suggesting changes

If both files already exist:
- Do not immediately overwrite them
- First ask whether the user wants to keep, refine, or replace the current outline

If only config exists:
- Confirm the collection id and tell the user you will draft or revise the outline next

If only outline exists:
- Summarize the outline and ask whether to reuse it or replace it

If neither exists:
- Start the normal first-time init flow

Also inspect the remote collection state when relevant:
- If the collection is empty, explain that `init --publish` will bootstrap the first document set from the outline
- If the collection already has docs, explain that `sync` is the normal next step and `init` should stay non-destructive

### 2. Keep the user interaction narrow and useful

Ask at most 1-2 focused questions before exploring. Good questions:
- What product or workspace should this outline cover?
- Is there an existing docs or marketing site I should use for terminology?
- Should this outline focus on end-user workflows, admin setup, or both?

Do not ask broad, repetitive brainstorming questions up front. Build a first draft quickly, then refine it with the user.

### 3. Present drafts before writing JSON

Do not dump raw JSON immediately unless the user asks for it.

First present:
- categories
- article titles
- paths
- brief summaries

Group by the first path segment. Highlight uncertain areas explicitly. Ask for approval or edits before writing `.agency-kb/outline.json`.

### 4. Use concrete guidance language

When guiding the user, prefer messages like:
- "I found an existing outline with 34 articles across getting-started, workflow, integrations, and admin. I can refine that instead of starting over."
- "I don't see an outline yet. I'll draft one from the repo structure and then we can trim or split articles."
- "This first draft is intentionally broad. We can remove low-value articles after checking file matches."
- "Before I write the JSON, I want to confirm the category structure and article paths."
- "The collection itself should already exist in Agency. Once the outline looks right, `init --publish` should only be used if that collection is empty."
- "After the first bootstrap, `sync` should be the command people normally run."

Avoid vague prompts like:
- "What do you want in the outline?"
- "Tell me everything about your product."

## Skill workflow

### Phase 1: Gather context

1. Inspect `.agency-kb/config.yaml` and `.agency-kb/outline.json` first if they exist.
2. Inspect `.agency-kb/PROMPT.md` if it exists and use it as project-specific guidance.
3. **Ask the user**: "What's your product website?" only if that context is missing or unclear.
4. **Optionally ask**: "Do you have any screenshots of the product or its navigation you can share?" if the repo structure is not enough.
5. **Research the website** when useful:
   - What the product does (core value proposition)
   - Key features and capabilities
   - Target users/personas
   - Navigation structure (from marketing site or docs)
   - Key terminology and concepts
   - Integrations and connected services
6. **Explore the codebase**:
   - Read the README
   - Scan the directory structure (use `Glob` with patterns like `**/*`)
   - Look for route/page files to understand product navigation:
     - Next.js: `app/**/page.tsx`, `pages/**/*.tsx`
     - React Router: files with `<Route` or `createBrowserRouter`
     - Other frameworks: look for routing patterns
   - Read key config files (`package.json`, `pyproject.toml`, etc.)
   - Skim a few feature directories to understand the codebase organization

### Phase 2: Generate the outline

Using everything you gathered, generate `.agency-kb/outline.json`:

```json
{
  "product_name": "Acme CRM",
  "product_summary": "Acme CRM helps sales teams manage their pipeline...",
  "articles": [
    {
      "title": "Pipeline management",
      "path": "features/pipeline-management",
      "summary": "How to create, view, and manage your sales pipeline",
      "globs": ["src/features/pipeline/**/*.ts", "src/pages/pipeline/**"],
      "topics": [
        "What the pipeline view shows and how to navigate it",
        "Creating and moving deals through stages",
        "Customizing pipeline stages",
        "Filtering and sorting deals",
        "Pipeline analytics and forecasting"
      ]
    }
  ]
}
```

**Outline rules:**
- **User-facing only**: Every article documents something a user can see, do, or configure. Skip internals, dev tooling, CI/CD, infrastructure.
- **Right granularity**: One article per feature area. Think Stripe/Linear/Notion help docs level.
- **Paths**: Lowercase slug paths with forward slashes, no `.md` suffix, and 2-3 segments total (`integrations/slack`, `admin/security/sso`; not `Integrations/Slack` or `integrations/slack.md`).
- **Globs**: Specific patterns mapping articles to source files. Use the directory structure you explored.
- **Topics**: 3-8 bullet points per article. Focus on user-facing behavior, not implementation.
- **Completeness**: Cover all major product areas. Better to propose too many (they can be removed).

### Phase 3: Brainstorm with the user (interactive loop)

Present the proposed TOC clearly and brainstorm with the user. This is a collaborative conversation — help them think through what should be documented.

**How to present the outline:**
- Group articles by category (the path prefix)
- Show title, path, and a brief summary for each
- Highlight any areas you're unsure about

**Prompt the user with questions like:**
- "Does this cover all the major features your users care about?"
- "Are there features I missed that aren't obvious from the codebase?"
- "Should any of these be split or merged?"
- "Are the categories/groupings right?"

**Common refinement actions:**

| User says | You do |
|-----------|--------|
| "Add an article about billing" | Add a new entry with appropriate title, path, globs, and topics |
| "Remove the deployment article" | Remove that entry |
| "Merge auth and SSO" | Combine both entries — merge globs and topics |
| "Split settings into general and admin" | Create two entries from one |
| "The auth glob is wrong, it lives in lib/auth/" | Fix the `globs` array |
| "Add a topic about rate limiting to the API article" | Append to that article's `topics` |
| "Show me what files match" | Run `agency-kb preview` and present the results |

**After each edit:**
- Show the updated article(s) affected
- Offer to run `agency-kb preview` to verify file matches
- Ask if they want to continue refining or proceed

### Phase 4: Write the outline

When the user is satisfied:
1. Write the final `.agency-kb/outline.json`
2. Write or update `.agency-kb/PROMPT.md` if you gathered useful product-specific instructions or terminology
3. Make sure the paths follow the path rules and the JSON is valid
4. Tell the user the outline is ready for `init`
5. If the collection is empty, explain that `init --publish` is the bootstrap step
6. If the collection already has docs, explain that they should use `sync` instead of trying to replace the collection

### Phase 5: Generate content

1. For an empty collection, use `init` to inspect/bootstrap first
2. For a non-empty collection, run `agency-kb sync --all` for the first full generation preview (local files only by default)
3. Preview results in `.agency-kb/upload/` and compare against `.agency-kb/download/`
4. If the user approves, run `agency-kb sync --all --publish` to push to API

`sync` also saves before/after artifacts to disk:
- `.agency-kb/download/<path>.md`
- `.agency-kb/download/<path>.json`
- `.agency-kb/upload/<path>.md`
- `.agency-kb/upload/<path>.json`

## Editing the outline file

When editing `.agency-kb/outline.json`, follow these rules:

- **Paths**: Use lowercase slug paths with no `.md` suffix and 2-3 segments total (`integrations/slack`, `admin/security/sso`; not `Integrations/Slack` or `integrations/slack.md`)
- **Globs**: Be specific. Prefer `src/features/auth/**/*.ts` over `**/*auth*`
- **Topics**: 3-8 bullet points per article. Focus on user-facing behavior, not implementation
- **Titles**: Use natural language, like a help article ("Task management", not "Tasks CRUD")
- Always preserve `product_name` and `product_summary` at the top level
- Keep the JSON valid and well-formatted (2-space indent)

When revising an existing outline:
- Prefer editing the existing article set over regenerating everything from scratch
- Preserve stable paths unless the user explicitly wants to rename or regroup them
- If you rename a path, call it out clearly because it changes the document identity in the KB
- Do not imply that editing the outline alone will change a non-empty collection. After bootstrap, `sync` is driven by the existing docs in Agency.

## Environment variables

- `AGENCY_API_KEY` — required for `sync`
- `ANTHROPIC_API_KEY` — required for `sync` (LLM content generation)

## For CI (GitHub Actions)

After the initial setup, the `sync` command handles incremental updates:

```yaml
- name: Update knowledge base
  env:
    AGENCY_API_KEY: ${{ secrets.AGENCY_API_KEY }}
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  run: |
    pip install agency-kb
    agency-kb sync --publish --diff-base=origin/main
```
