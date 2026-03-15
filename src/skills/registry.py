# -*- coding: utf-8 -*-
"""Research skills registry loaded from Anthropic-style skill folders."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import logging
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
_REPORT_CACHE: dict | None = None
_LOG = logging.getLogger(__name__)


def _safe_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False
    return default


def _strict_bool(value) -> tuple[bool, bool]:
    if isinstance(value, bool):
        return value, True
    if isinstance(value, int):
        return bool(value), True
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True, True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False, True
    return False, False


def _add_reject(report: dict, skill_dir: str, reason: str) -> None:
    report.setdefault("rejected", []).append({"skill_dir": skill_dir, "reason": reason})
    _LOG.warning("skills: rejected %s: %s", skill_dir, reason)


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
    enabled = _safe_bool(row.get("enabled", True), True)
    requires_kb = _safe_bool(row.get("requires_kb", False), False)
    critical = _safe_bool(row.get("critical", False), False)
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


def _load_from_skill_folders() -> tuple[list[SkillDefinition], dict]:
    root = get_project_root() / "skills"
    report = {
        "source": "skill_folders",
        "root": str(root),
        "found_skill_dirs": 0,
        "loaded": 0,
        "rejected": [],
        "used_legacy_fallback": False,
    }
    if not root.exists():
        return [], report

    rows: list[SkillDefinition] = []
    discovered: list = []
    for skill_dir in sorted(root.iterdir(), key=lambda p: p.name):
        if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
            discovered.append(skill_dir)
    report["found_skill_dirs"] = len(discovered)

    for index, skill_dir in enumerate(discovered):
        skill_md = skill_dir / "SKILL.md"

        try:
            content = skill_md.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            _add_reject(report, skill_dir.name, "SKILL.md unreadable")
            continue
        fm, _body = _frontmatter(content)
        if not fm:
            _add_reject(report, skill_dir.name, "frontmatter missing or invalid")
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

        if not openai_yaml.exists():
            _add_reject(report, skill_dir.name, "agents/openai.yaml missing")
            continue

        raw_id = _meta_value(metadata, "id", None)
        if raw_id is None:
            _add_reject(report, skill_dir.name, "metadata.id missing")
            continue
        skill_id = str(raw_id).strip()
        if not skill_id.startswith("/"):
            _add_reject(report, skill_dir.name, "metadata.id must start with '/'")
            continue

        label_cn_meta = str(
            _meta_value(metadata, "label_cn", interface.get("display_name") or name) or interface.get("display_name") or name
        ).strip()
        description_cn_meta = str(
            _meta_value(
                metadata,
                "description_cn",
                interface.get("short_description") or description,
            )
            or interface.get("short_description")
            or description
        ).strip()
        display_name = str(interface.get("display_name") or "").strip()
        short_description = str(interface.get("short_description") or "").strip()
        if not display_name:
            _add_reject(report, skill_dir.name, "openai.yaml.interface.display_name missing")
            continue
        if not short_description:
            _add_reject(report, skill_dir.name, "openai.yaml.interface.short_description missing")
            continue
        if label_cn_meta and display_name != label_cn_meta:
            _add_reject(
                report,
                skill_dir.name,
                "metadata.label_cn must equal openai.yaml.interface.display_name",
            )
            continue
        if description_cn_meta and short_description != description_cn_meta:
            _add_reject(
                report,
                skill_dir.name,
                "metadata.description_cn must equal openai.yaml.interface.short_description",
            )
            continue

        raw_domain = _meta_value(metadata, "domain", None)
        if raw_domain is None:
            _add_reject(report, skill_dir.name, "metadata.domain missing")
            continue
        domain = str(raw_domain).strip() or "research"
        raw_enabled = _meta_value(metadata, "enabled", None)
        if raw_enabled is None:
            _add_reject(report, skill_dir.name, "metadata.enabled missing")
            continue
        enabled, bool_ok = _strict_bool(raw_enabled)
        if not bool_ok:
            _add_reject(report, skill_dir.name, "metadata.enabled must be a boolean")
            continue
        requires_kb = _safe_bool(_meta_value(metadata, "requires_kb", False), False)
        critical = _safe_bool(_meta_value(metadata, "critical", False), False)
        timeout_ms = int(_meta_value(metadata, "timeout_ms", 2000) or 2000)
        order = int(_meta_value(metadata, "order", (index + 1) * 10) or (index + 1) * 10)
        instruction = str(_meta_value(metadata, "instruction", "") or "").strip()

        if domain != "research":
            _add_reject(report, skill_dir.name, "metadata.domain must be 'research'")
            continue

        rows.append(
            SkillDefinition(
                id=skill_id,
                name=name,
                description=description,
                label_cn=display_name or name,
                description_cn=short_description or description,
                domain=domain,
                enabled=enabled,
                requires_kb=requires_kb,
                critical=critical,
                timeout_ms=max(1, timeout_ms),
                sort_order=order,
                instruction=instruction,
            )
        )
    report["loaded"] = len(rows)
    return rows, report


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
    global _REPORT_CACHE
    with _LOCK:
        if _CACHE is not None:
            return _CACHE
        rows, report = _load_from_skill_folders()
        if int(report.get("found_skill_dirs", 0)) == 0:
            rows = _load_from_legacy_config()
            report["used_legacy_fallback"] = True
            report["loaded"] = len(rows)
        rows = sorted(rows, key=lambda s: (s.sort_order, s.id))
        _CACHE = rows
        _REPORT_CACHE = report
        return rows


def clear_skills_cache() -> None:
    global _CACHE
    global _REPORT_CACHE
    with _LOCK:
        _CACHE = None
        _REPORT_CACHE = None


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


def get_skills_registry_report() -> dict:
    _load_all()
    with _LOCK:
        if _REPORT_CACHE is None:
            return {
                "source": "skill_folders",
                "root": str(get_project_root() / "skills"),
                "found_skill_dirs": 0,
                "loaded": 0,
                "rejected": [],
                "used_legacy_fallback": False,
            }
        return copy.deepcopy(_REPORT_CACHE)


def warmup_skills_registry() -> dict:
    rows = _load_all()
    report = get_skills_registry_report()
    report["loaded"] = len(rows)
    return report
