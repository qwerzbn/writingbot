# WritingBot Secret Exposure Incident Record

## Incident Summary
- Incident type: sensitive configuration (`.env`) accidentally tracked by Git.
- Scope: local development secrets (LLM API key and related runtime settings).
- Disposal strategy: standard remediation (remove tracking + rotate keys), no history rewrite.

## Timeline (Asia/Shanghai)
- 2026-04-06 10:00: identified `.env` and runtime artifacts were tracked.
- 2026-04-06 10:10: added repository ignore rules for `.env`, logs, build outputs, and runtime data.
- 2026-04-06 10:20: removed tracked sensitive/runtime files from Git index.
- 2026-04-06 10:30: settings API updated to return masked key only.
- 2026-04-06 10:40: key rotation checklist issued for final validation.

## Key Rotation Checklist
1. Revoke old provider keys in vendor console.
2. Generate new keys with least privilege.
3. Update local `.env` and verify no secret is tracked by Git.
4. Validate runtime with `/api/settings/llm/test`.
5. Record rotation timestamp and operator below.

## Rotation Record
- Provider: pending
- Old key revoked at: pending
- New key activated at: pending
- Operator: pending
- Verification result: pending

## Defense Talking Points
- Secrets are no longer tracked in repository.
- Settings API no longer returns plaintext keys to frontend.
- Startup/readiness scripts now include preflight checks and downgrade guidance.
