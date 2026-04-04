#!/usr/bin/env python3

from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple
import os


@dataclass
class AnalysisResult:
    packages: Set[str]
    edges: Dict[Tuple[str, str], int]
    scc_cycles: List[Set[str]]


def module_name_from_path(src_root: Path, file_path: Path) -> str:
    rel = file_path.relative_to(src_root.parent).with_suffix("")
    return ".".join(rel.parts)


def package_name(module_name: str) -> str | None:
    parts = module_name.split(".")
    if len(parts) < 2 or parts[0] != "src":
        return None
    return parts[1]


def resolve_from_import(current_module: str, level: int, module: str | None) -> str | None:
    if level < 0:
        return None
    package_parts = current_module.split(".")[:-1]
    if level == 0:
        base_parts = []
    else:
        if level > len(package_parts):
            return None
        base_parts = package_parts[: len(package_parts) - level + 1]
    if module:
        base_parts += module.split(".")
    if not base_parts:
        return None
    return ".".join(base_parts)


def parse_import_targets(file_path: Path, current_module: str) -> Set[str]:
    targets: Set[str] = set()
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
    except Exception:
        return targets

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                targets.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            resolved = resolve_from_import(current_module, node.level, node.module)
            if resolved:
                targets.add(resolved)
    return targets


def list_python_files(src_root: Path) -> Iterable[Path]:
    for path in src_root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        yield path


def analyze(src_root: Path, simulate_new_cycle: bool = False) -> AnalysisResult:
    packages: Set[str] = set()
    edge_counts: Dict[Tuple[str, str], int] = defaultdict(int)

    for py_file in list_python_files(src_root):
        current_module = module_name_from_path(src_root, py_file)
        src_pkg = package_name(current_module)
        if not src_pkg:
            continue
        packages.add(src_pkg)
        targets = parse_import_targets(py_file, current_module)
        for target in targets:
            if not target.startswith("src."):
                continue
            dst_pkg = package_name(target)
            if not dst_pkg:
                continue
            packages.add(dst_pkg)
            if src_pkg != dst_pkg:
                edge_counts[(src_pkg, dst_pkg)] += 1

    if simulate_new_cycle:
        packages.update({"drill_alpha", "drill_beta"})
        edge_counts[("drill_alpha", "drill_beta")] += 1
        edge_counts[("drill_beta", "drill_alpha")] += 1

    cycles = find_cycles(packages, edge_counts)
    return AnalysisResult(packages=packages, edges=dict(edge_counts), scc_cycles=cycles)


def find_cycles(packages: Set[str], edges: Dict[Tuple[str, str], int]) -> List[Set[str]]:
    graph: Dict[str, Set[str]] = {pkg: set() for pkg in packages}
    for (src, dst), _ in edges.items():
        graph.setdefault(src, set()).add(dst)
        graph.setdefault(dst, set())

    index = 0
    stack: List[str] = []
    on_stack: Set[str] = set()
    indices: Dict[str, int] = {}
    lowlink: Dict[str, int] = {}
    sccs: List[Set[str]] = []

    def strongconnect(v: str) -> None:
        nonlocal index
        indices[v] = index
        lowlink[v] = index
        index += 1
        stack.append(v)
        on_stack.add(v)

        for w in graph.get(v, set()):
            if w not in indices:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], indices[w])

        if lowlink[v] == indices[v]:
            scc: Set[str] = set()
            while True:
                w = stack.pop()
                on_stack.remove(w)
                scc.add(w)
                if w == v:
                    break
            sccs.append(scc)

    for node in sorted(graph.keys()):
        if node not in indices:
            strongconnect(node)

    cycles: List[Set[str]] = []
    for scc in sccs:
        if len(scc) > 1:
            cycles.append(scc)
            continue
        node = next(iter(scc))
        if node in graph.get(node, set()):
            cycles.append(scc)
    return cycles


def cycle_key(cycle: Set[str]) -> str:
    return " <-> ".join(sorted(cycle))


def load_baseline(path: Path) -> Set[str]:
    if not path.exists():
        return set()
    lines = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        row = raw.strip()
        if not row or row.startswith("#"):
            continue
        lines.add(row)
    return lines


def write_baseline(path: Path, cycle_keys: Set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = ["# Dependency cycle baseline (package-level)", "# One SCC per line", ""]
    rows += sorted(cycle_keys)
    path.write_text("\n".join(rows).rstrip() + "\n", encoding="utf-8")


def to_mermaid(packages: Set[str], edges: Dict[Tuple[str, str], int]) -> str:
    rows: List[str] = ["flowchart LR"]
    for pkg in sorted(packages):
        node = pkg.upper().replace("-", "_")
        rows.append(f'  {node}["{pkg}"]')
    for (src, dst), weight in sorted(edges.items(), key=lambda x: (-x[1], x[0][0], x[0][1])):
        src_node = src.upper().replace("-", "_")
        dst_node = dst.upper().replace("-", "_")
        rows.append(f"  {src_node} -->|{weight}| {dst_node}")
    return "\n".join(rows)


def build_markdown(
    result: AnalysisResult,
    baseline_cycles: Set[str],
    detected_cycles: Set[str],
    new_cycles: Set[str],
    resolved_cycles: Set[str],
) -> str:
    top_edges = sorted(result.edges.items(), key=lambda x: (-x[1], x[0][0], x[0][1]))[:20]
    lines: List[str] = [
        "# Module Dependency Graph",
        "",
        f"Generated at: {datetime.now().isoformat()}",
        "",
        "## Summary",
        "",
        f"- packages: `{len(result.packages)}`",
        f"- dependency_edges: `{len(result.edges)}`",
        f"- detected_cycle_scc: `{len(detected_cycles)}`",
        f"- baseline_cycle_scc: `{len(baseline_cycles)}`",
        f"- new_cycle_scc: `{len(new_cycles)}`",
        f"- resolved_cycle_scc: `{len(resolved_cycles)}`",
        "",
        "## Cross-Module Dependency Graph (package-level)",
        "",
        "```mermaid",
        to_mermaid(result.packages, result.edges),
        "```",
        "",
        "## Top Cross-Module Edges",
        "",
        "| Edge | Count |",
        "|---|---:|",
    ]
    for (src, dst), w in top_edges:
        lines.append(f"| `{src} -> {dst}` | {w} |")

    lines += ["", "## Cycle Report", ""]
    if not detected_cycles:
        lines.append("- No cycle detected.")
    else:
        for c in sorted(detected_cycles):
            mark = "NEW" if c in new_cycles else "KNOWN"
            lines.append(f"- [{mark}] `{c}`")

    if resolved_cycles:
        lines += ["", "## Resolved Cycles", ""]
        for c in sorted(resolved_cycles):
            lines.append(f"- `{c}`")

    return "\n".join(lines) + "\n"


def emit_annotations(new_cycles: Set[str], known_cycles: Set[str], warn_only: bool) -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    if new_cycles:
        text = "; ".join(sorted(new_cycles))
        if warn_only:
            print(f"::warning title=Dependency Guard::new cycles detected (warn-only): {text}")
        else:
            print(f"::error title=Dependency Guard::new cycles detected: {text}")
    elif known_cycles:
        text = "; ".join(sorted(known_cycles))
        print(f"::warning title=Dependency Guard::known baseline cycles present: {text}")
    else:
        print("::notice title=Dependency Guard::no new dependency cycles detected")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate package-level dependency graph and detect cycles.")
    parser.add_argument("--src", default="src", help="Source root (default: src)")
    parser.add_argument("--output", default="docs/upgrade/module-dependency-graph.md", help="Markdown output path")
    parser.add_argument(
        "--baseline",
        default="config/dependency-cycles-baseline.txt",
        help="Baseline cycle file (one SCC key per line)",
    )
    parser.add_argument("--warn-only", action="store_true", help="Do not fail on new cycles")
    parser.add_argument("--update-baseline", action="store_true", help="Write detected cycles to baseline and exit")
    parser.add_argument("--simulate-new-cycle", action="store_true", help="Inject a synthetic cycle for drill")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    src_root = (root / args.src).resolve()
    output_path = (root / args.output).resolve()
    baseline_path = (root / args.baseline).resolve()

    result = analyze(src_root, simulate_new_cycle=args.simulate_new_cycle)
    detected_cycle_keys = {cycle_key(c) for c in result.scc_cycles}

    if args.update_baseline:
        write_baseline(baseline_path, detected_cycle_keys)
        print(f"[dep-guard] baseline updated: {baseline_path}")
        print(f"[dep-guard] cycle_scc={len(detected_cycle_keys)}")
        return 0

    baseline_cycles = load_baseline(baseline_path)
    new_cycles = detected_cycle_keys - baseline_cycles
    known_cycles = detected_cycle_keys & baseline_cycles
    resolved_cycles = baseline_cycles - detected_cycle_keys

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        build_markdown(result, baseline_cycles, detected_cycle_keys, new_cycles, resolved_cycles),
        encoding="utf-8",
    )

    print(f"[dep-guard] output={output_path}")
    print(f"[dep-guard] packages={len(result.packages)} edges={len(result.edges)}")
    print(
        "[dep-guard] summary: detected=%d baseline=%d new=%d resolved=%d"
        % (len(detected_cycle_keys), len(baseline_cycles), len(new_cycles), len(resolved_cycles))
    )
    if new_cycles:
        for c in sorted(new_cycles):
            print(f"[dep-guard] NEW {c}")
    if known_cycles:
        for c in sorted(known_cycles):
            print(f"[dep-guard] KNOWN {c}")
    if resolved_cycles:
        for c in sorted(resolved_cycles):
            print(f"[dep-guard] RESOLVED {c}")

    emit_annotations(new_cycles, known_cycles, args.warn_only)

    if new_cycles and not args.warn_only:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
