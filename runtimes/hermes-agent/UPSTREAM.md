# Hermes Agent Upstream

This directory is vendored from the official Hermes Agent repository.

- Upstream repository: https://github.com/NousResearch/hermes-agent
- Upstream branch: `main`
- Vendored commit: `d1367355d514b5ce3af6056ca660ab28e9d632e4`
- Vendored at: `2026-06-05`
- Import method: `git subtree --squash`

Initial import command:

```bash
git subtree add \
  --prefix=runtimes/hermes-agent \
  https://github.com/NousResearch/hermes-agent.git \
  main \
  --squash \
  -m "Vendor Hermes Agent runtime"
```

Keep this file updated whenever the vendored runtime is pulled from upstream or redirected to a fork.
