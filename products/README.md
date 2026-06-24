# Built-in AI Products

This directory contains curated AI products that ship with Knead as source examples.

Current built-ins are listed in [`catalog.json`](catalog.json). That catalog is
the source of truth for which product directories are shipped as maintained
examples.

## What Belongs Here

`products/` is not a dump of everything users create. It is the small public
gallery of products we maintain as part of the repository.

A product belongs here when it proves a reusable product shape:

- `general`: the default chat surface is itself a complete AI product.
- `ppt-designer`: chat can stay present while a structured task workspace grows beside it.
- `ai-otome`: an AI-first product can own an immersive interface without becoming a separate app.

Generated products, one-off experiments, local test products, and draft products
belong in runtime state instead:

```text
.hermes-home/webui/products/
```

Promote a product only when it is useful as a maintained example for other
contributors, not merely because it exists locally.

## Product Contract

Every curated product has a `product.json` manifest that follows
[`product.schema.json`](product.schema.json). The built-in product list follows
[`product-catalog.schema.json`](product-catalog.schema.json). These schemas
capture the stable contract for identity, prompt source, suggestions, layout,
skills, tools, preview entry, and the maintained example catalog.
Product-specific files may add more behavior, but the shell should be able to
understand the manifest without knowing the product's code.

The manifest is intentionally strict. Add product-specific extension data under
`metadata` or `config`; do not add ad hoc top-level fields, runtime state,
generated outputs, local paths, or credentials to `product.json`.

User-created products are runtime state, not source. In development they should live under:

```text
.hermes-home/webui/products/
```

## Promotion Checklist

To promote a generated product into this directory, clean it as a maintained example first:

1. Remove task outputs, local state, secrets, caches, published-draft markers such as `.knead-published.json`, and generated versions.
2. Keep a small `product.json` with `$schema: "https://knead.dev/schemas/product.schema.json"`, `README.md`, and the minimum workspace files needed to run.
3. Add the product id to `products/catalog.json` and the source allowlist in `.gitignore`.
4. Update the root `README.md` and product tests if it becomes part of the official MVP.
5. Explain in the product README what product shape it demonstrates and what should stay out of Git.

Before copying a runtime product into `products/`, run the candidate check:

```bash
pnpm product:check -- .hermes-home/webui/products/<product-id>
```

To preview the source changes needed for promotion:

```bash
pnpm product:promote -- .hermes-home/webui/products/<product-id>
```

To copy it into `products/` and update the source allowlists:

```bash
pnpm product:promote -- .hermes-home/webui/products/<product-id> --apply
```

After promotion, run:

```bash
pnpm verify
```

This validates the built-in product manifests, their preview entries, and the
source/runtime boundary before committing.
