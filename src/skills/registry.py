# -*- coding: utf-8 -*-
"""Research skills registry loaded from Anthropic-style skill folders."""

from __future__ import annotations

from dataclasses import dataclass
import re
from threading import RLock

import yaml

from src.services.config import get_project_root, get_skills_config


@dataclass(frozen=True)
class SkillDefinition:
    id: str
    name: str
    description: str
    label_cn: str = ""
    description_cn: str = ""
    domain: str = "research"
    enabled: bool = True
    requires_kb: bool = False
    critical: bool = False
    timeout_ms: int = 2000
    sort_order: int = 1000
    instruction: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "label_cn": self.label_cn or self.name,
            "description_cn": self.description_cn or self.description,
            "domain": self.domain,
            "enabled": self.enabled,
            "requires_kb": self.requires_kb,
            "critical": self.critical,
            "timeout_ms": self.timeout_ms,
        }


_LOCK = RLock()
_CACHE: list[SkillDefinition] | None = None


def _frontmatter(md: str) -> tuple[dict, str]:
    clean = md.lstrip("\ufeff")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", clean, re.DOTALL)
    if not match:
        return {}, clean
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except Exception:  # noqa: BLE001
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    body = clean[match.end() :]
    return meta, body


def _meta_value(meta: dict, key: str, default=None):
    if key in meta:
        return meta[key]
    alt = key.replace("_", "-")
    if alt in meta:
        return meta[alt]
    return default


def _normalize_skill_row(row: dict, index: int = 0) -> SkillDefinition | None:
    skill_id = str(row.get("id") or "").strip()
    if not skill_id.startswith("/"):
        return None
    name = str(row.get("name") or skill_id).strip() or skill_id
    description = str(row.get("description") or "").strip()
    label_cn = str(row.get("label_cn") or name).strip() or name
    description_cn = str(row.get("description_cn") or description).strip() or description
    domain = str(row.get("domain") or "research").strip() or "research"
    enabled = bool(row.get("enabled", True))
    requires_kb = bool(row.get("requires_kb", False))
    critical = bool(row.get("critical", False))
    timeout_ms = int(row.get("timeout_ms", 2000) or 2000)
    sort_order = int(row.get("order", index) or index)
    instruction = str(row.get("instruction") or "").strip()
    return SkillDefinition(
        id=skill_id,
        name=name,
        description=description,
        label_cn=label_cn,
        description_cn=description_cn,
        domain=domain,
        enabled=enabled,
        requires_kb=requires_kb,
        critical=critical,
        timeout_ms=max(1, timeout_ms),
        sort_order=sort_order,
        instruction=instruction,
    )


def _load_from_skill_folders() -> list[SkillDefinition]:
    root = get_project_root() / "skills"
    if not root.exists():
        return []

    rows: list[SkillDefinition] = []
    for index, skill_dir in enumerate(sorted(root.iterdir(), key=lambda p: p.name)):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue

        try:
            content = skill_md.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            continue
        fm, _body = _frontmatter(content)
        if not fm:
            continue

        name = str(fm.get("name") or skill_dir.name).strip() or skill_dir.name
        description = str(fm.get("description") or "").strip()
        metadata = fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {}

        openai_yaml = skill_dir / "agents" / "openai.yaml"
        interface = {}
        if openai_yaml.exists():
            try:
                openai_meta = yaml.safe_load(openai_yaml.read_text(encoding="utf-8")) or {}
                if isinstance(openai_meta, dict):
                    interface = openai_meta.get("interface") if isinstance(openai_meta.get("interface"), dict) else {}
            except Exception:  # noqa: BLE001
                interface = {}

        skill_id = str(_meta_value(metadata, "id", f"/{skill_dir.name}") or f"/{skill_dir.name}").strip()
        if not skill_id.startswith("/"):
            skill_id = f"/{skill_id.lstrip('/')}"

        label_cn = str(
            _meta_value(metadata, "label_cn", interface.get("display_name") or name) or interface.get("display_name") or name
        ).strip()
        description_cn = str(
            _meta_value(
                metadata,
                "description_cn",
                interface.get("short_description") or description,
            )
            or interface.get("short_description")
            or description
        ).strip()
        domain = str(_meta_value(metadata, "domain", "research") or "research").strip() or "research"
        enabled = bool(_meta_value(metadata, "enabled", True))
        requires_kb = bool(_meta_value(metadata, "requires_kb", False))
        critical = bool(_meta_value(metadata, "critical", False))
        timeout_ms = int(_meta_value(metadata, "timeout_ms", 2000) or 2000)
        order = int(_meta_value(metadata, "order", (index + 1) * 10) or (index + 1) * 10)
        instruction = str(_meta_value(metadata, "instruction", "") or "").strip()

        rows.append(
            SkillDefinition(
                id=skill_id,
                name=name,
                description=description,
                label_cn=label_cn or name,
                description_cn=description_cn or description,
                domain=domain,
                enabled=enabled,
                requires_kb=requires_kb,
                critical=critical,
                timeout_ms=max(1, timeout_ms),
                sort_order=order,
                instruction=instruction,
            )
        )
    return rows


def _load_from_legacy_config() -> list[SkillDefinition]:
    config = get_skills_config()
    items = config.get("skills", []) if isinstance(config, dict) else []
    rows: list[SkillDefinition] = []
    if isinstance(items, list):
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            normalized = _normalize_skill_row(item, index=index)
            if normalized:
                rows.append(normalized)
    return rows


def _load_all() -> list[SkillDefinition]:
    global _CACHE
    with _LOCK:
        if _CACHE is not None:
            return _CACHE
        rows = _load_from_skill_folders()
        if not rows:
            rows = _load_from_legacy_config()
        rows = sorted(rows, key=lambda s: (s.sort_order, s.id))
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
