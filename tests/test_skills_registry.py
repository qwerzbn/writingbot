from pathlib import Path

import src.skills.registry as skills_registry


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_registry_loads_anthropic_skill_folder(monkeypatch, tmp_path):
    skill_dir = tmp_path / "skills" / "demo-skill"
    _write(
        skill_dir / "SKILL.md",
        """---
name: demo-skill
description: Use this skill to test folder loading.
metadata:
  id: /demo-skill
  domain: research
  enabled: true
  requires-kb: true
  critical: true
  timeout-ms: 3456
  order: 5
---

# Demo
""",
    )
    _write(
        skill_dir / "agents" / "openai.yaml",
        """interface:
  display_name: "演示技能"
  short_description: "用于验证 skills 目录加载"
  default_prompt: "Use $demo-skill for loading checks."
""",
    )

    monkeypatch.setattr(skills_registry, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(skills_registry, "get_skills_config", lambda: {"skills": []})
    skills_registry.clear_skills_cache()

    rows = skills_registry.list_skills(domain="research", enabled_only=True)
    assert len(rows) == 1
    item = rows[0]
    assert item["id"] == "/demo-skill"
    assert item["label_cn"] == "演示技能"
    assert item["description_cn"] == "用于验证 skills 目录加载"
    assert item["requires_kb"] is True
    assert item["critical"] is True
    assert item["timeout_ms"] == 3456

