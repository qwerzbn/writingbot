## Summary

<!-- What changed and why -->

## Architecture Guard Checklist

- [ ] If I touched `api/chat` runtime path, I updated `docs/upgrade/architecture.md` accordingly.
- [ ] I ran `bash scripts/verify_architecture_chat_refs.sh` (or confirmed it in CI logs).
- [ ] I generated/checked structure snapshot via `bash scripts/print_repo_structure.sh --markdown`.
- [ ] If this PR changes architecture guard behavior, I ran `bash scripts/rehearse_arch_guard_pr.sh` and attached summary path.
- [ ] If this PR is a drill PR, title includes `[arch-drill]`.

## Validation

- [ ] Backend tests
- [ ] Web quality checks
