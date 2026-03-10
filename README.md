# Agency Skills

Official [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skill plugins for [Agency](https://agency.inc).

## Quick start

Add this marketplace to Claude Code, then install any plugin:

```bash
/plugin marketplace add agency-inc/skills
/plugin install agency-knows@agency-skills
```

## Available plugins

| Plugin | Description |
|--------|-------------|
| [agency-knows](plugins/agency-knows/) | Generate and maintain an Agency knowledge base from source code |

### agency-knows

Turn your codebase into a living knowledge base that Agency's AI assistant can use to answer customer questions.

- **Init** -- interactively author a KB outline from your repo, then seed an empty collection
- **Sync** -- detect source code changes, regenerate affected articles with Claude, and publish updates
- **Preview** -- see which files match each article's glob patterns before generating
- **CI-ready** -- run `agency-knows sync` in GitHub Actions to keep docs in sync on every push

See the full [agency-knows README](plugins/agency-knows/README.md) for usage details.

## Development

Requires [uv](https://docs.astral.sh/uv/) and Python 3.11+.

```bash
make install    # create venv and install dependencies
make lint       # ruff check
make format     # ruff format + auto-fix
make typecheck  # pyright
make check      # lint + typecheck
```

## Repository layout

```
.claude-plugin/
  marketplace.json          # marketplace registry

plugins/
  agency-knows/
    .claude-plugin/
      plugin.json           # plugin manifest
    README.md
    skills/
      agency-knows/
        SKILL.md            # Claude Code skill definition
        scripts/
          install.sh        # one-time CLI setup
          run.sh            # run the CLI (auto-installs)
          pyproject.toml    # Python package config
          src/agency_knows/ # CLI source code
```

## Contact

Questions or feedback: elias@agency.inc
