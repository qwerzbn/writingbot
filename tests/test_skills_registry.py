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


def test_registry_rejects_dirty_skill_and_does_not_fallback_to_legacy(monkeypatch, tmp_path):
    skill_dir = tmp_path / "skills" / "bad-skill"
    _write(
        skill_dir / "SKILL.md",
        """---
name: bad-skill
description: broken metadata/openai mapping
metadata:
  id: /bad-skill
  domain: research
  enabled: true
  label_cn: 技能甲
  description_cn: 这是技能甲说明
---
""",
    )
    _write(
        skill_dir / "agents" / "openai.yaml",
        """interface:
  display_name: "技能乙"
  short_description: "这是技能乙说明"
""",
    )

    monkeypatch.setattr(skills_registry, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(
        skills_registry,
        "get_skills_config",
        lambda: {
            "skills": [
                {
                    "id": "/legacy",
                    "name": "legacy",
                    "description": "legacy",
                    "domain": "research",
                    "enabled": True,
                }
            ]
        },
    )
    skills_registry.clear_skills_cache()

    rows = skills_registry.list_skills(domain="research", enabled_only=True)
    assert rows == []

    report = skills_registry.get_skills_registry_report()
    assert report["found_skill_dirs"] == 1
    assert report["used_legacy_fallback"] is False
    assert len(report["rejected"]) == 1
    assert "label_cn" in report["rejected"][0]["reason"]
