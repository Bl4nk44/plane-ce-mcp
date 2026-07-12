---
name: commit-style
description: Use when writing commit messages or preparing a PR in this repo - Conventional Commits with project-specific scopes and PR rules.
---

# Commit & PR style

Conventional Commits, matching upstream history.

## Format

```
<type>(<scope>): <subject ≤72 chars, imperative, no period>
```

Types: `feat`, `fix`, `perf`, `refactor`, `docs`, `chore`, `test`, `ci`.

Scopes (pick the narrowest): `tools`, a domain (`work-items`, `cycles`, `modules`,
`projects`, ...), `auth`, `client`, `server`, `compat`, `docker`, `deps`.

Examples:
- `fix(work-items): fall back to legacy /issues/ path on self-host 404`
- `feat(compat): add shared endpoint fallback layer with WARNING logging`
- `chore(deps): bump plane-sdk to 0.2.20`

Body: only when the "why" isn't obvious from the subject - e.g. which Plane versions
are affected, link to `docs/plane-api-compat.md` entry.

## PR rules

- One logical change per commit; PR diff ≤150 lines where feasible - split larger work.
- Squash merge.
- PR description states: what was tested against the local self-host instance
  (reference `docs/self-host-testing.md` items run).
- No merge without green CI.
