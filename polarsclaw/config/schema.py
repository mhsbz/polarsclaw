"""Load / save helpers for PolarsClaw configuration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from polarsclaw.config.settings import DEFAULT_CONFIG_PATH, Settings
from polarsclaw.errors import ConfigError, ConfigNotFoundError


def load_config(path: Path | str | None = None) -> Settings:
    """Load a :class:`Settings` instance from *path*.

    Parameters
    ----------
    path:
        JSON config file.  Defaults to ``~/.polarsclaw/config.json``.

    Raises
    ------
    ConfigNotFoundError
        If *path* is given explicitly but does not exist.
    ConfigError
        If the file contains invalid JSON or fails validation.
    """
    path = Path(path) if path else DEFAULT_CONFIG_PATH

    if path != DEFAULT_CONFIG_PATH and not path.exists():
        raise ConfigNotFoundError(f"Config file not found: {path}")

    try:
        return Settings.from_file(path)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ConfigError(f"Invalid configuration in {path}: {exc}") from exc


def save_config(settings: Settings, path: Path | str | None = None) -> Path:
    """Persist *settings* to a JSON file.

    Parameters
    ----------
    settings:
        The :class:`Settings` instance to serialise.
    path:
        Destination file.  Parent directories are created automatically.
        Defaults to ``~/.polarsclaw/config.json``.

    Returns
    -------
    Path
        The resolved path that was written.
    """
    path = Path(path) if path else DEFAULT_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    data: dict[str, Any] = json.loads(
        settings.model_dump_json(
            exclude={"config_dir", "db_path"},
            exclude_defaults=True,
        )
    )

    path.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")
    return path
