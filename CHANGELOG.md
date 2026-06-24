# Changelog

All notable changes to Knead are tracked here.

Knead follows a lightweight changelog format:

- `Added` for new features, examples, docs, or checks
- `Changed` for behavior, UX, architecture, or dependency changes
- `Fixed` for bug fixes
- `Security` for local secret, file access, sandbox, or provider-key handling

## Unreleased

### Added

- Root release checklist, contribution guide, security policy, and MIT license.
- GitHub issue templates, pull request template, CODEOWNERS, Dependabot configuration, and CI verification workflow.
- Repository audit, product manifest verifier, WebUI smoke test, source whitespace checker, Markdown link checker, secret scanner, local artifact cleaner, and release gate scripts.
- Frozen lockfile install verification in the release gate.
- Product promotion guidance for moving cleaned runtime products into `products/`.
- Curated built-in product boundary for `General AI`, `PPT Designer`, and `AI Otome`.
- Strict product manifest schema with explicit `metadata` and `config` extension slots.
- Product-layer tests for draft creation, product storage boundaries, UI status, scope lines, runtime prompts, and static product shell behavior.
- Non-production `experiments/` boundary documentation for prototypes that should not enter the public product surface.

### Changed

- Runtime-generated products are treated as local state under `.hermes-home/webui/products/`.
- Public configuration names use the `KNEAD_*` prefix, with legacy fallbacks kept in code.
- The source tree is organized around app shell, curated products, packages, runtime, scripts, and current docs.
- Product creation and shaping now use explicit product scope instead of frontend keyword classification.
- The bundled Hermes runtime and inherited WebUI code are documented as first-class repository dependencies with attribution boundaries.
- The root package remains private to prevent accidental npm registry publishes while the project is released as source.
- Built-in product example docs and preview entries are aligned with the English public repository surface.
- PPT Designer no longer force-loads a local demo deck on startup; curated product state now comes from defaults, runtime state, or explicit agent output.
- Historical experiment prototypes are excluded from the public release tree; `experiments/README.md` now documents the boundary.

### Security

- Release checks verify public-source secret patterns, local artifact boundaries, runtime product boundaries, and bundled runtime notice coverage before publishing.
- Secret scanning now covers the current design docs and asserts its release-owned scan surface in the repository audit.

## 0.1.0

Initial open-source preparation line. This version is not tagged until `pnpm release:check:clean` passes on the release branch.
