# Refactor Direction

- Clean before expanding.
- Delete redundant files and dead code when safe.
- Prefer one runtime over multiple competing orchestrators.
- Prefer one primary typed state model over parallel state worlds.
- Prefer fewer, higher-value agents over many overlapping agent classes.
- Treat planning, search, report, and review as canonical workflow agents.
- Treat retrieval, prompting, rendering, KB access, and validation as shared capabilities.
- Demote legacy wrappers into adapters when they do not own a real workflow boundary.
- Preserve evidence traceability and reviewer-based validation.
- Keep changes incremental, reviewable, and easy to explain.