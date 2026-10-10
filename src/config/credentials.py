"""Local acquisition credentials, kept separate from research configuration/provenance."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

DEFAULT_CREDENTIALS_FILE = Path("config/credentials.local.toml")


def load_tiingo_token(
    *, environment_name: str = "TIINGO_API_TOKEN",
    credentials_file: Path = DEFAULT_CREDENTIALS_FILE,
) -> str:
    """Prefer the named environment variable, then a local TOML file.

    Never expose parser diagnostics: malformed source text can contain credentials.
    This loader does not mutate the process environment or research configuration.
    """
    token: object = os.environ.get(environment_name, "").strip()
    if not token:
        try:
            with credentials_file.open("rb") as stream:
                config = tomllib.load(stream)
        except FileNotFoundError:
            raise ValueError(
                "Tiingo credential missing: set the token environment variable or "
                "tiingo.api_token in the local credentials file"
            ) from None
        except (OSError, ValueError):
            raise ValueError("Cannot read local credentials as valid TOML") from None
        section = config.get("tiingo")
        if not isinstance(section, dict):
            raise ValueError("Local credentials require a [tiingo] section")
        token = section.get("api_token")
    if not isinstance(token, str) or not token.strip():
        raise ValueError("Tiingo api_token must be a nonempty string")
    token = token.strip()
    if any(character.isspace() for character in token):
        raise ValueError("Tiingo api_token must not contain whitespace")
    return token
