# Module Dependency Graph

Generated at: 2026-03-16T18:15:44.114715

## Summary

- packages: `13`
- dependency_edges: `25`
- detected_cycle_scc: `1`
- baseline_cycle_scc: `1`
- new_cycle_scc: `0`
- resolved_cycle_scc: `0`

## Cross-Module Dependency Graph (package-level)

```mermaid
flowchart LR
  __INIT__["__init__"]
  AGENTS["agents"]
  API["api"]
  EVALUATION["evaluation"]
  KNOWLEDGE["knowledge"]
  ORCHESTRATOR["orchestrator"]
  PARSING["parsing"]
  PROCESSING["processing"]
  RAG["rag"]
  RETRIEVAL["retrieval"]
  SERVICES["services"]
  SESSION["session"]
  SKILLS["skills"]
  API -->|8| KNOWLEDGE
  API -->|8| SERVICES
  API -->|6| ORCHESTRATOR
  AGENTS -->|3| SERVICES
  API -->|3| RETRIEVAL
  AGENTS -->|2| RAG
  API -->|2| SKILLS
  ORCHESTRATOR -->|2| AGENTS
  ORCHESTRATOR -->|2| KNOWLEDGE
  ORCHESTRATOR -->|2| RETRIEVAL
  ORCHESTRATOR -->|2| SERVICES
  API -->|1| EVALUATION
  API -->|1| PARSING
  API -->|1| PROCESSING
  API -->|1| RAG
  API -->|1| SESSION
  EVALUATION -->|1| ORCHESTRATOR
  EVALUATION -->|1| SERVICES
  ORCHESTRATOR -->|1| SKILLS
  RAG -->|1| SERVICES
  RETRIEVAL -->|1| RAG
  SERVICES -->|1| KNOWLEDGE
  SERVICES -->|1| RETRIEVAL
  SESSION -->|1| SERVICES
  SKILLS -->|1| SERVICES
```

## Top Cross-Module Edges

| Edge | Count |
|---|---:|
| `api -> knowledge` | 8 |
| `api -> services` | 8 |
| `api -> orchestrator` | 6 |
| `agents -> services` | 3 |
| `api -> retrieval` | 3 |
| `agents -> rag` | 2 |
| `api -> skills` | 2 |
| `orchestrator -> agents` | 2 |
| `orchestrator -> knowledge` | 2 |
| `orchestrator -> retrieval` | 2 |
| `orchestrator -> services` | 2 |
| `api -> evaluation` | 1 |
| `api -> parsing` | 1 |
| `api -> processing` | 1 |
| `api -> rag` | 1 |
| `api -> session` | 1 |
| `evaluation -> orchestrator` | 1 |
| `evaluation -> services` | 1 |
| `orchestrator -> skills` | 1 |
| `rag -> services` | 1 |

## Cycle Report

- [KNOWN] `rag <-> retrieval <-> services`
