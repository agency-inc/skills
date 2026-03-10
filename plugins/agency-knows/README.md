# Agency Knowledge Base (GitHub)

Generate and maintain knowledge base articles from source code using Claude.

## Quick start

```bash
# Install (requires uv or pip)
uvx --from git+https://github.com/agency-inc/skills#subdirectory=plugins/agency-knows agency-knows --help

# Or clone and install locally
git clone https://github.com/agency-inc/skills.git
cd skills/plugins/agency-knows
uv venv .venv && uv pip install -e "."

# Initialize in your repo
agency-knows init --collection-id=<your-collection-id>

# Use the /agency:kb-github skill to author .agency-kb/outline.json
# Add repository-specific writing and product instructions in .agency-kb/PROMPT.md

# Materialize initial upload artifacts locally (safe by default)
agency-knows init

# Preview file matches from the outline
agency-knows preview

# Publish the initial docs only if the collection is empty
export AGENCY_API_KEY=<your-api-key>
agency-knows init --publish

# Sync existing KB docs from source code
agency-knows sync --diff-base=origin/main

# Sync only one area
agency-knows sync --path-prefix=workflow --diff-base=origin/main

# Preview generated docs locally instead of uploading
agency-knows sync --diff-base=origin/main --dry-run
```

## How it works

### Init (first run)

1. Create the collection manually in Agency UI
2. `agency-knows init --collection-id=...` writes `.agency-kb/config.yaml`
3. The `/agency:kb-github` skill authors `.agency-kb/outline.json`
4. `.agency-kb/PROMPT.md` provides repository-specific prompt instructions for init and sync
5. `agency-knows init` validates the outline and materializes initial files into `.agency-kb/upload/`
6. `agency-knows init --publish` uploads those initial docs, but only if the collection is empty
7. `agency-knows preview` shows which source files match each planned article

Path rules for outline articles:
- Do not include a `.md` suffix
- Use lowercase slug segments only
- Use 2 or 3 segments total, e.g. `integrations/slack` or `admin/security/sso`

### Sync (ongoing updates)

1. **Export** — fetch current KB docs from the API
2. **Analyze** — resolve glob patterns, score file relevance, detect git changes
3. **Generate** — call Claude with the previous doc content plus source code context
4. **Upload** — update the KB documents in Agency, or write preview files locally in `--dry-run`

`sync` does not create or seed documents. If the configured collection is empty, run init first.

Every `sync` run also saves local artifacts:
- `.agency-kb/download/<path>.md` — the current document fetched from Agency
- `.agency-kb/download/<path>.json` — metadata and globs for the fetched doc
- `.agency-kb/upload/<path>.md` — the newly generated document
- `.agency-kb/upload/<path>.json` — metadata and file match info for the generated doc

## GitHub Actions

```yaml
- name: Update knowledge base
  env:
    AGENCY_API_KEY: ${{ secrets.AGENCY_API_KEY }}
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  run: |
    pip install "agency-knows @ git+https://github.com/agency-inc/skills#subdirectory=plugins/agency-knows"
    agency-knows sync --diff-base=origin/main
```

## Configuration

Config lives in `.agency-kb/config.yaml`:

```yaml
collection_id: "github:acme/app:product-outline"
api_base_url: "https://api.agency.inc/external"
```

Prompt instructions live in `.agency-kb/PROMPT.md`. Both `init` and `sync` read that file if it exists.
