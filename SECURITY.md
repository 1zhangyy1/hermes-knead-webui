# Security Policy

## Reporting a Vulnerability

Please do not open public issues for secrets, prompt/tool sandbox escapes, file access bugs, or provider credential exposure.

Report security concerns through GitHub private vulnerability reporting for this
repository, or contact the maintainers privately if private reporting is not
available. Include:

- A short description of the issue
- Steps to reproduce
- Affected paths, commands, or product workspaces
- Whether credentials, local files, or generated product code are involved

## Local Secrets

Knead reads local development secrets from `.env`, `.hermes-home/`, and product-specific ignored env files such as `products/ppt-designer/ppt-skill/.env`.

Never commit real provider keys, generated runtime state, sessions, screenshots containing private data, or local product outputs.

Before opening a release PR or tag, run:

```bash
pnpm security:scan
```

The scanner checks tracked and untracked files in Knead-maintained release surfaces such as app code, products, packages, scripts, docs, and root metadata. Ignored local state such as `.env`, `.hermes-home/`, `vendor/`, `node_modules/`, and vendored upstream runtime internals stay outside this fast release scan.
