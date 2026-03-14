# -*- coding: utf-8 -*-
"""Research skills registry loaded from config/skills.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from src.services.config import get_skills_config


@dataclass(frozen=True)
class SkillDefinition:
    id: str
    name: str
    description: str
    domain: str = "research"
    enabled: bool = True
    requires_kb: bool = False
    critical: bool = False
    timeout_ms: int = 2000

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "domain": self.domain,
            "enabled": self.enabled,
            "requires_kb": self.requires_kb,
            "critical": self.critical,
            "timeout_ms": self.timeout_ms,
        }


_LOCK = RLock()
_CACHE: list[SkillDefinition] | None = None


def _normalize_skill_row(row: dict) -> SkillDefinition | None:
    skill_id = str(row.get("id") or "").strip()
    if not skill_id.startswith("/"):
        return None
    name = str(row.get("name") or skill_id).strip() or skill_id
    description = str(row.get("description") or "").strip()
    domain = str(row.get("domain") or "research").strip() or "research"
    enabled = bool(row.get("enabled", True))
    requires_kb = bool(row.get("requires_kb", False))
    critical = bool(row.get("critical", False))
    timeout_ms = int(row.get("timeout_ms", 2000) or 2000)
    return SkillDefinition(
        id=skill_id,
        name=name,
        description=description,
        domain=domain,
        enabled=enabled,
        requires_kb=requires_kb,
        critical=critical,
        timeout_ms=max(1, timeout_ms),
    )


def _load_all() -> list[SkillDefinition]:
    global _CACHE
    with _LOCK:
        if _CACHE is not None:
            return _CACHE
        config = get_skills_config()
        items = config.get("skills", []) if isinstance(config, dict) else []
        rows: list[SkillDefinition] = []
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                normalized = _normalize_skill_row(item)
                if normalized:
                    rows.append(normalized)
        _CACHE = rows
        return rows


def clear_skills_cache() -> None:
    global _CACHE
    with _LOCK:
        _CACHE = None


def list_skills(domain: str = "research", enabled_only: bool = True) -> list[dict]:
    rows = _load_all()
    selected = [s for s in rows if s.domain == domain]
    if enabled_only:
        selected = [s for s in selected if s.enabled]
    return [s.to_dict() for s in selected]


def get_skill(skill_id: str) -> SkillDefinition | None:
    lookup = (skill_id or "").strip()
    if not lookup:
        return None
    for skill in _load_all():
        if skill.id == lookup:
            return skill
    return None


def resolve_skill_chain(skill_ids: list[str], domain: str = "research") -> list[SkillDefinition]:
    if not skill_ids:
        return []
    seen: set[str] = set()
    resolved: list[SkillDefinition] = []
    for raw_id in skill_ids:
        skill_id = (raw_id or "").strip()
        if not skill_id or skill_id in seen:
            continue
        seen.add(skill_id)
        skill = get_skill(skill_id)
        if not skill:
            continue
        if skill.domain != domain:
            continue
        if not skill.enabled:
            continue
        resolved.append(skill)
    return resolved
