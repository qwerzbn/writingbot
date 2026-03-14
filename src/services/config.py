# -*- coding: utf-8 -*-
"""
Configuration Service
=====================

Loads YAML configuration files from the config/ directory.
"""

from pathlib import Path
from typing import Any

import yaml


_config_cache: dict[str, dict] = {}


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent.parent


def load_config(filename: str, project_root: Path | None = None) -> dict[str, Any]:
    """
    Load a YAML configuration file.

    Args:
        filename: Name of the config file (e.g., 'main.yaml')
        project_root: Optional project root path

    Returns:
        Configuration dictionary
    """
    if filename in _config_cache:
        return _config_cache[filename]

    if project_root is None:
        project_root = get_project_root()

    config_path = project_root / "config" / filename

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    _config_cache[filename] = config
    return config


def get_main_config() -> dict[str, Any]:
    """Load the main configuration."""
    return load_config("main.yaml")


def get_agents_config() -> dict[str, Any]:
    """Load the agents configuration."""
    return load_config("agents.yaml")


def get_skills_config() -> dict[str, Any]:
    """Load the skills configuration."""
    return load_config("skills.yaml")


def clear_config_cache():
    """Clear the configuration cache (useful for testing)."""
    _config_cache.clear()
