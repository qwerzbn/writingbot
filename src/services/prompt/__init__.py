# -*- coding: utf-8 -*-
"""
Prompt Management Service
==========================

Loads prompts from YAML files organized by module and language.
"""

from src.services.prompt.manager import PromptManager, get_prompt_manager

__all__ = ["PromptManager", "get_prompt_manager"]
