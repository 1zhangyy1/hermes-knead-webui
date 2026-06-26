# Release Checklist

Use this checklist before tagging or publishing a Knead release.

## 1. Check The Source Boundary

Runtime state must stay out of the source tree.

Also confirm the Git remote and public metadata use the release repository name
(`Hermes Knead WebUI`) rather than the old local project name:

```bash
git remote -v
node -e "const p=require('./package.json'); console.log(p.repository?.url, p.bugs?.url, p.homepage)"
```

The repository audit checks metadata against `https://github.com/1zhangyy1/hermes-knead-webui`
by default. If the release repository lives elsewhere, set
`KNEAD_RELEASE_REPO_URL` before running release checks.

```bash
pnpm audit:repo
pnpm release:clean:local
```

`release:clean:local` is a dry run by default. It reports ignored local release
artifacts such as root `.tmp-*` screenshots/logs, accidental `package-lock.json`
files, product outputs like `products/*/outputs`, `products/*/versions`, local
`.env` files, exported decks, runtime state, and ignored experiment build
artifacts such as `experiments/*/dist` and `*.tsbuildinfo`.

To remove those local-only artifacts:

```bash
pnpm release:clean:local -- --apply
```

## 2. Promote Example Products Carefully

Curated examples may live in `products/`. User-created products should stay in
`.hermes-home/webui/products/` unless they are intentionally promoted.

Before copying a runtime product into `products/`, run:

```bash
pnpm product:check -- .hermes-home/webui/products/<product-id>
pnpm product:promote -- .hermes-home/webui/products/<product-id>
```

A promoted product must have:

- `README.md`
- a `README.md` `Product Shape` section explaining why it is a maintained example
- clean `product.json`
- no ad hoc top-level `product.json` fields outside the public manifest contract
- a valid `preview_entry`
- no local paths, secrets, outputs, generated versions, published-draft markers, or runtime state

To copy it into `products/`, update `products/catalog.json`, and update source allowlists:

```bash
pnpm product:promote -- .hermes-home/webui/products/<product-id> --apply
```

Then run:

```bash
pnpm verify
```

## 3. Run The Release Gate

The release gate checks both unstaged and staged diffs for whitespace errors and
conflict markers before running heavier checks.

Before preparing release commits, inspect the non-destructive batch plan:

```bash
pnpm release:batches
```

This groups the dirty worktree by reviewable release themes and fails if a file
does not fit an expected production area. Use it as a staging guide; it does
not modify the Git index.
The output also shows review guidance and batch dependencies. Do not assume
every batch is independently green as a standalone commit; for example,
release gate changes often depend on product tests, curated product manifests,
and current docs landing together.
The full release gate also runs the quiet classification check automatically.

When you are ready to stage reviewable commits, print the exact `git add`
commands for each batch:

```bash
pnpm release:batches -- --staging
```

Review the printed files before running each command. Prefer one commit per
batch unless a batch is still too large to review comfortably.

The release gate first verifies that CI dependency installation will not fail
because of a stale lockfile by running `pnpm install --frozen-lockfile`.

Run the public-source secret scanner when you want a quick standalone check:

```bash
pnpm security:scan
```

Then run the full release gate:

```bash
pnpm release:check
```

This first fails if local-only product artifacts are still present under
`products/`. It also catches diff whitespace problems, verifies release batch
classification, checks local Markdown links, verifies the frozen lockfile
install, then runs TypeScript checks, repository audit, product manifest checks,
product runtime smoke tests, pytest product tests, and a temporary WebUI HTTP
smoke.

For the final pre-tag check, require a clean Git worktree too:

```bash
pnpm release:check:clean
```

The clean release gate also verifies that `origin` points at the configured
release repository. This prevents tagging and pushing a Knead release to an old
local repository name by accident.

## 4. Update Release Notes

Update [CHANGELOG.md](CHANGELOG.md) before tagging. The changelog should call
out product-facing behavior, repository/source-boundary changes, security
handling, and any promoted example products.

If the bundled Hermes runtime changed, also update:

- [NOTICE.md](NOTICE.md)
- [runtimes/hermes-agent/UPSTREAM.md](runtimes/hermes-agent/UPSTREAM.md)
- [runtimes/hermes-agent/PATCHES.md](runtimes/hermes-agent/PATCHES.md)

## 5. Optional Live Agent Smoke

If a configured Hermes Gateway is running, include a model-backed smoke test:

```bash
KNEAD_RELEASE_AGENT_SMOKE=1 pnpm release:check
```

This is intentionally optional because public CI should not require provider
keys.

## 6. Tag

Only tag after the clean release gate passes:

```bash
pnpm release:check:clean
git tag v0.1.0
git push origin v0.1.0
```

Do not tag if `products/` contains generated task outputs, local secrets, or
runtime-only products.
