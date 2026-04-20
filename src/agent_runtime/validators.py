from __future__ import annotations

from typing import Any

from src.agent_runtime.state import RuntimeState, model_to_dict


def _diff_paths(before: Any, after: Any, prefix: str = "") -> set[str]:
    if type(before) is not type(after):
        return {prefix or "<root>"}
    if isinstance(before, dict):
        changed: set[str] = set()
        keys = set(before) | set(after)
        for key in keys:
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            if key not in before or key not in after:
                changed.add(child_prefix)
                continue
            changed.update(_diff_paths(before[key], after[key], child_prefix))
        return changed
    if isinstance(before, list):
        return {prefix or "<root>"} if before != after else set()
    return {prefix or "<root>"} if before != after else set()


def assert_only_owned_fields_mutated(
    before: RuntimeState,
    after: RuntimeState,
    *,
    owner: str,
    allowed_paths: set[str],
) -> None:
    changed_paths = _diff_paths(model_to_dict(before), model_to_dict(after))
    illegal = [
        path
        for path in changed_paths
        if not any(path == allowed or path.startswith(f"{allowed}.") for allowed in allowed_paths)
    ]
    if illegal:
        joined = ", ".join(sorted(illegal))
        raise ValueError(f"{owner} mutated state outside its ownership: {joined}")
