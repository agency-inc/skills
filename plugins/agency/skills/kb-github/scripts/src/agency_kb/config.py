"""Config file loading and defaults."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import ValidationError

from agency_kb.schemas import KbGenConfig

CONFIG_DIR = ".agency-kb"
CONFIG_FILE = "config.yaml"
OUTLINE_FILE = "outline.json"
PROMPT_FILE = "PROMPT.md"
ANALYSIS_FILE = "analysis.json"
API_KEY_ENV_VAR = "AGENCY_API_KEY"


def config_dir(repo_root: Path) -> Path:
    return repo_root / CONFIG_DIR


def config_path(repo_root: Path) -> Path:
    return config_dir(repo_root) / CONFIG_FILE


def outline_path(repo_root: Path) -> Path:
    return config_dir(repo_root) / OUTLINE_FILE


def prompt_path(repo_root: Path) -> Path:
    return config_dir(repo_root) / PROMPT_FILE


def analysis_path(repo_root: Path) -> Path:
    return config_dir(repo_root) / ANALYSIS_FILE


def load_dotenv() -> None:
    """Load .env file if it exists. Checks .agency-kb/.env, repo root, then package dir."""
    cwd = Path.cwd()
    for env_file in [
        cwd / CONFIG_DIR / ".env",
        cwd / ".env",
        Path(__file__).resolve().parent.parent.parent / ".env",
    ]:
        if env_file.is_file():
            for raw_line in env_file.read_text(encoding="utf-8").splitlines():
                stripped = raw_line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key, _, value = stripped.partition("=")
                key = key.strip()
                value = value.strip().strip("\"'")
                if key and key not in os.environ:
                    os.environ[key] = value
            return


def load_config(repo_root: Path) -> KbGenConfig:
    path = config_path(repo_root)
    if not path.exists():
        raise FileNotFoundError(f"No config found at {path}. Run `agency-kb init` to create one.")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    try:
        return KbGenConfig.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"Invalid config at {path}: {exc}") from exc


def resolve_api_key(api_key: str | None) -> str:
    load_dotenv()
    resolved = api_key or os.environ.get(API_KEY_ENV_VAR)
    if not resolved:
        raise ValueError(
            f"API key not found. Either:\n"
            f"  - Pass --api-key=<key>\n"
            f"  - Set {API_KEY_ENV_VAR} in your environment\n"
            f"  - Add {API_KEY_ENV_VAR}=<key> to .agency-kb/.env"
        )
    return resolved


def find_repo_root() -> Path:
    """Walk up from cwd to find the git root."""
    current = Path.cwd().resolve()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return Path.cwd().resolve()
